from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import http.server
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import zlib


ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "skills" / "deep-review" / "scripts" / "bounded_fetch.py"
SPEC = importlib.util.spec_from_file_location("deep_review_bounded_fetch", HELPER_PATH)
assert SPEC is not None and SPEC.loader is not None
BF = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BF
SPEC.loader.exec_module(BF)

MIB = 1024 * 1024
FAKE_URL = "https://example.invalid/group/project.git"
ZERO_OID = "0" * 40


def git(*arguments: str, cwd: Path | None = None) -> str:
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    environment.update({
        "GIT_AUTHOR_NAME": "Deep Review Tests",
        "GIT_AUTHOR_EMAIL": "tests@example.invalid",
        "GIT_COMMITTER_NAME": "Deep Review Tests",
        "GIT_COMMITTER_EMAIL": "tests@example.invalid",
    })
    completed = subprocess.run(
        ["git", *arguments], cwd=cwd, env=environment, check=True,
        capture_output=True, text=True,
    )
    return completed.stdout.strip()


def store_git(store: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", f"--git-dir={store}", *arguments], env=BF.git_environment(),
        check=True, capture_output=True, text=True,
    )
    return completed.stdout.strip()


def pkt(data: bytes | str) -> bytes:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return b"%04x" % (len(data) + 4) + data


def entry_header(kind: int, size: int) -> bytes:
    byte = (kind << 4) | (size & 0x0F)
    size >>= 4
    encoded = bytearray()
    while size:
        encoded.append(byte | 0x80)
        byte = size & 0x7F
        size >>= 7
    encoded.append(byte)
    return bytes(encoded)


def varint(value: int) -> bytes:
    encoded = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            encoded.append(byte | 0x80)
        else:
            encoded.append(byte)
            return bytes(encoded)


def entry(kind: int, payload: bytes, *, declared: int | None = None, prefix: bytes = b"") -> bytes:
    size = len(payload) if declared is None else declared
    return entry_header(kind, size) + prefix + zlib.compress(payload)


def build_pack(entries: list[bytes], *, count: int | None = None) -> bytes:
    body = b"PACK" + (2).to_bytes(4, "big") + (len(entries) if count is None else count).to_bytes(4, "big")
    body += b"".join(entries)
    return body + hashlib.sha1(body).digest()


def packfile_response(pack: bytes) -> bytes:
    parts = [pkt("packfile\n")]
    for offset in range(0, len(pack), 65515):
        parts.append(pkt(b"\x01" + pack[offset:offset + 65515]))
    parts.append(b"0000")
    return b"".join(parts)


def ls_refs_response(oid: str, name: str = "refs/heads/main") -> bytes:
    return pkt(f"{oid} {name}\n") + b"0000"


def advertisement(*, version_two: bool = True, fetch: str = "shallow filter") -> bytes:
    if not version_two:
        return pkt(f"{ZERO_OID} HEAD\0side-band-64k\n") + b"0000"
    return b"".join([
        pkt("version 2\n"), pkt("ls-refs=unborn\n"), pkt(f"fetch={fetch}\n"),
        pkt("object-format=sha1\n"), b"0000",
    ])


class FakeConnection(BF.Connection):
    def __init__(self, responses: list[bytes], *, advert: bytes | None = None) -> None:
        self.responses = list(responses)
        self.advert = advertisement() if advert is None else advert
        self.requests: list[bytes] = []
        self.closed = False

    def handshake(self) -> io.BytesIO:
        return io.BytesIO(self.advert)

    def send(self, payload: bytes) -> io.BytesIO:
        self.requests.append(payload)
        return io.BytesIO(self.responses.pop(0))

    def close(self) -> None:
        self.closed = True


class GitHttpBackend(http.server.BaseHTTPRequestHandler):
    project_root = ""

    def _respond(self, body: bytes) -> None:
        path, _, query = self.path.partition("?")
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "GIT_PROJECT_ROOT": self.project_root,
            "GIT_HTTP_EXPORT_ALL": "1",
            "REQUEST_METHOD": self.command,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            "CONTENT_LENGTH": str(len(body)),
            "GIT_PROTOCOL": self.headers.get("Git-Protocol", ""),
            "REMOTE_ADDR": "127.0.0.1",
        }
        if "SYSTEMROOT" in os.environ:
            environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        output = subprocess.run(
            ["git", "http-backend"], input=body, env=environment, capture_output=True,
        ).stdout
        head, _, payload = output.partition(b"\r\n\r\n")
        status = 200
        headers = []
        for line in head.split(b"\r\n"):
            name, _, value = line.decode("latin-1").partition(":")
            if name.lower() == "status":
                status = int(value.split()[0])
            elif name:
                headers.append((name, value.strip()))
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - http.server interface
        self._respond(b"")

    def do_POST(self) -> None:  # noqa: N802 - http.server interface
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            chunks = []
            while True:
                size = int(self.rfile.readline().strip(), 16)
                if size == 0:
                    self.rfile.readline()
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.readline()
            body = b"".join(chunks)
        else:
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._respond(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


class BoundedFetchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="deep review fetch ")
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.git"
        git("init", "--quiet", "--bare", str(self.source))
        git("config", "uploadpack.allowFilter", "true", cwd=self.source)
        git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=self.source)
        work = self.root / "work"
        git("init", "--quiet", str(work))
        for index in range(3):
            (work / f"file-{index}.txt").write_text(f"content {index}\n", encoding="utf-8")
            (work / f"dir-{index}").mkdir()
            (work / f"dir-{index}" / "nested.txt").write_text("nested\n", encoding="utf-8")
            git("add", "-A", cwd=work)
            git("commit", "--quiet", "-m", f"commit {index}", cwd=work)
        self.main_oid = git("rev-parse", "HEAD", cwd=work)
        git("push", "--quiet", str(self.source), "HEAD:refs/heads/main", cwd=work)
        git("checkout", "--quiet", "-b", "side", "HEAD~1", cwd=work)
        (work / "side.txt").write_text("side\n", encoding="utf-8")
        git("add", "side.txt", cwd=work)
        git("commit", "--quiet", "-m", "side", cwd=work)
        self.side_oid = git("rev-parse", "HEAD", cwd=work)
        # Make the side commit present but unadvertised, like a recorded evidence commit.
        git("push", "--quiet", str(self.source), "HEAD:refs/heads/side", cwd=work)
        git("update-ref", "-d", "refs/heads/side", cwd=self.source)
        self.url = self.source.as_uri()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_helper(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HELPER_PATH), *arguments],
            capture_output=True, text=True, check=False,
        )

    def fake_fetch(self, connection: FakeConnection, **limits: int) -> Path:
        store = self.root / "fake-store"
        with self.assertRaises(BF.FetchError) as raised:
            BF.fetch(
                FAKE_URL, store, ["refs/heads/main:refs/deep-review/head"], [],
                limits=BF.Limits(**limits), connect=lambda _url, _deadline: connection,
            )
        self.assertFalse(store.exists(), "a failed bounded fetch must discard its store")
        self.exception = raised.exception
        return store

    def assert_quota(self, connection: FakeConnection, quota: str, **limits: int) -> None:
        self.fake_fetch(connection, **limits)
        self.assertIsInstance(self.exception, BF.QuotaExceeded)
        self.assertIn(quota, str(self.exception))

    # Probe: selection happens before any object is requested.

    def test_probe_reports_enforced_for_capable_remote(self) -> None:
        completed = self.run_helper("probe", "--remote-url", self.url)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["transport_quotas"], "enforced")
        self.assertEqual(result["limits"], {
            "compressed_input_bytes": 64 * MIB,
            "expanded_object_bytes": 256 * MIB,
            "store_disk_bytes": 320 * MIB,
        })

    def test_probe_requires_server_filter_support(self) -> None:
        git("config", "uploadpack.allowFilter", "false", cwd=self.source)
        completed = self.run_helper("probe", "--remote-url", self.url)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["transport_quotas"], "unavailable")
        self.assertIn("partial-clone filtering", result["reason"])

    def test_probe_reports_unavailable_for_unsupported_transports(self) -> None:
        for url in (
            "ssh://git@gitlab.com/group/project.git",
            "git@github.com:owner/repository.git",
            "http://gitlab.example/group/project.git",
        ):
            with self.subTest(url=url):
                completed = self.run_helper("probe", "--remote-url", url)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                result = json.loads(completed.stdout)
                self.assertEqual(result["transport_quotas"], "unavailable")
                self.assertIn("https:// and file://", result["reason"])

    def test_probe_requires_compatible_python_and_git(self) -> None:
        def git_version() -> tuple[int, int]:
            return (2, 54)

        self.assertIsNone(BF.local_capability_problem(FAKE_URL, (3, 10), git_version))
        self.assertIn("Python 3.10", BF.local_capability_problem(FAKE_URL, (3, 9), git_version))
        self.assertIn("Git 2.31", BF.local_capability_problem(FAKE_URL, (3, 14), lambda: (2, 30)))
        self.assertIn("git is unavailable", BF.local_capability_problem(FAKE_URL, (3, 14), lambda: None))

    def test_probe_reports_unavailable_without_protocol_v2(self) -> None:
        connection = FakeConnection([], advert=advertisement(version_two=False))
        result = BF.probe(FAKE_URL, connect=lambda _url, _deadline: connection)
        self.assertEqual(result["transport_quotas"], "unavailable")
        self.assertIn("protocol v2", result["reason"])
        self.assertEqual(connection.requests, [], "the probe must not request objects")

    def test_probe_access_failure_is_not_a_downgrade(self) -> None:
        missing = (self.root / "missing.git").as_uri()
        completed = self.run_helper("probe", "--remote-url", missing)
        self.assertEqual(completed.returncode, BF.EXIT_ACCESS)
        self.assertEqual(completed.stdout, "")
        self.assertIn("remote access failed", completed.stderr)

    # Bounded fetch path.

    def test_fetch_materializes_quota_bounded_blobless_store(self) -> None:
        store = self.root / "store"
        completed = self.run_helper(
            "fetch", "--remote-url", self.url, "--store", str(store),
            "--ref", "refs/heads/main:refs/deep-review/base", "--commit", self.side_oid,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["transport_quotas"], "enforced")
        self.assertEqual(result["refs"], {"refs/deep-review/base": self.main_oid})
        self.assertEqual(result["commits"], [self.side_oid])
        for name, used in result["usage"].items():
            self.assertGreater(used, 0, name)
            self.assertLessEqual(used, result["limits"][name], name)

        self.assertEqual(store_git(store, "rev-parse", "refs/deep-review/base"), self.main_oid)
        self.assertEqual(store_git(store, "cat-file", "-t", self.side_oid), "commit")
        kinds = set(store_git(
            store, "cat-file", "--batch-all-objects", "--batch-check=%(objecttype)"
        ).split())
        self.assertEqual(kinds, {"commit", "tree"})
        self.assertIn("file-0.txt", store_git(store, "ls-tree", "-r", "--name-only", self.main_oid))
        self.assertEqual(store_git(store, "config", "extensions.partialClone"), "deep-review-source")
        packs = sorted(path.name for path in (store / "objects" / "pack").iterdir())
        self.assertEqual(len([name for name in packs if name.endswith(".promisor")]), 2)

    def test_fetch_uses_git_remote_helper_for_https(self) -> None:
        GitHttpBackend.project_root = str(self.root)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), GitHttpBackend)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        # Plain HTTP stays unsupported publicly; loopback exercises the same helper code.
        loopback = f"http://127.0.0.1:{server.server_address[1]}/source.git"

        def connect(_url: str, deadline: object) -> object:
            return BF.RemoteHelperConnection(loopback, deadline)

        store = self.root / "https-store"
        result = BF.fetch(
            FAKE_URL, store, ["refs/heads/main:refs/deep-review/head"], [self.side_oid],
            connect=connect,
        )
        self.assertEqual(result["refs"], {"refs/deep-review/head": self.main_oid})
        self.assertEqual(store_git(store, "cat-file", "-t", self.side_oid), "commit")

        unreachable = f"http://127.0.0.1:{server.server_address[1]}/missing.git"
        with self.assertRaises(BF.AccessError):
            BF.fetch(
                FAKE_URL, self.root / "missing-store", ["refs/heads/main:refs/x"], [],
                connect=lambda _url, deadline: BF.RemoteHelperConnection(unreachable, deadline),
            )
        self.assertFalse((self.root / "missing-store").exists())

    def test_fetch_refuses_when_quotas_cannot_be_enforced(self) -> None:
        store = self.root / "store"
        completed = self.run_helper(
            "fetch", "--remote-url", "ssh://git@gitlab.com/group/project.git",
            "--store", str(store), "--ref", "refs/heads/main:refs/x",
        )
        self.assertEqual(completed.returncode, BF.EXIT_FAILURE)
        self.assertIn("cannot be enforced", completed.stderr)
        self.assertFalse(store.exists())

        connection = FakeConnection([], advert=advertisement(fetch="shallow"))
        self.fake_fetch(connection)
        self.assertIn("cannot be enforced", str(self.exception))
        self.assertEqual(connection.requests, [])

    def test_fetch_validates_arguments_before_creating_store(self) -> None:
        store = self.root / "store"
        for refs in ([], ["refs/heads/main"], ["refs/heads/*:refs/x"], ["main:refs/x"],
                     ["refs/heads/main:refs/x", "refs/heads/other:refs/x"]):
            with self.subTest(refs=refs):
                with self.assertRaises(BF.FetchError):
                    BF.fetch(self.url, store, refs, [])
                self.assertFalse(store.exists())
        store.mkdir()
        with self.assertRaisesRegex(BF.FetchError, "already exists"):
            BF.fetch(self.url, store, ["refs/heads/main:refs/x"], [])
        self.assertTrue(store.is_dir(), "a pre-existing path is never removed")

    # Independent quota breaches.

    def test_compressed_input_quota_is_enforced_while_receiving(self) -> None:
        store = self.root / "store"
        with self.assertRaises(BF.QuotaExceeded) as raised:
            BF.fetch(
                self.url, store, ["refs/heads/main:refs/x"], [],
                limits=BF.Limits(compressed_input=600),
            )
        self.assertIn("compressed input", str(raised.exception))
        self.assertFalse(store.exists())

    def test_compressed_input_quota_bounds_declared_object_count(self) -> None:
        pack = build_pack([], count=10_000)
        connection = FakeConnection([ls_refs_response(ZERO_OID), packfile_response(pack)])
        self.assert_quota(connection, "compressed-input quota", compressed_input=64 * 1024)

    def test_expanded_object_quota_rejects_declared_size_before_inflating(self) -> None:
        oversized = entry_header(BF.OBJ_TREE, 300 * MIB) + zlib.compress(b"x" * 64)
        connection = FakeConnection([ls_refs_response(ZERO_OID), packfile_response(build_pack([oversized]))])
        self.assert_quota(connection, "expanded commit/tree objects")

    def test_expanded_object_quota_counts_delta_results(self) -> None:
        base = entry(BF.OBJ_TREE, b"")
        delta = varint(0) + varint(300 * MIB) + b"\x01x"
        ofs_delta = entry(BF.OBJ_OFS_DELTA, delta, prefix=bytes([len(base)]))
        connection = FakeConnection([
            ls_refs_response(ZERO_OID), packfile_response(build_pack([base, ofs_delta])),
        ])
        self.assert_quota(connection, "expanded commit/tree objects")

    def test_store_disk_quota_is_enforced_while_writing(self) -> None:
        payload = os.urandom(3 * MIB)
        connection = FakeConnection([
            ls_refs_response(ZERO_OID), packfile_response(build_pack([entry(BF.OBJ_TREE, payload)])),
        ])
        self.assert_quota(connection, "isolated-store disk use", store_disk=3 * MIB)

    def test_store_disk_quota_reserves_pack_index(self) -> None:
        pack = build_pack([], count=100_000)
        connection = FakeConnection([ls_refs_response(ZERO_OID), packfile_response(pack)])
        self.assert_quota(connection, "isolated-store disk use", store_disk=3 * MIB)

    # Mandatory evidence protections on the bounded path.

    def test_rejects_blob_bodies_and_unexpected_objects(self) -> None:
        for kind, message in ((BF.OBJ_BLOB, "blob body"), (BF.OBJ_TAG, "unexpected object type")):
            with self.subTest(kind=kind):
                connection = FakeConnection([
                    ls_refs_response(ZERO_OID), packfile_response(build_pack([entry(kind, b"data")])),
                ])
                self.fake_fetch(connection)
                self.assertNotIsInstance(self.exception, BF.QuotaExceeded)
                self.assertIn(message, str(self.exception))

    def test_rejects_entries_inflating_beyond_declared_size(self) -> None:
        lying = entry(BF.OBJ_TREE, b"y" * 4096, declared=16)
        connection = FakeConnection([ls_refs_response(ZERO_OID), packfile_response(build_pack([lying]))])
        self.fake_fetch(connection)
        self.assertIn("beyond its declared size", str(self.exception))

    def test_rejects_corrupted_pack_checksum(self) -> None:
        pack = bytearray(build_pack([entry(BF.OBJ_TREE, b"")]))
        pack[-1] ^= 0xFF
        connection = FakeConnection([ls_refs_response(ZERO_OID), packfile_response(bytes(pack))])
        self.fake_fetch(connection)
        self.assertIn("checksum", str(self.exception))

    def test_rejects_missing_advertised_ref(self) -> None:
        connection = FakeConnection([ls_refs_response(ZERO_OID, "refs/heads/other")])
        self.fake_fetch(connection)
        self.assertIn("did not advertise refs/heads/main", str(self.exception))

    def test_failed_bounded_fetch_never_downgrades_to_git_fetch(self) -> None:
        commands: list[list[str]] = []
        real_run = subprocess.run
        real_popen = subprocess.Popen

        def record_run(arguments: list[str], *args: object, **kwargs: object) -> object:
            commands.append(list(arguments))
            return real_run(arguments, *args, **kwargs)

        def record_popen(arguments: list[str], *args: object, **kwargs: object) -> object:
            commands.append(list(arguments))
            return real_popen(arguments, *args, **kwargs)

        store = self.root / "store"
        with mock.patch.object(BF.subprocess, "run", record_run), \
                mock.patch.object(BF.subprocess, "Popen", record_popen):
            with self.assertRaises(BF.QuotaExceeded):
                BF.fetch(
                    self.url, store, ["refs/heads/main:refs/x"], [],
                    limits=BF.Limits(expanded_objects=64),
                )
        self.assertFalse(store.exists())
        self.assertTrue(any("upload-pack" in command for command in commands))
        for command in commands:
            self.assertNotIn("fetch", command)
            self.assertNotIn("clone", command)

    def test_cli_exit_codes_distinguish_quota_access_and_failure(self) -> None:
        arguments = ["bounded_fetch.py", "fetch", "--remote-url", FAKE_URL,
                     "--store", str(self.root / "store"), "--ref", "refs/heads/main:refs/x"]
        for error, code in (
            (BF.QuotaExceeded("limit"), BF.EXIT_QUOTA),
            (BF.AccessError("denied"), BF.EXIT_ACCESS),
            (BF.FetchError("broken"), BF.EXIT_FAILURE),
        ):
            with self.subTest(code=code), mock.patch.object(sys, "argv", arguments), \
                    mock.patch.object(BF, "fetch", side_effect=error), \
                    redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    BF.main()
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(stdout.getvalue(), "")

    def test_git_environment_removes_repository_overrides(self) -> None:
        overrides = {
            "GIT_DIR": "/elsewhere", "GIT_OBJECT_DIRECTORY": "/objects",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/alternates", "GIT_EXEC_PATH": "/exec",
            "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": "/hooks", "GIT_CONFIG_GLOBAL": "/config",
            "GIT_PROTOCOL": "version=0",
        }
        with mock.patch.dict(os.environ, overrides):
            environment = BF.git_environment()
        for key in overrides:
            self.assertNotIn(key, environment)
        self.assertEqual(environment["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(environment["GIT_NO_REPLACE_OBJECTS"], "1")
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")


if __name__ == "__main__":
    unittest.main()
