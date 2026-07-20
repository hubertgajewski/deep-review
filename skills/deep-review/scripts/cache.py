#!/usr/bin/env python3
"""Bounded, repository-local cache and result validator for deep-review."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any

try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    _fcntl = None

try:
    import msvcrt as _msvcrt
except ImportError:  # pragma: no cover - exercised on POSIX
    _msvcrt = None


SCHEMA_VERSION = 1
AGENT_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
HML_SUMMARY_RE = re.compile(r"^summary: (\d+) high / (\d+) medium / (\d+) low$")
CHECK_SUMMARY_RE = re.compile(r"^summary: (\d+) pass / (\d+) fail / (\d+) N/A$")
CHECK_ITEM_RE = re.compile(r"^- \[(pass|fail|N/A)\] ([^:]+): (.+)$")
CHECK_FAILURE_RE = re.compile(r"^([1-9]\d*)\. (.+):([1-9]\d*) (.+)$")
MAX_SCOPE_STATES = 64
KEY_FIELDS = {
    "schema_version",
    "agent",
    "provider",
    "host",
    "repository",
    "change_number",
    "base_identity",
    "head_identity",
    "mode",
    "scope_hash",
    "description_hash",
    "orchestrator_hash",
    "agent_prompt_hash",
    "config_hash",
    "checklist_hash",
    "references_hash",
    "scoped_prompt_hash",
    "dependencies_complete",
    "dependencies",
}


class CacheError(Exception):
    pass


def fail(message: str, code: int = 2) -> None:
    print(f"cache error: {message}", file=sys.stderr)
    raise SystemExit(code)


def read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise CacheError(f"cannot read valid JSON from {path}: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate_agent(agent: str) -> None:
    if not isinstance(agent, str) or not AGENT_RE.fullmatch(agent):
        raise CacheError("agent must use lowercase letters, digits, and interior hyphens")


def validate_hash(value: str, name: str) -> None:
    if not isinstance(value, str) or not HEX_RE.fullmatch(value):
        raise CacheError(f"{name} must be a lowercase SHA-256 hex digest")


def validate_repo_path(value: str, name: str) -> None:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise CacheError(f"{name} must remain repository-relative")


def set_private_descriptor_mode(descriptor: int) -> None:
    fchmod = getattr(os, "fchmod", None)
    if callable(fchmod):
        fchmod(descriptor, 0o600)


def safe_cache_dir(repo_root_arg: str, cache_dir_arg: str, create: bool = False) -> Path:
    try:
        root = Path(repo_root_arg).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CacheError(f"cannot resolve repository root: {exc}") from exc
    if not root.is_dir():
        raise CacheError("repository root is not a directory")
    raw = Path(cache_dir_arg).expanduser()
    if ".." in raw.parts:
        raise CacheError("cache directory cannot contain parent traversal")
    if raw.is_absolute():
        try:
            lexical_relative = raw.relative_to(root)
        except ValueError as exc:
            raise CacheError("cache directory must remain inside the repository") from exc
    else:
        lexical_relative = raw
    if not lexical_relative.parts:
        raise CacheError("cache directory cannot be the repository root")
    current = root
    for part in lexical_relative.parts:
        current = current / part
        if current.is_symlink():
            raise CacheError("cache path cannot contain symlinks")
    candidate = root / lexical_relative
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise CacheError(f"cannot resolve cache directory: {exc}") from exc
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise CacheError("cache directory must remain inside the repository") from exc
    if not relative.parts:
        raise CacheError("cache directory cannot be the repository root")
    if create:
        try:
            resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(resolved, 0o700)
        except OSError as exc:
            raise CacheError(f"cannot create writable cache directory {resolved}: {exc}") from exc
        if not os.access(resolved, os.W_OK):
            raise CacheError(f"cache directory is not writable: {resolved}")
    return resolved


def atomic_write(path: Path, value: Any) -> None:
    if path.parent.is_symlink():
        raise CacheError(f"atomic write parent cannot be a symlink: {path.parent}")
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    except OSError as exc:
        raise CacheError(f"cannot prepare atomic write for {path}: {exc}") from exc
    temp_path = Path(temp_name)
    try:
        set_private_descriptor_mode(descriptor)
        handle = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = -1
        with handle:
            json.dump(value, handle, sort_keys=True, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError as exc:
        raise CacheError(f"cannot atomically write {path}: {exc}") from exc
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def cache_lock(cache_dir: Path, name: str):
    validate_agent(name)
    lock_dir = cache_dir / "locks"
    lock_path = lock_dir / f"{name}.lock"
    try:
        lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if lock_dir.is_symlink() or lock_path.is_symlink():
            raise CacheError("cache lock path cannot contain symlinks")
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(lock_path, flags, 0o600)
        set_private_descriptor_mode(descriptor)
    except OSError as exc:
        raise CacheError(f"cannot open cache lock {lock_path}: {exc}") from exc
    try:
        if _fcntl is not None:
            _fcntl.flock(descriptor, _fcntl.LOCK_EX)
        elif _msvcrt is not None:
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            _msvcrt.locking(descriptor, _msvcrt.LK_LOCK, 1)
        else:
            raise CacheError("no supported cache lock backend is available")
        yield
    except OSError as exc:
        raise CacheError(f"cannot lock cache state {lock_path}: {exc}") from exc
    finally:
        try:
            if _fcntl is not None:
                _fcntl.flock(descriptor, _fcntl.LOCK_UN)
            elif _msvcrt is not None:
                os.lseek(descriptor, 0, os.SEEK_SET)
                _msvcrt.locking(descriptor, _msvcrt.LK_UNLCK, 1)
        finally:
            os.close(descriptor)


def validate_key_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CacheError("key manifest must be a JSON object")
    missing = sorted(KEY_FIELDS - value.keys())
    extra = sorted(value.keys() - KEY_FIELDS)
    if missing:
        raise CacheError(f"key manifest missing fields: {', '.join(missing)}")
    if extra:
        raise CacheError(f"key manifest has unknown fields: {', '.join(extra)}")
    if value["schema_version"] != SCHEMA_VERSION:
        raise CacheError(f"unsupported key schema {value['schema_version']!r}")
    validate_agent(value["agent"])
    for name in (
        "provider", "host", "repository", "change_number", "base_identity", "head_identity", "mode"
    ):
        if not isinstance(value[name], str):
            raise CacheError(f"{name} must be a string")
    if not value["repository"] or not value["base_identity"] or not value["head_identity"] or not value["mode"]:
        raise CacheError("repository, base_identity, head_identity, and mode cannot be empty")
    for name in (
        "scope_hash",
        "description_hash",
        "orchestrator_hash",
        "agent_prompt_hash",
        "config_hash",
        "checklist_hash",
        "references_hash",
        "scoped_prompt_hash",
    ):
        validate_hash(value[name], name)
    if not isinstance(value["dependencies_complete"], bool):
        raise CacheError("dependencies_complete must be boolean")
    dependencies = value["dependencies"]
    if not isinstance(dependencies, list):
        raise CacheError("dependencies must be an array")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for dependency in dependencies:
        if not isinstance(dependency, dict) or set(dependency) != {"path", "hash"}:
            raise CacheError("each dependency must contain only path and hash")
        path = dependency["path"]
        if not isinstance(path, str):
            raise CacheError("dependency paths must be strings")
        validate_repo_path(path, "dependency path")
        if path in seen:
            raise CacheError(f"duplicate dependency path: {path}")
        validate_hash(dependency["hash"], f"dependency hash for {path}")
        seen.add(path)
        normalized.append({"path": path, "hash": dependency["hash"]})
    if normalized != sorted(normalized, key=lambda item: item["path"]):
        raise CacheError("dependencies must be sorted by path")
    return value


def validate_hml(text: str) -> dict[str, int]:
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    summaries = [(index, HML_SUMMARY_RE.fullmatch(line)) for index, line in enumerate(lines)]
    summaries = [(index, match) for index, match in summaries if match]
    if len(summaries) != 1:
        raise CacheError("H/M/L result must contain exactly one valid summary")
    summary_index, summary_match = summaries[0]
    assert summary_match is not None
    if summary_index != len(lines) - 1:
        raise CacheError("H/M/L summary must be the final non-empty line")
    body = lines[:summary_index]
    if not body:
        raise CacheError("H/M/L result must contain findings or the exact empty sentinel")
    counts = {"high": 0, "medium": 0, "low": 0}
    if body == ["findings: none"]:
        pass
    else:
        for line in body:
            if line.count(" | ") != 4:
                raise CacheError(f"invalid H/M/L field separators: {line}")
            fields = line.split(" | ")
            if len(fields) != 5 or fields[0] not in {"HIGH", "MEDIUM", "LOW"}:
                raise CacheError(f"invalid H/M/L finding line: {line}")
            if not fields[1] or not fields[2] or not fields[3] or not fields[4]:
                raise CacheError("H/M/L finding fields cannot be empty")
            if any(re.search(r"(?<!\\)\|", field) for field in fields):
                raise CacheError("literal pipes in H/M/L fields must be escaped as \\|")
            location = re.fullmatch(r"(.+):([1-9]\d*)", fields[2])
            if not location:
                raise CacheError("H/M/L locations must use repository-relative file:line")
            finding_path = location.group(1)
            validate_repo_path(finding_path, "H/M/L location")
            counts[fields[0].lower()] += 1
    expected = tuple(int(summary_match.group(index)) for index in range(1, 4))
    actual = (counts["high"], counts["medium"], counts["low"])
    if actual != expected:
        raise CacheError(f"H/M/L summary drift: body={actual}, summary={expected}")
    return counts


def validate_checklist(text: str) -> dict[str, int]:
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    summary_entries = [(index, CHECK_SUMMARY_RE.fullmatch(line)) for index, line in enumerate(lines)]
    summary_entries = [(index, match) for index, match in summary_entries if match]
    if len(summary_entries) != 1:
        raise CacheError("checklist result must contain exactly one valid summary")
    summary_index, summary_match = summary_entries[0]
    assert summary_match is not None
    counts = {"pass": 0, "fail": 0, "N/A": 0}
    for line in lines[:summary_index]:
        match = CHECK_ITEM_RE.fullmatch(line)
        if not match:
            raise CacheError(f"invalid checklist line: {line}")
        counts[match.group(1)] += 1
    expected = tuple(int(summary_match.group(index)) for index in range(1, 4))
    actual = (counts["pass"], counts["fail"], counts["N/A"])
    if actual != expected:
        raise CacheError(f"checklist summary drift: body={actual}, summary={expected}")
    tail = lines[summary_index + 1 :]
    if counts["fail"] == 0:
        if tail != ["Failures: none."]:
            raise CacheError("passing checklist must end with exact empty sentinel")
    else:
        if not tail or tail[0] != "Failures (in order of priority):":
            raise CacheError("failing checklist must include prioritized failures")
        actions = tail[1:]
        if len(actions) != counts["fail"]:
            raise CacheError("checklist must contain exactly one action per failed item")
        for expected_number, line in enumerate(actions, 1):
            action = CHECK_FAILURE_RE.fullmatch(line)
            if not action or int(action.group(1)) != expected_number:
                raise CacheError("prioritized failures must be consecutively numbered file:line actions")
            validate_repo_path(action.group(2), "checklist failure location")
    return counts


def validate_result_object(result: Any, schema: str) -> dict[str, int]:
    if not isinstance(result, dict) or set(result) != {"body", "summary"}:
        raise CacheError("result JSON must contain only body and summary")
    if not isinstance(result["body"], str) or not isinstance(result["summary"], dict):
        raise CacheError("result body must be text and summary must be an object")
    counts = validate_hml(result["body"]) if schema == "hml" else validate_checklist(result["body"])
    if result["summary"] != counts:
        raise CacheError("result summary object does not match validated body counts")
    return counts


def command_hash(args: argparse.Namespace) -> None:
    try:
        data = Path(args.file).read_bytes()
    except OSError as exc:
        raise CacheError(f"cannot read {args.file}: {exc}") from exc
    print(sha256_bytes(data))


def command_key(args: argparse.Namespace) -> None:
    manifest = validate_key_manifest(read_json(Path(args.manifest)))
    print(sha256_bytes(canonical_bytes(manifest)))


def command_validate_result(args: argparse.Namespace) -> None:
    try:
        text = Path(args.file).read_text(encoding="utf-8")
    except OSError as exc:
        raise CacheError(f"cannot read {args.file}: {exc}") from exc
    counts = validate_hml(text) if args.schema == "hml" else validate_checklist(text)
    print(json.dumps({"schema": args.schema, "counts": counts}, sort_keys=True))


def command_store(args: argparse.Namespace) -> None:
    validate_agent(args.agent)
    validate_hash(args.key, "key")
    if not 1 <= args.iteration <= 3:
        raise CacheError("iteration must be between 1 and 3")
    result = read_json(Path(args.result))
    validate_result_object(result, args.schema)
    manifest = validate_key_manifest(read_json(Path(args.manifest)))
    if manifest["agent"] != args.agent:
        raise CacheError("record agent does not match key manifest agent")
    manifest_key = sha256_bytes(canonical_bytes(manifest))
    if manifest_key != args.key:
        raise CacheError("record key does not match canonical key manifest")
    cache_dir = safe_cache_dir(args.repo_root, args.cache_dir, create=True)
    record = {
        "schema_version": SCHEMA_VERSION,
        "agent": args.agent,
        "key": args.key,
        "classification": args.classification,
        "iteration": args.iteration,
        "schema": args.schema,
        "manifest": manifest,
        "result": result,
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write(cache_dir / "agents" / f"{args.agent}.json", record)
    print(json.dumps(record, sort_keys=True))


def validate_cached_record(record: Any, expected_agent: str) -> dict[str, Any]:
    required = {
        "schema_version", "agent", "key", "classification", "iteration", "schema", "manifest", "result", "stored_at"
    }
    if not isinstance(record, dict) or set(record) != required:
        raise CacheError("cached agent record has invalid fields")
    if record["schema_version"] != SCHEMA_VERSION or record["agent"] != expected_agent:
        raise CacheError("cached agent record has invalid identity")
    validate_hash(record["key"], "cached key")
    if record["classification"] not in {"nonblocking", "blocking", "incomplete"}:
        raise CacheError("cached agent record has invalid classification")
    if not isinstance(record["iteration"], int) or not 1 <= record["iteration"] <= 3:
        raise CacheError("cached agent record has invalid iteration")
    if record["schema"] not in {"hml", "checklist"}:
        raise CacheError("cached agent record has invalid schema")
    manifest = validate_key_manifest(record["manifest"])
    if manifest["agent"] != expected_agent or sha256_bytes(canonical_bytes(manifest)) != record["key"]:
        raise CacheError("cached key manifest does not match record identity")
    validate_result_object(record["result"], record["schema"])
    if not isinstance(record["stored_at"], str) or not record["stored_at"]:
        raise CacheError("cached agent record has invalid timestamp")
    return record


def read_agent_record(args: argparse.Namespace) -> dict[str, Any]:
    validate_agent(args.agent)
    cache_dir = safe_cache_dir(args.repo_root, args.cache_dir)
    record_path = cache_dir / "agents" / f"{args.agent}.json"
    if not record_path.is_file():
        raise SystemExit(3)
    return validate_cached_record(read_json(record_path), args.agent)


def command_probe(args: argparse.Namespace) -> None:
    record = read_agent_record(args)
    print(json.dumps(record["manifest"], sort_keys=True))


def command_lookup(args: argparse.Namespace) -> None:
    validate_hash(args.key, "key")
    record = read_agent_record(args)
    if record["key"] != args.key:
        raise SystemExit(3)
    print(json.dumps(record, sort_keys=True))


def validate_state_record(value: Any) -> dict[str, Any]:
    required = {
        "schema_version", "scope_key", "reviewed_state_hash", "iteration", "status", "reuse_used",
        "targeted_rerun_used", "generation", "updated_at"
    }
    legacy_required = required - {"generation"}
    if isinstance(value, dict) and set(value) == legacy_required:
        value = dict(value)
        value["generation"] = 1
    if not isinstance(value, dict) or set(value) != required:
        raise CacheError("cached convergence state has invalid fields")
    if value["schema_version"] != SCHEMA_VERSION:
        raise CacheError("cached convergence state has unsupported schema")
    validate_hash(value["scope_key"], "cached scope_key")
    validate_hash(value["reviewed_state_hash"], "cached reviewed_state_hash")
    if not isinstance(value["iteration"], int) or not 1 <= value["iteration"] <= 3:
        raise CacheError("cached convergence state has invalid iteration")
    if not isinstance(value["generation"], int) or value["generation"] < 1:
        raise CacheError("cached convergence state has invalid generation")
    if value["status"] not in {"ready", "blocked", "incomplete"}:
        raise CacheError("cached convergence state has invalid status")
    if not isinstance(value["reuse_used"], bool) or not isinstance(value["targeted_rerun_used"], bool):
        raise CacheError("cached convergence state flags must be boolean")
    if not isinstance(value["updated_at"], str) or not value["updated_at"]:
        raise CacheError("cached convergence state has invalid timestamp")
    return value


def read_scope_states(state_path: Path) -> dict[str, dict[str, Any]]:
    if not state_path.is_file():
        return {}
    value = read_json(state_path)
    if isinstance(value, dict) and set(value) == {"schema_version", "states"}:
        if value["schema_version"] != SCHEMA_VERSION or not isinstance(value["states"], dict):
            raise CacheError("cached convergence state store is invalid")
        states: dict[str, dict[str, Any]] = {}
        for scope_key, state in value["states"].items():
            validate_hash(scope_key, "state store scope key")
            validated = validate_state_record(state)
            if validated["scope_key"] != scope_key:
                raise CacheError("state store key does not match record scope")
            states[scope_key] = validated
        if len(states) > MAX_SCOPE_STATES:
            raise CacheError("cached convergence state store exceeds its bounded size")
        return states
    legacy = validate_state_record(value)
    return {legacy["scope_key"]: legacy}


def command_state(args: argparse.Namespace) -> None:
    validate_hash(args.scope_key, "scope_key")
    validate_hash(args.reviewed_state_hash, "reviewed_state_hash")
    cache_dir = safe_cache_dir(args.repo_root, args.cache_dir, create=True)
    state_path = cache_dir / "state.json"
    with cache_lock(cache_dir, "state"):
        states = read_scope_states(state_path)
        prior = states.get(args.scope_key)
        if prior is None and args.expected_generation is not None:
            raise CacheError("new scope state cannot have an expected generation")
        if prior is not None:
            if args.expected_generation is None:
                raise CacheError("existing scope state requires --expected-generation")
            if args.expected_generation != prior["generation"]:
                stage = "final guard" if args.final_guard_run else "review"
                raise CacheError(f"scope state changed during {stage}; rebuild against current state")

        if args.final_guard_run and args.start_new_sequence:
            raise CacheError("final guard cannot start a new convergence sequence")

        if args.final_guard_run:
            if prior is None:
                raise CacheError("final guard requires an existing scope state")
            if args.reviewed_state_hash != prior["reviewed_state_hash"]:
                raise CacheError("reviewed state changed during final guard; rerun the fresh guard")
            iteration = prior["iteration"]
            reuse_used = False
            targeted_rerun_used = False
        else:
            reviewed_state_changed = (
                prior is not None
                and prior["reviewed_state_hash"] != args.reviewed_state_hash
            )
            exhausted_sequence = (
                prior is not None
                and prior["iteration"] == 3
                and prior["status"] in {"blocked", "incomplete"}
            )
            if args.start_new_sequence:
                if not exhausted_sequence:
                    raise CacheError("new sequence requires a terminal iteration-3 review")
                if not reviewed_state_changed:
                    raise CacheError("new sequence requires a changed reviewed state")
            elif exhausted_sequence and reviewed_state_changed:
                raise CacheError(
                    "changed review iteration limit exceeded; a later explicit invocation must use "
                    "--start-new-sequence"
                )
            new_sequence = (
                reviewed_state_changed
                and (prior["status"] == "ready" or args.start_new_sequence)
            )
            if prior is None or new_sequence:
                iteration = 1
            elif prior["reviewed_state_hash"] == args.reviewed_state_hash:
                iteration = prior["iteration"]
            else:
                iteration = prior["iteration"] + 1
            if iteration > 3:
                raise CacheError("changed review iteration limit exceeded")
            carry_prior = prior is not None and not new_sequence
            reuse_used = args.reuse_used or (carry_prior and prior["reuse_used"])
            targeted_rerun_used = args.targeted_rerun_used or (
                carry_prior and prior["targeted_rerun_used"]
            )
        if args.status == "ready" and (reuse_used or targeted_rerun_used):
            raise CacheError("ready state with reuse or targeted reruns requires a successful final guard")
        state = {
            "schema_version": SCHEMA_VERSION,
            "scope_key": args.scope_key,
            "reviewed_state_hash": args.reviewed_state_hash,
            "iteration": iteration,
            "status": args.status,
            "reuse_used": reuse_used,
            "targeted_rerun_used": targeted_rerun_used,
            "generation": 1 if prior is None else prior["generation"] + 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        states[args.scope_key] = state
        if len(states) > MAX_SCOPE_STATES:
            evictable = [
                item
                for item in states.items()
                if item[0] != args.scope_key
                and (item[1]["status"] == "ready" or item[1]["iteration"] == 3)
            ]
            if not evictable:
                raise CacheError("scope state capacity is exhausted by unfinished reviews")
            oldest = min(evictable, key=lambda item: item[1]["updated_at"])
            del states[oldest[0]]
        atomic_write(state_path, {"schema_version": SCHEMA_VERSION, "states": states})
    print(json.dumps(state, sort_keys=True))


def command_state_read(args: argparse.Namespace) -> None:
    cache_dir = safe_cache_dir(args.repo_root, args.cache_dir)
    state_path = cache_dir / "state.json"
    states = read_scope_states(state_path)
    if not states:
        raise SystemExit(3)
    if args.scope_key is not None:
        validate_hash(args.scope_key, "scope_key")
        state = states.get(args.scope_key)
        if state is None:
            raise SystemExit(3)
    elif len(states) == 1:
        state = next(iter(states.values()))
    else:
        raise CacheError("state-read requires --scope-key when multiple scopes are cached")
    print(json.dumps(state, sort_keys=True))


def command_clear(args: argparse.Namespace) -> None:
    cache_dir = safe_cache_dir(args.repo_root, args.cache_dir)
    if cache_dir.exists():
        try:
            shutil.rmtree(cache_dir)
        except OSError as exc:
            raise CacheError(f"cannot clear cache directory {cache_dir}: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    hash_parser = subparsers.add_parser("hash", help="hash a file with SHA-256")
    hash_parser.add_argument("--file", required=True)
    hash_parser.set_defaults(handler=command_hash)

    key_parser = subparsers.add_parser("key", help="validate and hash a canonical key manifest")
    key_parser.add_argument("--manifest", required=True)
    key_parser.set_defaults(handler=command_key)

    result_parser = subparsers.add_parser("validate-result", help="validate an agent result")
    result_parser.add_argument("--schema", choices=("hml", "checklist"), required=True)
    result_parser.add_argument("--file", required=True)
    result_parser.set_defaults(handler=command_validate_result)

    for name, handler in (("store", command_store), ("lookup", command_lookup), ("probe", command_probe)):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--repo-root", default=".")
        subparser.add_argument("--cache-dir", default=".deep-review-cache")
        subparser.add_argument("--agent", required=True)
        if name != "probe":
            subparser.add_argument("--key", required=True)
        if name == "store":
            subparser.add_argument("--classification", choices=("nonblocking", "blocking", "incomplete"), required=True)
            subparser.add_argument("--iteration", type=int, required=True)
            subparser.add_argument("--schema", choices=("hml", "checklist"), required=True)
            subparser.add_argument("--manifest", required=True)
            subparser.add_argument("--result", required=True)
        subparser.set_defaults(handler=handler)

    state_parser = subparsers.add_parser("state", help="advance or retain convergence state")
    state_parser.add_argument("--repo-root", default=".")
    state_parser.add_argument("--cache-dir", default=".deep-review-cache")
    state_parser.add_argument("--scope-key", required=True)
    state_parser.add_argument("--reviewed-state-hash", required=True)
    state_parser.add_argument("--status", choices=("ready", "blocked", "incomplete"), required=True)
    state_parser.add_argument("--reuse-used", action="store_true")
    state_parser.add_argument("--targeted-rerun-used", action="store_true")
    state_parser.add_argument("--final-guard-run", action="store_true")
    state_parser.add_argument(
        "--start-new-sequence",
        action="store_true",
        help="start iteration 1 after a changed terminal iteration-3 review",
    )
    state_parser.add_argument(
        "--expected-generation",
        type=int,
        help="required compare-and-set generation when the scope state already exists",
    )
    state_parser.set_defaults(handler=command_state)

    read_parser = subparsers.add_parser("state-read", help="read convergence state")
    read_parser.add_argument("--repo-root", default=".")
    read_parser.add_argument("--cache-dir", default=".deep-review-cache")
    read_parser.add_argument("--scope-key")
    read_parser.set_defaults(handler=command_state_read)

    clear_parser = subparsers.add_parser("clear", help="remove only the validated cache directory")
    clear_parser.add_argument("--repo-root", default=".")
    clear_parser.add_argument("--cache-dir", default=".deep-review-cache")
    clear_parser.set_defaults(handler=command_clear)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.handler(args)
    except CacheError as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
