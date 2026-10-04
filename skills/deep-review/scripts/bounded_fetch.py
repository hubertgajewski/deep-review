#!/usr/bin/env python3
"""Optional quota-enforcing metadata fetch for Deep Review remote scopes.

The helper is its own Git protocol v2 client so that it can account for every
received byte, every expanded object, and every byte written to the isolated
store before Git processes the pack. Ordinary ``git fetch`` exposes no
client-side ceiling for expanded objects, so wrapping it would not enforce the
remote-transport quotas.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
from typing import BinaryIO, Callable, Iterable
from urllib.parse import urlsplit
from urllib.request import url2pathname
import zlib


MIB = 1024 * 1024
COMPRESSED_INPUT_LIMIT = 64 * MIB
EXPANDED_OBJECT_LIMIT = 256 * MIB
STORE_DISK_LIMIT = 320 * MIB
# Filesystem allocation rounding, refs, configuration, and pack marker files.
STORE_DISK_RESERVE = 1 * MIB
MIN_PYTHON = (3, 10)
MIN_GIT = (2, 31)
TRANSFER_TIMEOUT_SECONDS = 600
MAX_REFS = 16
MAX_COMMITS = 16
MAX_PKT_LEN = 65520
# One type/size byte plus the smallest zlib stream.
MIN_PACK_ENTRY_BYTES = 9
INFLATE_STEP = 64 * 1024
PROMISOR_REMOTE = "deep-review-source"
HASH_LENGTHS = {"sha1": 20, "sha256": 32}
OBJ_COMMIT, OBJ_TREE, OBJ_BLOB, OBJ_TAG, OBJ_OFS_DELTA, OBJ_REF_DELTA = 1, 2, 3, 4, 6, 7
FLUSH, DELIM, RESPONSE_END = 0, 1, 2

EXIT_FAILURE = 2
EXIT_ACCESS = 3
EXIT_QUOTA = 4

STRIPPED_GIT_ENVIRONMENT = (
    "GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_REPLACE_REF_BASE", "GIT_SHALLOW_FILE", "GIT_EXEC_PATH",
    "GIT_EXTERNAL_DIFF", "GIT_DIFF_OPTS", "GIT_PROTOCOL", "GIT_NAMESPACE",
)


class FetchError(Exception):
    """The bounded fetch failed; the caller must not downgrade."""


class AccessError(FetchError):
    """Authentication, network, or repository access failed."""


class QuotaExceeded(FetchError):
    """A transport quota would be crossed."""


class Unsupported(FetchError):
    """This host or server cannot enforce the transport quotas."""


@dataclass(frozen=True)
class Limits:
    compressed_input: int = COMPRESSED_INPUT_LIMIT
    expanded_objects: int = EXPANDED_OBJECT_LIMIT
    store_disk: int = STORE_DISK_LIMIT

    def as_json(self) -> dict[str, int]:
        return {
            "compressed_input_bytes": self.compressed_input,
            "expanded_object_bytes": self.expanded_objects,
            "store_disk_bytes": self.store_disk,
        }


PACKAGE_LIMITS = Limits()


class Budget:
    """Cumulative accounting for one helper invocation."""

    def __init__(self, limits: Limits) -> None:
        self.limits = limits
        self.input_bytes = 0
        self.expanded_bytes = 0
        self.disk_baseline = 0
        self.disk_pending = 0
        self.disk_reserved = 0

    def charge_input(self, count: int) -> None:
        if self.input_bytes + count > self.limits.compressed_input:
            raise QuotaExceeded(
                f"compressed input would exceed {self.limits.compressed_input} bytes"
            )
        self.input_bytes += count

    def remaining_input(self) -> int:
        return self.limits.compressed_input - self.input_bytes

    def charge_expanded(self, count: int) -> None:
        if self.expanded_bytes + count > self.limits.expanded_objects:
            raise QuotaExceeded(
                f"expanded commit/tree objects would exceed {self.limits.expanded_objects} bytes"
            )
        self.expanded_bytes += count

    def set_disk_baseline(self, measured: int) -> None:
        self.disk_baseline = measured
        self.disk_pending = 0
        self.disk_reserved = 0
        self._check_disk()

    def charge_disk(self, count: int) -> None:
        self.disk_pending += count
        self._check_disk()

    def reserve_disk(self, count: int) -> None:
        self.disk_reserved += count
        self._check_disk()

    def _check_disk(self) -> None:
        projected = (
            self.disk_baseline + self.disk_pending + self.disk_reserved + STORE_DISK_RESERVE
        )
        if projected > self.limits.store_disk:
            raise QuotaExceeded(
                f"isolated-store disk use would exceed {self.limits.store_disk} bytes"
            )


def git_environment() -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items()
        if key not in STRIPPED_GIT_ENVIRONMENT and not key.startswith("GIT_CONFIG")
    }
    environment.update({
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
    })
    return environment


GIT_BASE = ("git", "-c", "core.fsmonitor=false")


def run_git(arguments: list[str], *, input_bytes: bytes | None = None) -> bytes:
    try:
        completed = subprocess.run(
            [*GIT_BASE, *arguments], input=input_bytes, capture_output=True,
            env=git_environment(), check=False,
        )
    except OSError as exc:
        raise FetchError(f"cannot run git: {exc}") from None
    if completed.returncode != 0:
        command = next((argument for argument in arguments if not argument.startswith("-")), "")
        raise FetchError(f"git {command} failed")
    return completed.stdout


def git_version() -> tuple[int, int] | None:
    try:
        completed = subprocess.run(
            ["git", "version"], capture_output=True, env=git_environment(), check=False,
        )
    except OSError:
        return None
    match = re.match(rb"git version (\d+)\.(\d+)", completed.stdout)
    if completed.returncode != 0 or match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def local_capability_problem(
    url: str,
    python_version: tuple[int, ...] = tuple(sys.version_info[:2]),
    installed_git: Callable[[], tuple[int, int] | None] = git_version,
) -> str | None:
    if python_version < MIN_PYTHON:
        return "Python {}.{} or newer is required".format(*MIN_PYTHON)
    version = installed_git()
    if version is None:
        return "git is unavailable"
    if version < MIN_GIT:
        return "Git {}.{} or newer is required".format(*MIN_GIT)
    scheme = urlsplit(url).scheme.lower()
    if scheme not in ("https", "file"):
        return "the bounded helper supports only https:// and file:// remotes"
    return None


def validate_remote_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.query or parts.fragment:
        raise FetchError("remote URL must not contain a query or fragment")
    if parts.scheme.lower() == "https":
        if "@" in parts.netloc or not parts.hostname:
            raise FetchError("HTTPS remote URL must name a host without credentials")
    elif parts.scheme.lower() == "file":
        if parts.netloc not in ("", "localhost") or not parts.path:
            raise FetchError("file remote URL must name a local path")


class Deadline:
    """Kills transport processes that exceed the transfer deadline."""

    def __init__(self, seconds: float) -> None:
        self.expired = False
        self._processes: list[subprocess.Popen[bytes]] = []
        self._lock = threading.Lock()
        self._timer = threading.Timer(seconds, self._expire)
        self._timer.daemon = True
        self._timer.start()

    def register(self, process: subprocess.Popen[bytes]) -> None:
        with self._lock:
            if self.expired:
                process.kill()
            self._processes.append(process)

    def _expire(self) -> None:
        with self._lock:
            self.expired = True
            for process in self._processes:
                if process.poll() is None:
                    process.kill()

    def cancel(self) -> None:
        self._timer.cancel()


class Connection:
    """A Git protocol v2 upload-pack channel."""

    uses_response_end = False

    def handshake(self) -> BinaryIO:
        raise NotImplementedError

    def send(self, payload: bytes) -> BinaryIO:
        raise NotImplementedError

    def finish_response(self) -> None:
        """Validate process state after one complete response."""

    def close(self) -> None:
        """Release transport resources."""


class RemoteHelperConnection(Connection):
    """Uses Git's own HTTPS remote helper, including its credential handling."""

    uses_response_end = True

    def __init__(self, url: str, deadline: Deadline) -> None:
        scheme = urlsplit(url).scheme.lower()
        try:
            self._process = subprocess.Popen(
                [*GIT_BASE, "-c", "protocol.version=2", f"remote-{scheme}", url, url],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=git_environment(),
            )
        except OSError as exc:
            raise Unsupported(f"cannot start the Git remote helper: {exc}") from None
        deadline.register(self._process)
        assert self._process.stdin is not None and self._process.stdout is not None
        self._stdin = self._process.stdin
        self._stdout = self._process.stdout

    def _command(self, line: bytes) -> None:
        try:
            self._stdin.write(line)
            self._stdin.flush()
        except OSError:
            raise AccessError("the Git remote helper exited") from None

    def handshake(self) -> BinaryIO:
        # Listing capabilities is local; only stateless-connect reaches the network.
        self._command(b"capabilities\n")
        capabilities = set()
        while True:
            line = self._stdout.readline(4096)
            if not line:
                raise Unsupported("the Git remote helper did not list capabilities")
            if line == b"\n":
                break
            capabilities.add(line.strip().lstrip(b"*"))
        if b"stateless-connect" not in capabilities:
            raise Unsupported("the Git remote helper lacks stateless-connect")
        self._command(b"stateless-connect git-upload-pack\n")
        reply = self._stdout.readline(4096)
        if reply == b"\n":
            return self._stdout
        if reply == b"fallback\n":
            raise Unsupported("the server does not offer Git protocol v2")
        raise AccessError("the remote could not be reached or authentication failed")

    def send(self, payload: bytes) -> BinaryIO:
        self._command(payload)
        return self._stdout

    def close(self) -> None:
        for stream in (self._stdin, self._stdout):
            try:
                stream.close()
            except OSError:
                pass
        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()


class UploadPackConnection(Connection):
    """Runs the local upload-pack in stateless mode for file:// remotes."""

    def __init__(self, url: str, deadline: Deadline) -> None:
        self._path = url2pathname(urlsplit(url).path)
        self._deadline = deadline
        self._process: subprocess.Popen[bytes] | None = None

    def _start(self, *arguments: str) -> subprocess.Popen[bytes]:
        self.close()
        environment = git_environment()
        environment["GIT_PROTOCOL"] = "version=2"
        try:
            process = subprocess.Popen(
                [*GIT_BASE, "upload-pack", "--stateless-rpc", *arguments,
                 "--", self._path],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env=environment,
            )
        except OSError as exc:
            raise AccessError(f"cannot run git upload-pack: {exc}") from None
        self._deadline.register(process)
        self._process = process
        return process

    def handshake(self) -> BinaryIO:
        process = self._start("--advertise-refs")
        assert process.stdin is not None and process.stdout is not None
        process.stdin.close()
        return process.stdout

    def send(self, payload: bytes) -> BinaryIO:
        process = self._start()
        assert process.stdin is not None and process.stdout is not None
        try:
            process.stdin.write(payload)
            process.stdin.close()
        except OSError:
            raise AccessError("git upload-pack exited") from None
        return process.stdout

    def finish_response(self) -> None:
        if self._process is not None and self._process.wait() != 0:
            raise FetchError("git upload-pack failed")
        self.close()

    def close(self) -> None:
        if self._process is not None:
            if self._process.poll() is None:
                self._process.kill()
            self._process.wait()
            assert self._process.stdout is not None
            self._process.stdout.close()
            self._process = None


def open_connection(url: str, deadline: Deadline) -> Connection:
    if urlsplit(url).scheme.lower() == "file":
        return UploadPackConnection(url, deadline)
    return RemoteHelperConnection(url, deadline)


class PacketReader:
    """Reads pkt-lines while charging every received byte as compressed input."""

    def __init__(self, stream: BinaryIO, budget: Budget, closed: type[FetchError] = FetchError):
        self._stream = stream
        self._budget = budget
        self._closed = closed

    def _read_exact(self, count: int) -> bytes:
        chunks = []
        remaining = count
        while remaining:
            chunk = self._stream.read(remaining)
            if not chunk:
                raise self._closed("the transport closed before the response completed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def read(self) -> bytes | int:
        self._budget.charge_input(4)
        header = self._read_exact(4)
        try:
            length = int(header.decode("ascii"), 16)
        except (UnicodeDecodeError, ValueError):
            raise FetchError("malformed pkt-line header") from None
        if length in (FLUSH, DELIM, RESPONSE_END):
            return length
        if length < 5 or length > MAX_PKT_LEN:
            raise FetchError("invalid pkt-line length")
        self._budget.charge_input(length - 4)
        payload = self._read_exact(length - 4)
        if payload.startswith(b"ERR "):
            raise self._closed("the server reported an error")
        return payload

    def at_eof(self) -> bool:
        return self._stream.read(1) == b""


def pkt_line(text: str) -> bytes:
    data = text.encode("utf-8")
    return b"%04x" % (len(data) + 4) + data


def read_advertisement(stream: BinaryIO, budget: Budget) -> dict[str, str]:
    reader = PacketReader(stream, budget, closed=AccessError)
    first = reader.read()
    if first != b"version 2\n":
        raise Unsupported("the server does not offer Git protocol v2")
    capabilities: dict[str, str] = {}
    while True:
        packet = reader.read()
        if packet == FLUSH:
            return capabilities
        if not isinstance(packet, bytes):
            raise FetchError("malformed capability advertisement")
        key, _, value = packet.decode("utf-8", "replace").rstrip("\n").partition("=")
        capabilities[key] = value


def server_capability_problem(capabilities: dict[str, str]) -> str | None:
    if "ls-refs" not in capabilities or "fetch" not in capabilities:
        return "the server does not offer ls-refs and fetch"
    if "filter" not in capabilities["fetch"].split():
        return "the server does not advertise partial-clone filtering"
    if capabilities.get("object-format", "sha1") not in HASH_LENGTHS:
        return "the server uses an unsupported object format"
    return None


def finish_response(connection: Connection, reader: PacketReader) -> None:
    if connection.uses_response_end:
        if reader.read() != RESPONSE_END:
            raise FetchError("missing response-end packet")
    elif not reader.at_eof():
        raise FetchError("unexpected data after the response")
    connection.finish_response()


def command_request(command: str, object_format: str, arguments: Iterable[str]) -> bytes:
    payload = [pkt_line(f"command={command}\n"), pkt_line(f"object-format={object_format}\n"), b"0001"]
    payload.extend(pkt_line(f"{argument}\n") for argument in arguments)
    payload.append(b"0000")
    return b"".join(payload)


def list_refs(
    connection: Connection, budget: Budget, object_format: str, sources: list[str]
) -> dict[str, str]:
    stream = connection.send(
        command_request("ls-refs", object_format, (f"ref-prefix {source}" for source in sources))
    )
    reader = PacketReader(stream, budget)
    wanted = set(sources)
    found: dict[str, str] = {}
    hex_length = HASH_LENGTHS[object_format] * 2
    while True:
        packet = reader.read()
        if packet == FLUSH:
            break
        if not isinstance(packet, bytes):
            raise FetchError("malformed ls-refs response")
        fields = packet.rstrip(b"\n").split(b" ")
        if len(fields) < 2 or not re.fullmatch(rb"[0-9a-f]{%d}" % hex_length, fields[0]):
            raise FetchError("malformed ls-refs response")
        name = fields[1].decode("utf-8", "replace")
        if name in wanted:
            found[name] = fields[0].decode("ascii")
    finish_response(connection, reader)
    missing = sorted(wanted - set(found))
    if missing:
        raise FetchError(f"the server did not advertise {', '.join(missing)}")
    return found


class SidebandPack:
    """Yields band-1 payloads from the packfile section."""

    def __init__(self, reader: PacketReader) -> None:
        self._reader = reader
        self.done = False

    def next_chunk(self) -> bytes | None:
        while not self.done:
            packet = self._reader.read()
            if packet == FLUSH:
                self.done = True
                break
            if not isinstance(packet, bytes) or not packet:
                raise FetchError("malformed packfile section")
            band = packet[0]
            if band == 1:
                if len(packet) > 1:
                    return packet[1:]
            elif band == 3:
                raise FetchError("the server reported a fatal pack error")
            elif band != 2:
                raise FetchError("unknown sideband channel")
        return None


class PackInput:
    """Buffered pack bytes that reach disk only after the parser consumes them."""

    def __init__(self, chunks: SidebandPack, sink: BinaryIO, budget: Budget, hash_name: str):
        self._chunks = chunks
        self._sink = sink
        self._budget = budget
        self._data = memoryview(b"")
        self.hasher = hashlib.new(hash_name)

    def peek(self) -> memoryview:
        while not self._data:
            chunk = self._chunks.next_chunk()
            if chunk is None:
                raise FetchError("the pack stream ended early")
            self._data = memoryview(chunk)
        return self._data

    def consume(self, count: int, *, hashed: bool = True) -> bytes:
        data = bytes(self._data[:count])
        self._data = self._data[count:]
        self._budget.charge_disk(len(data))
        self._sink.write(data)
        if hashed:
            self.hasher.update(data)
        return data

    def read_exact(self, count: int, *, hashed: bool = True) -> bytes:
        parts = []
        while count:
            view = self.peek()
            part = self.consume(min(count, len(view)), hashed=hashed)
            parts.append(part)
            count -= len(part)
        return b"".join(parts)

    def expect_end(self) -> None:
        if self._data or self._chunks.next_chunk() is not None:
            raise FetchError("unexpected data after the pack trailer")


def read_varint(data: bytes, offset: int) -> tuple[int, int] | None:
    value = shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return value, offset
        if shift > 63:
            raise FetchError("malformed delta header")
    return None


def inflate_entry(pack: PackInput, budget: Budget, declared: int, is_delta: bool) -> None:
    """Inflate one entry, never producing more than its declared size."""
    decompressor = zlib.decompressobj()
    produced = 0
    head = b""
    result_known = not is_delta
    while not decompressor.eof:
        view = pack.peek()
        try:
            output = decompressor.decompress(view, INFLATE_STEP)
        except zlib.error:
            raise FetchError("malformed compressed pack entry") from None
        if decompressor.eof:
            consumed = len(view) - len(decompressor.unused_data)
        else:
            consumed = len(view) - len(decompressor.unconsumed_tail)
        pack.consume(consumed)
        produced += len(output)
        if produced > declared:
            raise FetchError("a pack entry inflates beyond its declared size")
        if not result_known:
            head += output[:24]
            base = read_varint(head, 0)
            result = read_varint(head, base[1]) if base else None
            if result is not None:
                result_known = True
                budget.charge_expanded(max(0, result[0] - declared))
            elif len(head) >= 24:
                raise FetchError("malformed delta header")
    if produced != declared:
        raise FetchError("a pack entry does not match its declared size")
    if not result_known:
        raise FetchError("malformed delta header")


def parse_pack(pack: PackInput, budget: Budget, object_format: str) -> str:
    header = pack.read_exact(12)
    if header[:4] != b"PACK" or int.from_bytes(header[4:8], "big") not in (2, 3):
        raise FetchError("the response is not a Git pack")
    count = int.from_bytes(header[8:12], "big")
    if count * MIN_PACK_ENTRY_BYTES > budget.remaining_input():
        raise QuotaExceeded("the pack declares more objects than the compressed-input quota can carry")
    hash_length = HASH_LENGTHS[object_format]
    # pack-*.idx v2: header, fanout, names, CRCs, offsets, and two trailing hashes.
    pack_index_bytes = 8 + 256 * 4 + count * (hash_length + 8) + 2 * hash_length
    budget.reserve_disk(pack_index_bytes)
    for _ in range(count):
        byte = pack.read_exact(1)[0]
        kind = (byte >> 4) & 7
        size = byte & 0x0F
        shift = 4
        while byte & 0x80:
            if shift > 60:
                raise FetchError("malformed pack entry header")
            byte = pack.read_exact(1)[0]
            size |= (byte & 0x7F) << shift
            shift += 7
        if kind == OBJ_BLOB:
            raise FetchError("the response includes a blob body")
        if kind == OBJ_OFS_DELTA:
            byte = pack.read_exact(1)[0]
            while byte & 0x80:
                byte = pack.read_exact(1)[0]
        elif kind == OBJ_REF_DELTA:
            pack.read_exact(hash_length)
        elif kind not in (OBJ_COMMIT, OBJ_TREE):
            raise FetchError("the response includes an unexpected object type")
        budget.charge_expanded(size)
        inflate_entry(pack, budget, size, kind in (OBJ_OFS_DELTA, OBJ_REF_DELTA))
    expected = pack.hasher.digest()
    if pack.read_exact(hash_length, hashed=False) != expected:
        raise FetchError("the pack checksum does not match")
    pack.expect_end()
    return expected.hex()


def disk_usage(root: Path) -> int:
    total = 0
    for directory, names, files in os.walk(root, followlinks=False):
        for name in [*names, *files]:
            status = os.lstat(os.path.join(directory, name))
            total += max(status.st_size, getattr(status, "st_blocks", 0) * 512)
    return total


def fetch_pack(
    connection: Connection, budget: Budget, store: Path, object_format: str,
    wants: list[str], haves: list[str],
) -> None:
    arguments = ["no-progress", "ofs-delta", "filter blob:none"]
    arguments.extend(f"want {oid}" for oid in wants)
    arguments.extend(f"have {oid}" for oid in haves)
    arguments.append("done")
    stream = connection.send(command_request("fetch", object_format, arguments))
    reader = PacketReader(stream, budget)
    if reader.read() != b"packfile\n":
        raise FetchError("the server did not send a packfile section")
    pack_directory = store / "objects" / "pack"
    temporary = pack_directory / "tmp_deep_review.pack"
    with open(temporary, "xb") as sink:
        pack = PackInput(SidebandPack(reader), sink, budget, object_format)
        checksum = parse_pack(pack, budget, object_format)
    finish_response(connection, reader)
    final = pack_directory / f"pack-{checksum}.pack"
    if final.exists():
        raise FetchError("the server resent an existing pack")
    os.replace(temporary, final)
    run_git([f"--git-dir={store}", "index-pack", "--no-rev-index", str(final)])
    (pack_directory / f"pack-{checksum}.promisor").touch()
    budget.set_disk_baseline(disk_usage(store))


def object_types(store: Path, object_ids: list[str]) -> list[str]:
    output = run_git(
        [f"--git-dir={store}", "cat-file", "--batch-check=%(objecttype)"],
        input_bytes="".join(f"{oid}\n" for oid in object_ids).encode("ascii"),
    )
    return [line.split(" ")[-1] for line in output.decode("ascii").splitlines()]


def initialize_store(store: Path, object_format: str) -> None:
    # The promisor remote has no URL, so even a Git version that ignores
    # GIT_NO_LAZY_FETCH cannot lazily fetch missing blobs into this store.
    run_git(["init", "--quiet", "--bare", "--template=", f"--object-format={object_format}", str(store)])
    settings = (
        ("core.repositoryformatversion", "1"),
        ("extensions.partialClone", PROMISOR_REMOTE),
        (f"remote.{PROMISOR_REMOTE}.promisor", "true"),
        (f"remote.{PROMISOR_REMOTE}.partialclonefilter", "blob:none"),
        ("core.logAllRefUpdates", "false"),
        ("gc.auto", "0"),
        ("maintenance.auto", "false"),
    )
    for key, value in settings:
        run_git([f"--git-dir={store}", "config", key, value])
    (store / "objects" / "pack").mkdir(parents=True, exist_ok=True)


def parse_ref_mappings(values: list[str]) -> list[tuple[str, str]]:
    if not values or len(values) > MAX_REFS:
        raise FetchError(f"supply between 1 and {MAX_REFS} --ref values")
    mappings = []
    for value in values:
        source, separator, destination = value.partition(":")
        if not separator:
            raise FetchError("--ref must be SOURCE:DESTINATION")
        for name in (source, destination):
            if not name.startswith("refs/") or any(c in name for c in "*?[\\"):
                raise FetchError("--ref names must be complete refs without patterns")
            try:
                run_git(["check-ref-format", name])
            except FetchError:
                raise FetchError(f"invalid ref name: {name}") from None
        mappings.append((source, destination))
    if len({destination for _, destination in mappings}) != len(mappings):
        raise FetchError("--ref destinations must be distinct")
    return mappings


def probe(url: str, *, connect: Callable[[str, Deadline], Connection] = open_connection) -> dict:
    limits = PACKAGE_LIMITS.as_json()
    problem = local_capability_problem(url)
    if problem is None:
        validate_remote_url(url)
        deadline = Deadline(TRANSFER_TIMEOUT_SECONDS)
        connection = None
        try:
            connection = connect(url, deadline)
            advertised = read_advertisement(connection.handshake(), Budget(PACKAGE_LIMITS))
            problem = server_capability_problem(advertised)
        except Unsupported as exc:
            problem = str(exc)
        finally:
            if connection is not None:
                connection.close()
            deadline.cancel()
    if problem is not None:
        return {"transport_quotas": "unavailable", "reason": problem, "limits": limits}
    return {"transport_quotas": "enforced", "limits": limits}


def fetch(
    url: str, store: Path, ref_values: list[str], commits: list[str], *,
    limits: Limits = PACKAGE_LIMITS,
    connect: Callable[[str, Deadline], Connection] = open_connection,
) -> dict:
    problem = local_capability_problem(url)
    if problem is not None:
        raise FetchError(f"transport quotas cannot be enforced: {problem}")
    validate_remote_url(url)
    mappings = parse_ref_mappings(ref_values)
    if len(commits) > MAX_COMMITS:
        raise FetchError(f"supply at most {MAX_COMMITS} --commit values")
    store = store.absolute()
    if not store.parent.is_dir():
        raise FetchError("the store parent directory does not exist")
    try:
        store.mkdir(mode=0o700)
    except FileExistsError:
        raise FetchError("the store path already exists") from None
    deadline = Deadline(TRANSFER_TIMEOUT_SECONDS)
    connection = None
    try:
        budget = Budget(limits)
        connection = connect(url, deadline)
        try:
            capabilities = read_advertisement(connection.handshake(), budget)
        except Unsupported as exc:
            raise FetchError(f"transport quotas cannot be enforced: {exc}") from None
        problem = server_capability_problem(capabilities)
        if problem is not None:
            raise FetchError(f"transport quotas cannot be enforced: {problem}")
        object_format = capabilities.get("object-format", "sha1")
        hex_pattern = re.compile(rf"[0-9a-f]{{{HASH_LENGTHS[object_format] * 2}}}")
        if not all(hex_pattern.fullmatch(oid) for oid in commits):
            raise FetchError("--commit values must be full object IDs")
        initialize_store(store, object_format)
        budget.set_disk_baseline(disk_usage(store))
        tips = list_refs(connection, budget, object_format, [source for source, _ in mappings])
        wants = sorted(set(tips.values()))
        fetch_pack(connection, budget, store, object_format, wants, [])
        missing = sorted({
            oid for oid, kind in zip(commits, object_types(store, commits)) if kind == "missing"
        })
        if missing:
            fetch_pack(connection, budget, store, object_format, missing, wants)
        connection.close()
        connection = None
        present = run_git(
            [f"--git-dir={store}", "cat-file", "--batch-all-objects", "--batch-check=%(objecttype)"]
        ).decode("ascii").split()
        if set(present) - {"commit", "tree"}:
            raise FetchError("the response included an object other than a commit or tree")
        required = [*wants, *commits]
        if any(kind != "commit" for kind in object_types(store, required)):
            raise FetchError("a requested identity is not a commit in the isolated store")
        refs = {}
        for source, destination in mappings:
            run_git([f"--git-dir={store}", "update-ref", destination, tips[source]])
            refs[destination] = tips[source]
        budget.set_disk_baseline(disk_usage(store))
        return {
            "transport_quotas": "enforced",
            "store": str(store),
            "object_format": object_format,
            "refs": refs,
            "commits": sorted(set(commits)),
            "usage": {
                "compressed_input_bytes": budget.input_bytes,
                "expanded_object_bytes": budget.expanded_bytes,
                "store_disk_bytes": budget.disk_baseline,
            },
            "limits": limits.as_json(),
        }
    except BaseException as exc:
        if connection is not None:
            connection.close()
        shutil.rmtree(store, ignore_errors=True)
        if deadline.expired and not isinstance(exc, QuotaExceeded):
            raise FetchError(f"the transfer exceeded {TRANSFER_TIMEOUT_SECONDS} seconds") from None
        raise
    finally:
        deadline.cancel()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    probe_parser = subparsers.add_parser("probe", help="verify that all transport quotas can be enforced")
    probe_parser.add_argument("--remote-url", required=True)
    fetch_parser = subparsers.add_parser("fetch", help="fetch commit/tree metadata under the transport quotas")
    fetch_parser.add_argument("--remote-url", required=True)
    fetch_parser.add_argument("--store", required=True, type=Path)
    fetch_parser.add_argument("--ref", action="append", default=[], metavar="SOURCE:DESTINATION")
    fetch_parser.add_argument("--commit", action="append", default=[], metavar="OBJECT_ID")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "probe":
            result = probe(args.remote_url)
        else:
            result = fetch(args.remote_url, args.store, args.ref, args.commit)
    except QuotaExceeded as exc:
        print(f"transport quota exceeded: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_QUOTA) from None
    except AccessError as exc:
        print(f"remote access failed: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_ACCESS) from None
    except FetchError as exc:
        print(f"bounded fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_FAILURE) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
