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

from result_processing import (
    REDACTION_MARKER,
    RESULT_MAX_UTF8_BYTES,
    ResultError as CacheError,
    process_result_body,
    redact_result_body,
    sanitize_result_object,
    validate_allowed_categories,
    validate_checklist,
    validate_hml,
    validate_repo_path,
    validate_result_object,
)

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
MAX_SCOPE_STATES = 64
CACHE_RECORD_MAX_UTF8_BYTES = 524_288
MAX_ITERATIONS = 3
SYNTHESIS_PROTOCOL_VERSION = 1
MAX_SYNTHESIS_CHUNKS_PER_AGENT = 16
_MISSING_JSON = object()
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
    "blocking_policy",
    "checklist_hash",
    "references_hash",
    "scoped_prompt_hash",
    "dependencies_complete",
    "dependencies",
}
OPTIONAL_KEY_FIELDS = {"synthesis"}
GLOBAL_BLOCKING_ORDER = ("HIGH", "MEDIUM", "LOW", "CHECKLIST_FAIL")
SCHEMA_BLOCKING_ORDER = {
    "hml": ("HIGH", "MEDIUM", "LOW"),
    "checklist": ("fail",),
}
BUILTIN_DEFAULT_BLOCKING = {
    "hml": ("HIGH", "MEDIUM"),
    "checklist": ("fail",),
}


def fail(message: str, code: int = 2) -> None:
    print(f"cache error: {message}", file=sys.stderr)
    raise SystemExit(code)


def read_bounded_text(
    path: Path,
    max_utf8_bytes: int,
    label: str,
) -> str:
    try:
        with path.open("rb") as handle:
            data = handle.read(max_utf8_bytes + 1)
    except FileNotFoundError as exc:
        raise CacheError(f"cannot read {label} from {path}: {exc}") from exc
    except OSError as exc:
        raise CacheError(f"cannot read {label} from {path}: {exc}") from exc
    if len(data) > max_utf8_bytes:
        raise CacheError(f"{label} exceeds the {max_utf8_bytes}-byte limit: {path}")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CacheError(f"cannot read UTF-8 {label} from {path}: {exc}") from exc


def read_json(path: Path, *, missing_ok: bool = False) -> Any:
    try:
        with path.open("rb") as handle:
            data = handle.read(CACHE_RECORD_MAX_UTF8_BYTES + 1)
    except FileNotFoundError as exc:
        if missing_ok:
            return _MISSING_JSON
        raise CacheError(f"cannot read valid JSON from {path}: {exc}") from exc
    except OSError as exc:
        raise CacheError(f"cannot read valid JSON from {path}: {exc}") from exc
    if len(data) > CACHE_RECORD_MAX_UTF8_BYTES:
        raise CacheError(
            f"JSON input exceeds the {CACHE_RECORD_MAX_UTF8_BYTES}-byte limit: {path}"
        )
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CacheError(f"cannot read valid JSON from {path}: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    try:
        return rendered.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CacheError("JSON values must contain valid Unicode scalar values") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate_agent(agent: str) -> None:
    if not isinstance(agent, str) or not AGENT_RE.fullmatch(agent):
        raise CacheError("agent must use lowercase letters, digits, and interior hyphens")


def validate_hash(value: str, name: str) -> None:
    if not isinstance(value, str) or not HEX_RE.fullmatch(value):
        raise CacheError(f"{name} must be a lowercase SHA-256 hex digest")


def normalize_global_blocking(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        raise CacheError("global blocking_levels must be an array")
    if any(not isinstance(value, str) for value in values):
        raise CacheError("global blocking_levels must contain only strings")
    if len(values) != len(set(values)):
        raise CacheError("global blocking_levels cannot contain duplicates")
    unknown = sorted(set(values) - set(GLOBAL_BLOCKING_ORDER))
    if unknown:
        raise CacheError(f"unsupported global blocking level: {', '.join(unknown)}")
    return tuple(value for value in GLOBAL_BLOCKING_ORDER if value in values)


def normalize_schema_blocking(schema: str, values: Any) -> tuple[str, ...]:
    if schema not in SCHEMA_BLOCKING_ORDER:
        raise CacheError(f"unsupported result schema: {schema}")
    if not isinstance(values, list):
        raise CacheError("agent blocking policy must be an array")
    if any(not isinstance(value, str) for value in values):
        raise CacheError("agent blocking policy must contain only strings")
    if len(values) != len(set(values)):
        raise CacheError("agent blocking policy cannot contain duplicates")
    allowed = SCHEMA_BLOCKING_ORDER[schema]
    unknown = sorted(set(values) - set(allowed))
    if unknown:
        raise CacheError(
            f"blocking policy values do not belong to {schema}: {', '.join(unknown)}"
        )
    return tuple(value for value in allowed if value in values)


def validate_manifest_blocking(values: Any) -> None:
    if not isinstance(values, list):
        raise CacheError("blocking_policy must be an array")
    if any(not isinstance(value, str) for value in values):
        raise CacheError("blocking_policy must contain only strings")
    if len(values) != len(set(values)):
        raise CacheError("blocking_policy cannot contain duplicates")
    allowed = set(SCHEMA_BLOCKING_ORDER["hml"]) | set(
        SCHEMA_BLOCKING_ORDER["checklist"]
    )
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise CacheError(f"unsupported blocking_policy value: {', '.join(unknown)}")
    if "fail" in values and len(values) != 1:
        raise CacheError("blocking_policy cannot mix H/M/L and checklist values")
    canonical = [
        value for value in (*SCHEMA_BLOCKING_ORDER["hml"], "fail") if value in values
    ]
    if values != canonical:
        raise CacheError("blocking_policy must use canonical severity order")


def global_policy_for_schema(schema: str, global_values: Any) -> tuple[str, ...]:
    normalized = normalize_global_blocking(global_values)
    if schema == "hml":
        return tuple(
            value for value in SCHEMA_BLOCKING_ORDER["hml"] if value in normalized
        )
    if schema == "checklist":
        return ("fail",) if "CHECKLIST_FAIL" in normalized else ()
    raise CacheError(f"unsupported result schema: {schema}")


def effective_blocking_policy(
    schema: str,
    global_values: Any,
    declared_values: Any,
    *,
    built_in: bool,
) -> tuple[str, ...]:
    declared = normalize_schema_blocking(schema, declared_values)
    global_policy = global_policy_for_schema(schema, global_values)
    if built_in:
        if declared != BUILTIN_DEFAULT_BLOCKING[schema]:
            raise CacheError("built-in blocking policy contradicts the package default")
        return global_policy
    return tuple(
        value
        for value in SCHEMA_BLOCKING_ORDER[schema]
        if value in declared and value in global_policy
    )


def classify_result(
    schema: str,
    counts: dict[str, int],
    blocking_policy: Any,
    *,
    dependencies_complete: bool,
) -> str:
    policy = normalize_schema_blocking(schema, blocking_policy)
    if schema == "hml":
        count_names = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
        blocking = any(counts[count_names[value]] for value in policy)
    else:
        blocking = "fail" in policy and bool(counts["fail"])
    if blocking:
        return "blocking"
    return "nonblocking" if dependencies_complete else "incomplete"


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
    rendered = json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    try:
        rendered_bytes = rendered.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CacheError("cache records must contain valid Unicode scalar values") from exc
    if len(rendered_bytes) > CACHE_RECORD_MAX_UTF8_BYTES:
        raise CacheError(
            f"cache record exceeds the {CACHE_RECORD_MAX_UTF8_BYTES}-byte limit: {path}"
        )
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    except OSError as exc:
        raise CacheError(f"cannot prepare atomic write for {path}: {exc}") from exc
    temp_path = Path(temp_name)
    try:
        set_private_descriptor_mode(descriptor)
        handle = os.fdopen(descriptor, "wb")
        descriptor = -1
        with handle:
            handle.write(rendered_bytes)
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
    extra = sorted(value.keys() - KEY_FIELDS - OPTIONAL_KEY_FIELDS)
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
    validate_manifest_blocking(value["blocking_policy"])
    synthesis = value.get("synthesis", _MISSING_JSON)
    if synthesis is not _MISSING_JSON:
        validate_synthesis_identity(synthesis)
    if not isinstance(value["dependencies_complete"], bool):
        raise CacheError("dependencies_complete must be boolean")
    if synthesis is not _MISSING_JSON and not value["dependencies_complete"]:
        raise CacheError("synthesized cache identity requires complete dependencies")
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


def validate_synthesis_identity(value: Any) -> dict[str, Any]:
    required = {
        "required",
        "protocol_version",
        "prompt_hash",
        "schema_hash",
        "input_hash",
        "chunks",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise CacheError("synthesis identity has invalid fields")
    if not isinstance(value["required"], bool):
        raise CacheError("synthesis required must be boolean")
    protocol_version = value["protocol_version"]
    if isinstance(protocol_version, bool) or not isinstance(protocol_version, int):
        raise CacheError("synthesis protocol_version must be an integer")
    chunks = value["chunks"]
    if not isinstance(chunks, list):
        raise CacheError("synthesis chunks must be an array")

    if not value["required"]:
        raise CacheError("single-chunk cache identities must omit synthesis")

    if protocol_version != SYNTHESIS_PROTOCOL_VERSION:
        raise CacheError(f"unsupported synthesis protocol {protocol_version!r}")
    for name in ("prompt_hash", "schema_hash", "input_hash"):
        validate_hash(value[name], f"synthesis {name}")
    if not 2 <= len(chunks) <= MAX_SYNTHESIS_CHUNKS_PER_AGENT:
        raise CacheError(
            "synthesis chunks must contain between 2 and "
            f"{MAX_SYNTHESIS_CHUNKS_PER_AGENT} identities"
        )
    seen: set[str] = set()
    for chunk in chunks:
        if not isinstance(chunk, dict) or set(chunk) != {"chunk_id", "handoff_hash"}:
            raise CacheError("each synthesis chunk must contain only chunk_id and handoff_hash")
        validate_hash(chunk["chunk_id"], "synthesis chunk_id")
        validate_hash(chunk["handoff_hash"], "synthesis handoff_hash")
        if chunk["chunk_id"] in seen:
            raise CacheError(f"duplicate synthesis chunk identity: {chunk['chunk_id']}")
        seen.add(chunk["chunk_id"])
    return value


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
    text = read_bounded_text(Path(args.file), RESULT_MAX_UTF8_BYTES, "result")
    allowed_categories = validate_allowed_categories(args.schema, args.allowed_category)
    _, counts = process_result_body(
        text,
        args.schema,
        allowed_categories=allowed_categories,
    )
    print(json.dumps({"schema": args.schema, "counts": counts}, sort_keys=True))


def command_store(args: argparse.Namespace) -> None:
    validate_agent(args.agent)
    validate_hash(args.key, "key")
    if (
        isinstance(args.iteration, bool)
        or not isinstance(args.iteration, int)
        or not 1 <= args.iteration <= MAX_ITERATIONS
    ):
        raise CacheError(f"iteration must be between 1 and {MAX_ITERATIONS}")
    result, counts = sanitize_result_object(read_json(Path(args.result)), args.schema)
    manifest = validate_key_manifest(read_json(Path(args.manifest)))
    if manifest["agent"] != args.agent:
        raise CacheError("record agent does not match key manifest agent")
    manifest_key = sha256_bytes(canonical_bytes(manifest))
    if manifest_key != args.key:
        raise CacheError("record key does not match canonical key manifest")
    classification = classify_result(
        args.schema,
        counts,
        manifest["blocking_policy"],
        dependencies_complete=manifest["dependencies_complete"],
    )
    requested_classification = getattr(args, "classification", None)
    if requested_classification is not None and requested_classification != classification:
        raise CacheError(
            f"classification must be {classification} under the effective blocking policy"
        )
    cache_dir = safe_cache_dir(args.repo_root, args.cache_dir, create=True)
    record = {
        "schema_version": SCHEMA_VERSION,
        "agent": args.agent,
        "key": args.key,
        "classification": classification,
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
    if (
        isinstance(record["iteration"], bool)
        or not isinstance(record["iteration"], int)
        or not 1 <= record["iteration"] <= MAX_ITERATIONS
    ):
        raise CacheError("cached agent record has invalid iteration")
    if record["schema"] not in {"hml", "checklist"}:
        raise CacheError("cached agent record has invalid schema")
    manifest = validate_key_manifest(record["manifest"])
    if manifest["agent"] != expected_agent or sha256_bytes(canonical_bytes(manifest)) != record["key"]:
        raise CacheError("cached key manifest does not match record identity")
    result, counts = sanitize_result_object(record["result"], record["schema"])
    expected_classification = classify_result(
        record["schema"],
        counts,
        manifest["blocking_policy"],
        dependencies_complete=manifest["dependencies_complete"],
    )
    if record["classification"] != expected_classification:
        raise CacheError(
            "cached agent record classification disagrees with its blocking policy"
        )
    if not isinstance(record["stored_at"], str) or not record["stored_at"]:
        raise CacheError("cached agent record has invalid timestamp")
    sanitized_record = dict(record)
    sanitized_record["result"] = result
    return sanitized_record


def read_agent_record(args: argparse.Namespace) -> dict[str, Any]:
    validate_agent(args.agent)
    cache_dir = safe_cache_dir(args.repo_root, args.cache_dir)
    record_path = cache_dir / "agents" / f"{args.agent}.json"
    record = read_json(record_path, missing_ok=True)
    if record is _MISSING_JSON:
        raise SystemExit(3)
    return validate_cached_record(record, args.agent)


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
    if (
        isinstance(value["iteration"], bool)
        or not isinstance(value["iteration"], int)
        or not 1 <= value["iteration"] <= MAX_ITERATIONS
    ):
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
    value = read_json(state_path, missing_ok=True)
    if value is _MISSING_JSON:
        return {}
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
                and prior["iteration"] == MAX_ITERATIONS
                and prior["status"] in {"blocked", "incomplete"}
            )
            if args.start_new_sequence:
                if not exhausted_sequence:
                    raise CacheError(
                        f"new sequence requires a terminal iteration-{MAX_ITERATIONS} review"
                    )
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
            if iteration > MAX_ITERATIONS:
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
                and (
                    item[1]["status"] == "ready"
                    or item[1]["iteration"] == MAX_ITERATIONS
                )
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
    try:
        shutil.rmtree(cache_dir)
    except FileNotFoundError:
        pass
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
    result_parser.add_argument(
        "--allowed-category",
        action="append",
        help="permitted namespaced language-rule category; repeat for every enabled rule",
    )
    result_parser.set_defaults(handler=command_validate_result)

    for name, handler in (("store", command_store), ("lookup", command_lookup), ("probe", command_probe)):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--repo-root", default=".")
        subparser.add_argument("--cache-dir", default=".deep-review-cache")
        subparser.add_argument("--agent", required=True)
        if name != "probe":
            subparser.add_argument("--key", required=True)
        if name == "store":
            subparser.add_argument(
                "--classification",
                choices=("nonblocking", "blocking", "incomplete"),
                help="optional assertion; classification is derived from the effective policy",
            )
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
        help=f"start iteration 1 after a changed terminal iteration-{MAX_ITERATIONS} review",
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
