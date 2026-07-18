#!/usr/bin/env python3
"""Bounded, repository-local cache and result validator for deep-review."""

from __future__ import annotations

import argparse
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


SCHEMA_VERSION = 1
AGENT_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
HML_SUMMARY_RE = re.compile(r"^summary: (\d+) high / (\d+) medium / (\d+) low$")
CHECK_SUMMARY_RE = re.compile(r"^summary: (\d+) pass / (\d+) fail / (\d+) N/A$")
CHECK_ITEM_RE = re.compile(r"^- \[(pass|fail|N/A)\] ([^:]+): (.+)$")
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
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, sort_keys=True, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        except OSError as exc:
            raise CacheError(f"cannot atomically write {path}: {exc}") from exc
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


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
        if not isinstance(path, str) or not path or path.startswith("/") or ".." in Path(path).parts:
            raise CacheError("dependency paths must be safe repository-relative paths")
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
    counts = {"high": 0, "medium": 0, "low": 0}
    if body == ["findings: none"]:
        pass
    else:
        for line in body:
            fields = line.split(" | ", 4)
            if len(fields) != 5 or fields[0] not in {"HIGH", "MEDIUM", "LOW"}:
                raise CacheError(f"invalid H/M/L finding line: {line}")
            if not fields[1] or not fields[2] or not fields[3] or not fields[4]:
                raise CacheError("H/M/L finding fields cannot be empty")
            location = re.fullmatch(r"(.+):([1-9]\d*)", fields[2])
            if not location:
                raise CacheError("H/M/L locations must use repository-relative file:line")
            finding_path = location.group(1)
            if finding_path.startswith("/") or ".." in Path(finding_path).parts:
                raise CacheError("H/M/L locations must remain repository-relative")
            counts[fields[0].lower()] += 1
    expected = tuple(int(summary_match.group(index)) for index in range(1, 4))
    actual = (counts["high"], counts["medium"], counts["low"])
    if actual != expected:
        raise CacheError(f"H/M/L summary drift: body={actual}, summary={expected}")
    if body == ["findings: none"] and any(actual):
        raise CacheError("empty H/M/L sentinel requires zero counts")
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
        if len(tail) == 1 or any(not re.fullmatch(r"\d+\. .+", line) for line in tail[1:]):
            raise CacheError("prioritized failures must be numbered actions")
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
    if not isinstance(result, dict) or set(result) != {"body", "summary"}:
        raise CacheError("result JSON must contain only body and summary")
    if not isinstance(result["body"], str) or not isinstance(result["summary"], dict):
        raise CacheError("result body must be text and summary must be an object")
    manifest = validate_key_manifest(read_json(Path(args.manifest)))
    if manifest["agent"] != args.agent:
        raise CacheError("record agent does not match key manifest agent")
    manifest_key = sha256_bytes(canonical_bytes(manifest))
    if manifest_key != args.key:
        raise CacheError("record key does not match canonical key manifest")
    counts = validate_hml(result["body"]) if args.schema == "hml" else validate_checklist(result["body"])
    if result["summary"] != counts:
        raise CacheError("result summary object does not match validated body counts")
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
    result = record["result"]
    if not isinstance(result, dict) or set(result) != {"body", "summary"}:
        raise CacheError("cached result has invalid fields")
    if not isinstance(result["body"], str) or not isinstance(result["summary"], dict):
        raise CacheError("cached result body or summary has invalid type")
    counts = validate_hml(result["body"]) if record["schema"] == "hml" else validate_checklist(result["body"])
    if result["summary"] != counts:
        raise CacheError("cached summary does not match validated body counts")
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
        "targeted_rerun_used", "updated_at"
    }
    if not isinstance(value, dict) or set(value) != required:
        raise CacheError("cached convergence state has invalid fields")
    if value["schema_version"] != SCHEMA_VERSION:
        raise CacheError("cached convergence state has unsupported schema")
    validate_hash(value["scope_key"], "cached scope_key")
    validate_hash(value["reviewed_state_hash"], "cached reviewed_state_hash")
    if not isinstance(value["iteration"], int) or not 1 <= value["iteration"] <= 3:
        raise CacheError("cached convergence state has invalid iteration")
    if value["status"] not in {"ready", "blocked", "incomplete"}:
        raise CacheError("cached convergence state has invalid status")
    if not isinstance(value["reuse_used"], bool) or not isinstance(value["targeted_rerun_used"], bool):
        raise CacheError("cached convergence state flags must be boolean")
    if not isinstance(value["updated_at"], str) or not value["updated_at"]:
        raise CacheError("cached convergence state has invalid timestamp")
    return value


def command_state(args: argparse.Namespace) -> None:
    validate_hash(args.scope_key, "scope_key")
    validate_hash(args.reviewed_state_hash, "reviewed_state_hash")
    cache_dir = safe_cache_dir(args.repo_root, args.cache_dir, create=True)
    state_path = cache_dir / "state.json"
    prior: dict[str, Any] | None = None
    if state_path.is_file():
        prior = validate_state_record(read_json(state_path))
    if prior is None or prior.get("scope_key") != args.scope_key:
        iteration = 1
    elif prior.get("reviewed_state_hash") == args.reviewed_state_hash:
        iteration = int(prior.get("iteration", 1))
    else:
        iteration = int(prior.get("iteration", 1)) + 1
    if iteration > 3:
        raise CacheError("changed review iteration limit exceeded")
    state = {
        "schema_version": SCHEMA_VERSION,
        "scope_key": args.scope_key,
        "reviewed_state_hash": args.reviewed_state_hash,
        "iteration": iteration,
        "status": args.status,
        "reuse_used": args.reuse_used,
        "targeted_rerun_used": args.targeted_rerun_used,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write(state_path, state)
    print(json.dumps(state, sort_keys=True))


def command_state_read(args: argparse.Namespace) -> None:
    cache_dir = safe_cache_dir(args.repo_root, args.cache_dir)
    state_path = cache_dir / "state.json"
    if not state_path.is_file():
        raise SystemExit(3)
    print(json.dumps(validate_state_record(read_json(state_path)), sort_keys=True))


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
    state_parser.set_defaults(handler=command_state)

    read_parser = subparsers.add_parser("state-read", help="read convergence state")
    read_parser.add_argument("--repo-root", default=".")
    read_parser.add_argument("--cache-dir", default=".deep-review-cache")
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
