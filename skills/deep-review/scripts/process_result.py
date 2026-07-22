#!/usr/bin/env python3
"""Process one bounded Deep Review result through the credential-safe boundary."""

from __future__ import annotations

import argparse
import json
import sys

from result_processing import (
    RESULT_MAX_UTF8_BYTES,
    ResultError,
    process_result_body,
    validate_allowed_categories,
)


def read_bounded_stdin() -> str:
    try:
        data = sys.stdin.buffer.read(RESULT_MAX_UTF8_BYTES + 1)
    except OSError as exc:
        raise ResultError(f"cannot read result from standard input: {exc}") from exc
    if len(data) > RESULT_MAX_UTF8_BYTES:
        raise ResultError(f"result exceeds the {RESULT_MAX_UTF8_BYTES}-byte limit")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ResultError("cannot read UTF-8 result from standard input") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", choices=("hml", "checklist"), required=True)
    parser.add_argument("--allowed-category", action="append")
    args = parser.parse_args()
    try:
        body, counts = process_result_body(
            read_bounded_stdin(),
            args.schema,
            allowed_categories=validate_allowed_categories(
                args.schema, args.allowed_category
            ),
        )
    except ResultError as exc:
        print(f"result error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    print(json.dumps({"body": body, "summary": counts}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
