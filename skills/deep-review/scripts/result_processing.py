"""Credential-safe validation for bounded Deep Review result bodies."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import re
from typing import Any


HML_SUMMARY_RE = re.compile(r"^summary: (\d+) high / (\d+) medium / (\d+) low$")
CHECK_SUMMARY_RE = re.compile(r"^summary: (\d+) pass / (\d+) fail / (\d+) N/A$")
CHECK_ITEM_RE = re.compile(r"^- \[(pass|fail|N/A)\] ([^:]+): (.+)$")
CHECK_FAILURE_RE = re.compile(r"^([1-9]\d*)\. (.+):([1-9]\d*) (.+)$")
RULE_ID_RE = re.compile(r"^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$")
REDACTION_MARKER = "[REDACTED CREDENTIAL]"
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?P<label>(?:(?:RSA|EC|DSA|OPENSSH|ENCRYPTED) )?PRIVATE KEY|"
    r"PGP PRIVATE KEY BLOCK)-----"
    r".*?-----END (?P=label)-----",
    re.DOTALL,
)
SENSITIVE_HEADER_RE = re.compile(
    r"((?:\b(?:authorization|(?:set-)?cookie)\s*[:=]\s*|"
    r"['\"](?:authorization|(?:set-)?cookie)['\"]\s*[:=]\s*|"
    r"\[\s*['\"](?:authorization|(?:set-)?cookie)['\"]\s*\]"
    r"\s*[:=]\s*|"
    r"\b(?:setRequestHeader|setHeader|addHeader|header|"
    r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\(\))*\.(?:Set|Add))\s*\(\s*"
    r"['\"](?:authorization|(?:set-)?cookie)['\"]\s*,\s*))[^\r\n]*",
    re.IGNORECASE,
)
NAMED_CREDENTIAL_RE = re.compile(
    r"\b(?P<name>api[_ -]?key|access[_ -]?key|private[_ -]?key|"
    r"access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|"
    r"password|passwd|pwd|token|secret|cookie)\b"
    r"(?P<separator>\s*[:=]\s*)"
    r'(?:(?P<double_quote>")(?P<double_quoted>(?:\\.|[^"\\\r\n])*)"|'
    r"(?P<single_quote>')(?P<single_quoted>(?:\\.|[^'\\\r\n])*)'|"
    rf"(?P<bare>{re.escape(REDACTION_MARKER)}|[^\r\n,;|]+))",
    re.IGNORECASE,
)
WELL_KNOWN_CREDENTIAL_RES = (
    re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{20,255}|"
        r"glpat-[A-Za-z0-9_-]{20,255})\b"
    ),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{6,}\.eyJ[A-Za-z0-9_-]{6,}\."
        r"[A-Za-z0-9_-]{6,}\b"
    ),
)
SAFE_CREDENTIAL_VALUES = {
    "accepted", "configured", "dummy", "empty", "example", "exposed",
    "fake", "hardcoded", "hidden", "invalid", "leaked", "logged",
    "masked", "missing", "nil", "none", "null", "omitted",
    "placeholder", "present", "redacted", "rejected", "required",
    "rotated", "test", "unknown", "unset", "unsafe", "valid",
}
EXPLICIT_REDACTION_MARKERS = {
    REDACTION_MARKER.casefold(),
    "[redacted]",
}
RESULT_MAX_UTF8_BYTES = 12_000


class ResultError(Exception):
    pass


def validate_allowed_categories(
    schema: str, categories: Any
) -> set[str] | None:
    values = categories or []
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ResultError("allowed categories must be strings")
    if values and schema != "hml":
        raise ResultError("allowed categories apply only to H/M/L results")
    if len(values) != len(set(values)):
        raise ResultError("allowed categories cannot contain duplicates")
    if any(not RULE_ID_RE.fullmatch(category) for category in values):
        raise ResultError("invalid namespaced rule category")
    return set(values) if values else None


def validate_repo_path(value: str, name: str) -> None:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ResultError(f"{name} must remain repository-relative")


def credential_value_is_placeholder(value: str) -> bool:
    normalized = value.strip()
    folded = normalized.casefold()
    if not normalized or folded in SAFE_CREDENTIAL_VALUES:
        return True
    if folded in EXPLICIT_REDACTION_MARKERS:
        return True
    if re.fullmatch(
        r"(?:\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*)",
        normalized,
    ):
        return True
    return bool(re.fullmatch(r"[*xX-]{3,}", normalized))


def complete_header_value_is_placeholder(value: str) -> bool:
    normalized = value.strip()
    if normalized[:1] in {"'", '"'}:
        quote = normalized[0]
        end = normalized.find(quote, 1)
        if end != len(normalized) - 1:
            return False
        normalized = normalized[1:end]
    return credential_value_is_placeholder(normalized)


def header_placeholder_end(value: str, *, method_call: bool) -> int | None:
    candidate = value.lstrip()
    leading_whitespace = len(value) - len(candidate)
    if method_call:
        closing = candidate.find(")")
        if closing < 0:
            return None
        expression = candidate[:closing].strip()
        if complete_header_value_is_placeholder(expression):
            return leading_whitespace + closing + 1
        return None
    if candidate[:1] in {"'", '"'}:
        quote = candidate[0]
        end = candidate.find(quote, 1)
        if end < 0:
            return None
        suffix = candidate[end + 1 :].lstrip()
        if suffix and suffix[0] not in ",;.!":
            return None
        if complete_header_value_is_placeholder(candidate[: end + 1]):
            return leading_whitespace + end + 1
        return None
    candidate = candidate.rstrip()
    while candidate[-1:] in {",", ";", ":", ".", "!", "?"}:
        candidate = candidate[:-1].rstrip()
    if complete_header_value_is_placeholder(candidate):
        return len(value)
    return None


def redact_sensitive_text(text: str) -> str:
    redacted = PRIVATE_KEY_RE.sub(REDACTION_MARKER, text)
    pending = redacted
    header_parts: list[str] = []
    while match := SENSITIVE_HEADER_RE.search(pending):
        header_parts.append(pending[: match.start()])
        prefix = match.group(1)
        value = match.group(0)[len(prefix) :]
        placeholder_end = header_placeholder_end(
            value,
            method_call=prefix.rstrip().endswith(","),
        )
        if placeholder_end is not None:
            header_parts.append(f"{prefix}{value[:placeholder_end]}")
            pending = value[placeholder_end:] + pending[match.end() :]
            continue
        header_parts.append(f"{prefix}{REDACTION_MARKER}")
        pending = pending[match.end() :]

    redacted = "".join(header_parts) + pending
    for pattern in WELL_KNOWN_CREDENTIAL_RES:
        redacted = pattern.sub(REDACTION_MARKER, redacted)

    def replace_named(match: re.Match[str]) -> str:
        if match.group("double_quote") is not None:
            value = match.group("double_quoted") or ""
            quote = '"'
        elif match.group("single_quote") is not None:
            value = match.group("single_quoted") or ""
            quote = "'"
        else:
            value = match.group("bare") or ""
            quote = ""
        if credential_value_is_placeholder(value):
            return match.group(0)
        return (
            f"{match.group('name')}{match.group('separator')}"
            f"{quote}{REDACTION_MARKER}{quote}"
        )

    return NAMED_CREDENTIAL_RE.sub(replace_named, redacted)


def reject_sensitive_structural_field(
    value: str, label: str, private_key_sentinel: str
) -> None:
    if private_key_sentinel in value or redact_sensitive_text(value) != value:
        raise ResultError(f"{label} contains a recognized credential")


def map_result_lines(text: str, transform: Callable[[str], str]) -> str:
    transformed: list[str] = []
    for raw_line in text.splitlines(keepends=True):
        content = raw_line.rstrip("\r\n")
        transformed.append(transform(content) + raw_line[len(content) :])
    return "".join(transformed)


def redact_result_body(text: str, schema: str) -> str:
    private_key_sentinel = "\0"
    while private_key_sentinel in text:
        private_key_sentinel += "\0"
    without_private_keys = PRIVATE_KEY_RE.sub(private_key_sentinel, text)

    def redact_field(value: str) -> str:
        return redact_sensitive_text(
            value.replace(private_key_sentinel, REDACTION_MARKER)
        )

    if schema == "hml":
        def redact_hml_line(line: str) -> str:
            if line.count(" | ") != 4:
                return redact_field(line)
            fields = line.split(" | ")
            if len(fields) != 5:
                return redact_field(line)
            reject_sensitive_structural_field(
                fields[1], "H/M/L category", private_key_sentinel
            )
            location = re.fullmatch(r"(.+):([1-9]\d*)", fields[2])
            location_path = location.group(1) if location else fields[2]
            reject_sensitive_structural_field(
                location_path, "H/M/L location", private_key_sentinel
            )
            fields[3] = redact_field(fields[3])
            fields[4] = redact_field(fields[4])
            return " | ".join(fields)

        return map_result_lines(without_private_keys, redact_hml_line)
    if schema == "checklist":
        def redact_checklist_line(line: str) -> str:
            item = CHECK_ITEM_RE.fullmatch(line)
            if item:
                reject_sensitive_structural_field(
                    item.group(2), "checklist item name", private_key_sentinel
                )
                evidence = redact_field(item.group(3))
                return f"- [{item.group(1)}] {item.group(2)}: {evidence}"
            action = CHECK_FAILURE_RE.fullmatch(line)
            if action:
                reject_sensitive_structural_field(
                    action.group(2), "checklist failure location", private_key_sentinel
                )
                return (
                    f"{action.group(1)}. {action.group(2)}:{action.group(3)} "
                    f"{redact_field(action.group(4))}"
                )
            return redact_field(line)

        return map_result_lines(without_private_keys, redact_checklist_line)
    raise ResultError("unsupported result schema")


def validate_hml(
    text: str, allowed_categories: set[str] | None = None
) -> dict[str, int]:
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    summaries = [
        (index, HML_SUMMARY_RE.fullmatch(line)) for index, line in enumerate(lines)
    ]
    summaries = [(index, match) for index, match in summaries if match]
    if len(summaries) != 1:
        raise ResultError("H/M/L result must contain exactly one valid summary")
    summary_index, summary_match = summaries[0]
    assert summary_match is not None
    if summary_index != len(lines) - 1:
        raise ResultError("H/M/L summary must be the final non-empty line")
    body = lines[:summary_index]
    if not body:
        raise ResultError("H/M/L result must contain findings or the exact empty sentinel")
    counts = {"high": 0, "medium": 0, "low": 0}
    if body != ["findings: none"]:
        for line in body:
            if line.count(" | ") != 4:
                raise ResultError("invalid H/M/L field separators")
            fields = line.split(" | ")
            if len(fields) != 5 or fields[0] not in {"HIGH", "MEDIUM", "LOW"}:
                raise ResultError("invalid H/M/L finding line")
            if not all(fields[1:]):
                raise ResultError("H/M/L finding fields cannot be empty")
            if allowed_categories is not None and fields[1] not in allowed_categories:
                raise ResultError("H/M/L category is not enabled for this agent")
            if any(re.search(r"(?<!\\)\|", field) for field in fields):
                raise ResultError("literal pipes in H/M/L fields must be escaped as \\|")
            location = re.fullmatch(r"(.+):([1-9]\d*)", fields[2])
            if not location:
                raise ResultError(
                    "H/M/L locations must use repository-relative file:line"
                )
            validate_repo_path(location.group(1), "H/M/L location")
            counts[fields[0].lower()] += 1
    expected = tuple(int(summary_match.group(index)) for index in range(1, 4))
    actual = (counts["high"], counts["medium"], counts["low"])
    if actual != expected:
        raise ResultError(f"H/M/L summary drift: body={actual}, summary={expected}")
    return counts


def validate_checklist(text: str) -> dict[str, int]:
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    entries = [
        (index, CHECK_SUMMARY_RE.fullmatch(line)) for index, line in enumerate(lines)
    ]
    entries = [(index, match) for index, match in entries if match]
    if len(entries) != 1:
        raise ResultError("checklist result must contain exactly one valid summary")
    summary_index, summary_match = entries[0]
    assert summary_match is not None
    counts = {"pass": 0, "fail": 0, "N/A": 0}
    for line in lines[:summary_index]:
        match = CHECK_ITEM_RE.fullmatch(line)
        if not match:
            raise ResultError("invalid checklist line")
        counts[match.group(1)] += 1
    expected = tuple(int(summary_match.group(index)) for index in range(1, 4))
    actual = (counts["pass"], counts["fail"], counts["N/A"])
    if actual != expected:
        raise ResultError(f"checklist summary drift: body={actual}, summary={expected}")
    tail = lines[summary_index + 1 :]
    if counts["fail"] == 0:
        if tail != ["Failures: none."]:
            raise ResultError("passing checklist must end with exact empty sentinel")
    else:
        if not tail or tail[0] != "Failures (in order of priority):":
            raise ResultError("failing checklist must include prioritized failures")
        actions = tail[1:]
        if len(actions) != counts["fail"]:
            raise ResultError("checklist must contain exactly one action per failed item")
        for expected_number, line in enumerate(actions, 1):
            action = CHECK_FAILURE_RE.fullmatch(line)
            if not action or int(action.group(1)) != expected_number:
                raise ResultError(
                    "prioritized failures must be consecutively numbered file:line actions"
                )
            validate_repo_path(action.group(2), "checklist failure location")
    return counts


def require_bounded_result_body(body: str, label: str) -> None:
    try:
        body_size = len(body.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ResultError(f"{label} must contain valid Unicode scalar values") from exc
    if body_size > RESULT_MAX_UTF8_BYTES:
        raise ResultError(f"{label} exceeds the {RESULT_MAX_UTF8_BYTES}-byte limit")


def process_result_body(
    text: str,
    schema: str,
    allowed_categories: set[str] | None = None,
) -> tuple[str, dict[str, int]]:
    require_bounded_result_body(text, "result body")
    body = redact_result_body(text, schema)
    require_bounded_result_body(body, "redacted result body")
    counts = (
        validate_hml(body, allowed_categories=allowed_categories)
        if schema == "hml"
        else validate_checklist(body)
    )
    return body, counts


def sanitize_result_object(
    result: Any, schema: str
) -> tuple[dict[str, Any], dict[str, int]]:
    if not isinstance(result, dict) or set(result) != {"body", "summary"}:
        raise ResultError("result JSON must contain only body and summary")
    if not isinstance(result["body"], str) or not isinstance(result["summary"], dict):
        raise ResultError("result body must be text and summary must be an object")
    body, counts = process_result_body(result["body"], schema)
    if result["summary"] != counts:
        raise ResultError("result summary object does not match validated body counts")
    return {"body": body, "summary": dict(result["summary"])}, counts


def validate_result_object(result: Any, schema: str) -> dict[str, int]:
    _, counts = sanitize_result_object(result, schema)
    return counts
