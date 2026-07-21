from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "skills" / "deep-review" / "scripts" / "cache.py"
SPEC = importlib.util.spec_from_file_location("deep_review_cache", CACHE_PATH)
assert SPEC and SPEC.loader
CACHE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CACHE)


def digest(seed: str) -> str:
    return CACHE.sha256_bytes(seed.encode("utf-8"))


AUTO_GENERATION = object()


def manifest(agent: str = "code") -> dict[str, object]:
    return {
        "schema_version": 1,
        "agent": agent,
        "provider": "",
        "host": "",
        "repository": "example/project",
        "change_number": "",
        "base_identity": digest("base"),
        "head_identity": digest("head"),
        "mode": "local",
        "scope_hash": digest("scope"),
        "description_hash": digest("description"),
        "orchestrator_hash": digest("orchestrator"),
        "agent_prompt_hash": digest("agent"),
        "config_hash": digest("config"),
        "blocking_policy": ["HIGH", "MEDIUM"],
        "checklist_hash": digest("checklist"),
        "references_hash": digest("references"),
        "scoped_prompt_hash": digest("prompt"),
        "dependencies_complete": True,
        "dependencies": [
            {"path": "src/example.py", "hash": digest("dependency")},
        ],
    }


class KeyTests(unittest.TestCase):
    def test_key_is_canonical_and_sensitive_to_dependencies(self) -> None:
        first = CACHE.validate_key_manifest(manifest())
        second = dict(first)
        second["dependencies"] = [{"path": "src/example.py", "hash": digest("changed")}]
        first_key = digest(CACHE.canonical_bytes(first).decode("utf-8"))
        second_key = digest(CACHE.canonical_bytes(second).decode("utf-8"))
        self.assertNotEqual(first_key, second_key)
        reordered = dict(reversed(list(first.items())))
        self.assertEqual(CACHE.canonical_bytes(first), CACHE.canonical_bytes(reordered))

    def test_key_rejects_missing_and_unsorted_dependencies(self) -> None:
        missing = manifest()
        del missing["scope_hash"]
        with self.assertRaises(CACHE.CacheError):
            CACHE.validate_key_manifest(missing)
        unsorted = manifest()
        unsorted["dependencies"] = [
            {"path": "z", "hash": digest("z")},
            {"path": "a", "hash": digest("a")},
        ]
        with self.assertRaises(CACHE.CacheError):
            CACHE.validate_key_manifest(unsorted)

    def test_all_review_identity_changes_invalidate_the_key(self) -> None:
        original = manifest()
        original_key = CACHE.sha256_bytes(CACHE.canonical_bytes(original))
        replacements = {
            "provider": "gitlab",
            "host": "git.example.test",
            "repository": "example/another-project",
            "change_number": "42",
            "base_identity": "base-two",
            "head_identity": "head-two",
            "mode": "remote",
            "scope_hash": digest("scope-two"),
            "description_hash": digest("description-two"),
            "orchestrator_hash": digest("orchestrator-two"),
            "agent_prompt_hash": digest("agent-two"),
            "config_hash": digest("config-two"),
            "blocking_policy": ["HIGH"],
            "checklist_hash": digest("checklist-two"),
            "references_hash": digest("references-two"),
            "scoped_prompt_hash": digest("prompt-two"),
            "dependencies_complete": False,
            "dependencies": [{"path": "src/example.py", "hash": digest("dependency-two")}],
        }
        for field, replacement in replacements.items():
            with self.subTest(field=field):
                changed = dict(original)
                changed[field] = replacement
                CACHE.validate_key_manifest(changed)
                self.assertNotEqual(
                    CACHE.sha256_bytes(CACHE.canonical_bytes(changed)), original_key
                )

    def test_effective_description_and_chunk_plan_invalidate_cache_identity(self) -> None:
        original = manifest()
        original["description_hash"] = digest("effective description")
        original["scoped_prompt_hash"] = digest("chunks:1,2,3")
        original_key = CACHE.sha256_bytes(CACHE.canonical_bytes(original))

        changed_description = dict(original)
        changed_description["description_hash"] = digest("different effective description")
        changed_plan = dict(original)
        changed_plan["scoped_prompt_hash"] = digest("chunks:1,3,2")

        self.assertNotEqual(
            CACHE.sha256_bytes(CACHE.canonical_bytes(changed_description)), original_key
        )
        self.assertNotEqual(
            CACHE.sha256_bytes(CACHE.canonical_bytes(changed_plan)), original_key
        )


class BlockingPolicyTests(unittest.TestCase):
    def test_builtin_policy_tracks_default_stricter_and_looser_global_configuration(self) -> None:
        declared = ["HIGH", "MEDIUM"]
        cases = (
            (["HIGH", "MEDIUM", "CHECKLIST_FAIL"], ("HIGH", "MEDIUM")),
            (["HIGH", "MEDIUM", "LOW", "CHECKLIST_FAIL"], ("HIGH", "MEDIUM", "LOW")),
            (["HIGH", "CHECKLIST_FAIL"], ("HIGH",)),
        )
        for global_values, expected in cases:
            with self.subTest(global_values=global_values):
                self.assertEqual(
                    CACHE.effective_blocking_policy(
                        "hml", global_values, declared, built_in=True
                    ),
                    expected,
                )

        checklist_cases = (
            (["HIGH", "MEDIUM", "CHECKLIST_FAIL"], ("fail",)),
            (["HIGH", "MEDIUM", "LOW", "CHECKLIST_FAIL"], ("fail",)),
            (["HIGH", "MEDIUM"], ()),
        )
        for global_values, expected in checklist_cases:
            with self.subTest(global_values=global_values, schema="checklist"):
                self.assertEqual(
                    CACHE.effective_blocking_policy(
                        "checklist", global_values, ["fail"], built_in=True
                    ),
                    expected,
                )

    def test_extension_policy_intersects_with_global_configuration(self) -> None:
        declared = ["HIGH", "MEDIUM"]
        cases = (
            (["HIGH", "MEDIUM", "CHECKLIST_FAIL"], ("HIGH", "MEDIUM")),
            (["HIGH", "MEDIUM", "LOW", "CHECKLIST_FAIL"], ("HIGH", "MEDIUM")),
            (["HIGH", "CHECKLIST_FAIL"], ("HIGH",)),
        )
        for global_values, expected in cases:
            with self.subTest(global_values=global_values):
                self.assertEqual(
                    CACHE.effective_blocking_policy(
                        "hml", global_values, declared, built_in=False
                    ),
                    expected,
                )

    def test_checklist_fail_and_global_token_normalize_to_one_native_value(self) -> None:
        self.assertEqual(
            CACHE.effective_blocking_policy(
                "checklist", ["CHECKLIST_FAIL"], ["fail"], built_in=False
            ),
            ("fail",),
        )
        self.assertEqual(
            CACHE.effective_blocking_policy("checklist", ["HIGH"], ["fail"], built_in=False),
            (),
        )

    def test_invalid_or_contradictory_policies_are_rejected(self) -> None:
        invalid_calls = (
            lambda: CACHE.normalize_global_blocking(["HIGH", "HIGH"]),
            lambda: CACHE.normalize_global_blocking(["fail"]),
            lambda: CACHE.normalize_schema_blocking("hml", ["CHECKLIST_FAIL"]),
            lambda: CACHE.normalize_schema_blocking("checklist", ["fail", "fail"]),
            lambda: CACHE.validate_manifest_blocking(["HIGH", "fail"]),
            lambda: CACHE.effective_blocking_policy(
                "hml", ["HIGH"], ["HIGH"], built_in=True
            ),
        )
        for call in invalid_calls:
            with self.subTest(call=call), self.assertRaises(CACHE.CacheError):
                call()

    def test_result_classification_uses_only_the_effective_policy(self) -> None:
        counts = {"high": 0, "medium": 1, "low": 1}
        self.assertEqual(
            CACHE.classify_result(
                "hml", counts, ["HIGH", "MEDIUM"], dependencies_complete=True
            ),
            "blocking",
        )
        self.assertEqual(
            CACHE.classify_result("hml", counts, ["HIGH"], dependencies_complete=True),
            "nonblocking",
        )
        self.assertEqual(
            CACHE.classify_result("hml", counts, ["HIGH"], dependencies_complete=False),
            "incomplete",
        )
        self.assertEqual(
            CACHE.classify_result(
                "hml", counts, ["MEDIUM"], dependencies_complete=False
            ),
            "blocking",
        )


class ResultValidationTests(unittest.TestCase):
    def test_hml_empty_and_findings(self) -> None:
        self.assertEqual(
            CACHE.validate_hml("findings: none\nsummary: 0 high / 0 medium / 0 low\n"),
            {"high": 0, "medium": 0, "low": 0},
        )
        result = (
            "HIGH | functionality | src/a.py:4 | wrong value | return the expected value\n"
            "LOW | comments | src/a.py:8 | stale comment | update the comment\n"
            "summary: 1 high / 0 medium / 1 low\n"
        )
        self.assertEqual(CACHE.validate_hml(result), {"high": 1, "medium": 0, "low": 1})

    def test_hml_rejects_summary_drift_and_prose(self) -> None:
        with self.assertRaises(CACHE.CacheError):
            CACHE.validate_hml("summary: 0 high / 0 medium / 0 low\n")
        with self.assertRaises(CACHE.CacheError):
            CACHE.validate_hml("findings: none\nsummary: 1 high / 0 medium / 0 low\n")
        with self.assertRaises(CACHE.CacheError):
            CACHE.validate_hml("Looks good\nsummary: 0 high / 0 medium / 0 low\n")
        with self.assertRaises(CACHE.CacheError):
            CACHE.validate_hml(
                "HIGH | functionality | ../outside.py:1 | unsafe path | fix it\n"
                "summary: 1 high / 0 medium / 0 low\n"
            )

    def test_hml_requires_exact_separators_and_escaped_literal_pipes(self) -> None:
        invalid_findings = (
            "HIGH | functionality | src/a.py:1 | wrong value | use x | y\n",
            "HIGH | functionality | src/a.py:1 | wrong|value | use x\n",
        )
        for finding in invalid_findings:
            with self.subTest(finding=finding), self.assertRaises(CACHE.CacheError):
                CACHE.validate_hml(finding + "summary: 1 high / 0 medium / 0 low\n")

        escaped = (
            "HIGH | functionality | src/a.py:1 | wrong \\| value | use x \\| y\n"
            "summary: 1 high / 0 medium / 0 low\n"
        )
        self.assertEqual(CACHE.validate_hml(escaped), {"high": 1, "medium": 0, "low": 0})

    def test_hml_can_require_enabled_language_rule_categories(self) -> None:
        finding = (
            "MEDIUM | typescript.no-explicit-any | src/a.ts:1 | type boundary is unchecked | "
            "use unknown and narrow\nsummary: 0 high / 1 medium / 0 low\n"
        )
        self.assertEqual(
            CACHE.validate_hml(finding, {"typescript.no-explicit-any"}),
            {"high": 0, "medium": 1, "low": 0},
        )
        with self.assertRaisesRegex(CACHE.CacheError, "not enabled"):
            CACHE.validate_hml(finding, {"typescript.unsafe-type-assertion"})

    def test_hml_redaction_covers_common_credentials_without_changing_schema_fields(self) -> None:
        provider_token = "gh" + "p_" + "A" * 36
        gitlab_token = "glpat-" + "G" * 20
        access_key = "AKIA" + "B" * 16
        raw = (
            "HIGH | credential-exposure | src/auth.py:12 | "
            f"Authorization: Bearer {provider_token}, api_key='{access_key}', "
            f"password=hunter2, token={gitlab_token}, Cookie: session=abcdef123456 | "
            "rotate the credentials\n"
            "summary: 1 high / 0 medium / 0 low\n"
        )
        redacted = CACHE.redact_result_body(raw, "hml")

        self.assertNotIn(provider_token, redacted)
        self.assertNotIn(gitlab_token, redacted)
        self.assertNotIn(access_key, redacted)
        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("abcdef123456", redacted)
        self.assertGreaterEqual(redacted.count(CACHE.REDACTION_MARKER), 5)
        self.assertTrue(redacted.startswith(
            "HIGH | credential-exposure | src/auth.py:12 | "
        ))
        self.assertIn(" | rotate the credentials\n", redacted)
        self.assertEqual(
            CACHE.validate_hml(redacted), {"high": 1, "medium": 0, "low": 0}
        )

    def test_private_key_redaction_restores_a_valid_single_line_finding(self) -> None:
        key_body = "-----BEGIN PRIVATE KEY-----\nQUJDREVGRw==\n-----END PRIVATE KEY-----"
        raw = (
            "HIGH | credential-exposure | src/key.py:3 | committed key "
            f"{key_body} | remove and rotate it\n"
            "summary: 1 high / 0 medium / 0 low\n"
        )
        redacted = CACHE.redact_result_body(raw, "hml")

        self.assertNotIn("QUJDREVGRw==", redacted)
        self.assertEqual(redacted.count(CACHE.REDACTION_MARKER), 1)
        self.assertEqual(
            CACHE.validate_hml(redacted), {"high": 1, "medium": 0, "low": 0}
        )

    def test_checklist_redaction_preserves_item_and_failure_locations(self) -> None:
        raw = (
            "- [fail] secrets: password='correct horse battery staple' is committed\n"
            "summary: 0 pass / 1 fail / 0 N/A\n"
            "Failures (in order of priority):\n"
            "1. token:12 replace api_key=abcdef123456 with an environment lookup\n"
        )
        redacted = CACHE.redact_result_body(raw, "checklist")

        self.assertIn("- [fail] secrets:", redacted)
        self.assertIn("1. token:12 replace", redacted)
        self.assertNotIn("correct horse battery staple", redacted)
        self.assertNotIn("abcdef123456", redacted)
        self.assertEqual(
            CACHE.validate_checklist(redacted), {"pass": 0, "fail": 1, "N/A": 0}
        )

    def test_redaction_is_idempotent_and_preserves_false_positive_shaped_values(self) -> None:
        raw = (
            "LOW | configuration | src/token:12 | token_count=4, password_policy=strict, "
            "token=${API_TOKEN}, secret=<secret>, api_key=[REDACTED], password: hardcoded, "
            "token: exposed | keep placeholders\n"
            "summary: 0 high / 0 medium / 1 low\n"
        )
        redacted = CACHE.redact_result_body(raw, "hml")

        self.assertEqual(redacted, raw)
        self.assertEqual(CACHE.redact_result_body(redacted, "hml"), redacted)

    def test_process_result_reads_stdin_and_never_echoes_raw_credentials(self) -> None:
        provider_token = "gh" + "p_" + "C" * 36
        valid = (
            "HIGH | credential-exposure | src/auth.py:9 | "
            f"token={provider_token} is logged | remove the log\n"
            "summary: 1 high / 0 medium / 0 low\n"
        )
        completed = subprocess.run(
            [sys.executable, str(CACHE_PATH), "process-result", "--schema", "hml"],
            input=valid,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0)
        processed = json.loads(completed.stdout)
        self.assertNotIn(provider_token, completed.stdout)
        self.assertIn(CACHE.REDACTION_MARKER, processed["body"])
        self.assertEqual(processed["summary"], {"high": 1, "medium": 0, "low": 0})

        malformed = f"malformed password={provider_token}\nsummary: 0 high / 0 medium / 0 low\n"
        failed = subprocess.run(
            [sys.executable, str(CACHE_PATH), "process-result", "--schema", "hml"],
            input=malformed,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(failed.returncode, 2)
        self.assertNotIn(provider_token, failed.stderr)
        self.assertNotIn("malformed password", failed.stderr)
        self.assertNotIn("Traceback", failed.stderr)

    def test_process_result_rejects_invalid_or_oversized_stdin_without_traceback(self) -> None:
        for payload, expected in (
            (b"\xff\xfe", b"cannot read UTF-8 result from standard input"),
            (b"x" * (CACHE.RESULT_MAX_UTF8_BYTES + 1), b"result exceeds"),
        ):
            with self.subTest(expected=expected):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(CACHE_PATH),
                        "process-result",
                        "--schema",
                        "hml",
                    ],
                    input=payload,
                    check=False,
                    capture_output=True,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(completed.stdout, b"")
                self.assertIn(expected, completed.stderr)
                self.assertNotIn(b"Traceback", completed.stderr)

    def test_validate_result_command_rejects_invalid_allowed_categories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.txt"
            result.write_text("findings: none\nsummary: 0 high / 0 medium / 0 low\n", encoding="utf-8")
            base = {"schema": "hml", "file": str(result)}
            for categories in (["not-namespaced"], ["python.runtime-assert", "python.runtime-assert"]):
                with self.subTest(categories=categories), self.assertRaises(CACHE.CacheError):
                    CACHE.command_validate_result(
                        argparse.Namespace(**base, allowed_category=categories)
                    )

    def test_result_body_and_validation_input_have_hard_byte_limits(self) -> None:
        oversized = "x" * (CACHE.RESULT_MAX_UTF8_BYTES + 1)
        with self.assertRaisesRegex(CACHE.CacheError, "result body exceeds"):
            CACHE.validate_result_object(
                {"body": oversized, "summary": {"high": 0, "medium": 0, "low": 0}},
                "hml",
            )

        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.txt"
            result.write_text(oversized, encoding="utf-8")
            with self.assertRaisesRegex(CACHE.CacheError, "result exceeds"):
                CACHE.command_validate_result(
                    argparse.Namespace(schema="hml", file=str(result), allowed_category=[])
                )

    def test_result_json_rejects_escaped_lone_surrogate_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.json"
            result.write_text(
                '{"body":"findings: none\\nsummary: 0 high / 0 medium / 0 low\\n\\ud800",'
                '"summary":{"high":0,"medium":0,"low":0}}',
                encoding="utf-8",
            )
            parsed = CACHE.read_json(result)
            with self.assertRaisesRegex(CACHE.CacheError, "valid Unicode scalar values"):
                CACHE.validate_result_object(parsed, "hml")

    def test_checklist_empty_and_failure(self) -> None:
        passing = "- [pass] tests: focused test exists\nsummary: 1 pass / 0 fail / 0 N/A\nFailures: none.\n"
        self.assertEqual(CACHE.validate_checklist(passing), {"pass": 1, "fail": 0, "N/A": 0})
        failing = (
            "- [fail] docs: config is undocumented\n"
            "- [N/A] migration: no migration changed\n"
            "summary: 0 pass / 1 fail / 1 N/A\n"
            "Failures (in order of priority):\n"
            "1. docs/config.md:1 document the new key\n"
        )
        self.assertEqual(CACHE.validate_checklist(failing), {"pass": 0, "fail": 1, "N/A": 1})

    def test_checklist_requires_exact_empty_sentinel(self) -> None:
        with self.assertRaises(CACHE.CacheError):
            CACHE.validate_checklist("summary: 0 pass / 0 fail / 0 N/A\nNo failures.\n")

    def test_checklist_requires_one_safe_location_per_failure(self) -> None:
        prefix = "- [fail] docs: config is undocumented\nsummary: 0 pass / 1 fail / 0 N/A\n"
        invalid_tails = (
            "Failures (in order of priority):\n",
            "Failures (in order of priority):\n1. explain the failure\n",
            "Failures (in order of priority):\n1. ../outside.md:1 fix it\n",
            "Failures (in order of priority):\n2. docs/config.md:1 fix it\n",
            (
                "Failures (in order of priority):\n"
                "1. docs/config.md:1 fix it\n"
                "2. docs/other.md:1 extra action\n"
            ),
        )
        for tail in invalid_tails:
            with self.subTest(tail=tail), self.assertRaises(CACHE.CacheError):
                CACHE.validate_checklist(prefix + tail)


class CacheStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".git").mkdir()
        self.cache_dir = CACHE.safe_cache_dir(str(self.root), ".deep-review-cache", create=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_atomic_write_and_latest_record_are_bounded(self) -> None:
        path = self.cache_dir / "agents" / "code.json"
        first = {"value": 1}
        second = {"value": 2}
        CACHE.atomic_write(path, first)
        CACHE.atomic_write(path, second)
        self.assertEqual(CACHE.read_json(path), second)
        self.assertEqual(len(list((self.cache_dir / "agents").glob("code.json"))), 1)
        mode = stat.S_IMODE(path.stat().st_mode)
        self.assertEqual(mode & 0o077, 0)

    def test_atomic_write_uses_exact_measured_utf8_bytes(self) -> None:
        path = self.cache_dir / "newline-heavy.json"
        value = {"values": [0] * 70_000}
        expected = (
            json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        self.assertLessEqual(len(expected), CACHE.CACHE_RECORD_MAX_UTF8_BYTES)
        self.assertGreater(
            len(expected) + expected.count(b"\n"),
            CACHE.CACHE_RECORD_MAX_UTF8_BYTES,
        )

        opened_modes: list[str] = []
        original_fdopen = CACHE.os.fdopen

        def recording_fdopen(descriptor: int, mode: str):
            opened_modes.append(mode)
            return original_fdopen(descriptor, mode)

        with mock.patch.object(CACHE.os, "fdopen", side_effect=recording_fdopen):
            CACHE.atomic_write(path, value)

        self.assertEqual(opened_modes, ["wb"])
        self.assertEqual(path.read_bytes(), expected)

    def test_store_redacts_result_before_stdout_and_persistence(self) -> None:
        provider_token = "gh" + "p_" + "D" * 36
        result_path = self.root / "result.json"
        manifest_path = self.root / "manifest.json"
        key_manifest = manifest()
        manifest_path.write_text(json.dumps(key_manifest), encoding="utf-8")
        key = CACHE.sha256_bytes(CACHE.canonical_bytes(key_manifest))
        result_path.write_text(
            json.dumps(
                {
                    "body": (
                        "HIGH | credential-exposure | src/auth.py:4 | "
                        f"password={provider_token} is exposed | rotate it\n"
                        "summary: 1 high / 0 medium / 0 low\n"
                    ),
                    "summary": {"high": 1, "medium": 0, "low": 0},
                }
            ),
            encoding="utf-8",
        )
        output = io.StringIO()
        with redirect_stdout(output):
            CACHE.command_store(
                argparse.Namespace(
                    repo_root=str(self.root),
                    cache_dir=".deep-review-cache",
                    agent="code",
                    key=key,
                    iteration=1,
                    schema="hml",
                    manifest=str(manifest_path),
                    result=str(result_path),
                )
            )

        record_path = self.cache_dir / "agents" / "code.json"
        self.assertNotIn(provider_token, output.getvalue())
        self.assertNotIn(provider_token.encode("utf-8"), record_path.read_bytes())
        self.assertIn(CACHE.REDACTION_MARKER, output.getvalue())
        self.assertIn(CACHE.REDACTION_MARKER.encode("utf-8"), record_path.read_bytes())

    def test_cache_reads_and_writes_reject_oversized_records(self) -> None:
        read_path = self.cache_dir / "oversized-read.json"
        read_path.write_text(
            json.dumps({"value": "x" * CACHE.CACHE_RECORD_MAX_UTF8_BYTES}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(CACHE.CacheError, "JSON input exceeds"):
            CACHE.read_json(read_path)

        write_path = self.cache_dir / "oversized-write.json"
        with self.assertRaisesRegex(CACHE.CacheError, "cache record exceeds"):
            CACHE.atomic_write(
                write_path,
                {"value": "x" * CACHE.CACHE_RECORD_MAX_UTF8_BYTES},
            )
        self.assertFalse(write_path.exists())

    def test_store_cli_reports_escaped_lone_surrogate_without_traceback(self) -> None:
        result_path = self.root / "surrogate-result.json"
        manifest_path = self.root / "manifest.json"
        key_manifest = manifest()
        manifest_path.write_text(json.dumps(key_manifest), encoding="utf-8")
        result_path.write_text(
            '{"body":"findings: none\\nsummary: 0 high / 0 medium / 0 low\\n\\ud800",'
            '"summary":{"high":0,"medium":0,"low":0}}',
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(CACHE_PATH),
                "store",
                "--repo-root",
                str(self.root),
                "--cache-dir",
                ".deep-review-cache",
                "--agent",
                "code",
                "--key",
                CACHE.sha256_bytes(CACHE.canonical_bytes(key_manifest)),
                "--classification",
                "nonblocking",
                "--iteration",
                "1",
                "--schema",
                "hml",
                "--manifest",
                str(manifest_path),
                "--result",
                str(result_path),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("cache error: result body must contain valid Unicode", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_store_and_lookup_survive_separate_calls_and_replace_latest(self) -> None:
        result_path = self.root / "result.json"
        manifest_path = self.root / "manifest.json"
        key_manifest = manifest()
        manifest_path.write_text(json.dumps(key_manifest), encoding="utf-8")
        key = CACHE.sha256_bytes(CACHE.canonical_bytes(key_manifest))
        result_path.write_text(
            json.dumps(
                {
                    "body": "findings: none\nsummary: 0 high / 0 medium / 0 low\n",
                    "summary": {"high": 0, "medium": 0, "low": 0},
                }
            ),
            encoding="utf-8",
        )
        common = {
            "repo_root": str(self.root),
            "cache_dir": ".deep-review-cache",
            "agent": "code",
            "key": key,
        }
        with redirect_stdout(io.StringIO()):
            CACHE.command_store(
                argparse.Namespace(
                    **common,
                    classification="nonblocking",
                    iteration=1,
                    schema="hml",
                    manifest=str(manifest_path),
                    result=str(result_path),
                )
            )
            CACHE.command_store(
                argparse.Namespace(
                    **common,
                    classification="nonblocking",
                    iteration=2,
                    schema="hml",
                    manifest=str(manifest_path),
                    result=str(result_path),
                )
            )
        output = io.StringIO()
        with redirect_stdout(output):
            CACHE.command_lookup(argparse.Namespace(**common))
        record = json.loads(output.getvalue())
        self.assertEqual(record["iteration"], 2)
        self.assertEqual(record["key"], key)
        self.assertEqual(record["manifest"]["dependencies"], key_manifest["dependencies"])
        self.assertEqual(len(list((self.cache_dir / "agents").glob("*.json"))), 1)

        probe = io.StringIO()
        with redirect_stdout(probe):
            CACHE.command_probe(
                argparse.Namespace(
                    repo_root=str(self.root), cache_dir=".deep-review-cache", agent="code"
                )
            )
        self.assertEqual(json.loads(probe.getvalue()), key_manifest)

        record_path = self.cache_dir / "agents" / "code.json"
        tampered = CACHE.read_json(record_path)
        tampered["iteration"] = True
        CACHE.atomic_write(record_path, tampered)
        with self.assertRaisesRegex(CACHE.CacheError, "invalid iteration"):
            CACHE.command_probe(
                argparse.Namespace(
                    repo_root=str(self.root), cache_dir=".deep-review-cache", agent="code"
                )
            )

        tampered["iteration"] = 2
        tampered["result"]["body"] = "findings: none\nsummary: 1 high / 0 medium / 0 low\n"
        CACHE.atomic_write(record_path, tampered)
        with self.assertRaises(CACHE.CacheError):
            CACHE.command_lookup(argparse.Namespace(**common))

    def test_store_derives_and_lookup_revalidates_classification(self) -> None:
        result_path = self.root / "result.json"
        manifest_path = self.root / "manifest.json"
        key_manifest = manifest()
        key_manifest["blocking_policy"] = ["HIGH"]
        manifest_path.write_text(json.dumps(key_manifest), encoding="utf-8")
        key = CACHE.sha256_bytes(CACHE.canonical_bytes(key_manifest))
        result_path.write_text(
            json.dumps(
                {
                    "body": (
                        "MEDIUM | functionality | src/a.py:4 | wrong value | fix it\n"
                        "summary: 0 high / 1 medium / 0 low\n"
                    ),
                    "summary": {"high": 0, "medium": 1, "low": 0},
                }
            ),
            encoding="utf-8",
        )
        args = argparse.Namespace(
            repo_root=str(self.root),
            cache_dir=".deep-review-cache",
            agent="code",
            key=key,
            iteration=1,
            schema="hml",
            manifest=str(manifest_path),
            result=str(result_path),
        )
        output = io.StringIO()
        with redirect_stdout(output):
            CACHE.command_store(args)
        self.assertEqual(json.loads(output.getvalue())["classification"], "nonblocking")

        with self.assertRaisesRegex(CACHE.CacheError, "classification must be nonblocking"):
            CACHE.command_store(argparse.Namespace(**vars(args), classification="blocking"))

        record_path = self.cache_dir / "agents" / "code.json"
        tampered = CACHE.read_json(record_path)
        tampered["classification"] = "blocking"
        CACHE.atomic_write(record_path, tampered)
        with self.assertRaisesRegex(CACHE.CacheError, "classification disagrees"):
            CACHE.command_lookup(
                argparse.Namespace(
                    repo_root=str(self.root),
                    cache_dir=".deep-review-cache",
                    agent="code",
                    key=key,
                )
            )

    def test_cache_survives_separate_process_invocations(self) -> None:
        result_path = self.root / "result.json"
        manifest_path = self.root / "manifest.json"
        key_manifest = manifest()
        manifest_path.write_text(json.dumps(key_manifest), encoding="utf-8")
        key = CACHE.sha256_bytes(CACHE.canonical_bytes(key_manifest))
        result_path.write_text(
            json.dumps(
                {
                    "body": "findings: none\nsummary: 0 high / 0 medium / 0 low\n",
                    "summary": {"high": 0, "medium": 0, "low": 0},
                }
            ),
            encoding="utf-8",
        )
        base = [
            sys.executable,
            str(CACHE_PATH),
            "--repo-root",
            str(self.root),
            "--cache-dir",
            ".deep-review-cache",
            "--agent",
            "code",
        ]
        subprocess.run(
            base[:2]
            + [
                "store",
                *base[2:],
                "--key",
                key,
                "--classification",
                "nonblocking",
                "--iteration",
                "1",
                "--schema",
                "hml",
                "--manifest",
                str(manifest_path),
                "--result",
                str(result_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        looked_up = subprocess.run(
            base[:2] + ["lookup", *base[2:], "--key", key],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(looked_up.stdout)["key"], key)

    def test_lookup_key_miss_and_corrupt_record_fail_closed(self) -> None:
        common = argparse.Namespace(
            repo_root=str(self.root),
            cache_dir=".deep-review-cache",
            agent="code",
            key=digest("expected"),
        )
        with self.assertRaises(SystemExit) as missing:
            CACHE.command_lookup(common)
        self.assertEqual(missing.exception.code, 3)

        record_path = self.cache_dir / "agents" / "code.json"
        record_path.parent.mkdir()
        record_path.write_text("{not-json", encoding="utf-8")
        with self.assertRaises(CACHE.CacheError):
            CACHE.command_lookup(common)

    def test_invalid_utf8_json_inputs_are_normalized(self) -> None:
        invalid_bytes = b"\xff\xfe"

        record_path = self.cache_dir / "agents" / "code.json"
        record_path.parent.mkdir()
        record_path.write_bytes(invalid_bytes)
        with self.assertRaisesRegex(CACHE.CacheError, "cannot read valid JSON"):
            CACHE.command_probe(
                argparse.Namespace(
                    repo_root=str(self.root), cache_dir=".deep-review-cache", agent="code"
                )
            )

        state_path = self.cache_dir / "state.json"
        state_path.write_bytes(invalid_bytes)
        with self.assertRaisesRegex(CACHE.CacheError, "cannot read valid JSON"):
            CACHE.read_scope_states(state_path)

        manifest_path = self.root / "manifest.json"
        manifest_path.write_bytes(invalid_bytes)
        with self.assertRaisesRegex(CACHE.CacheError, "cannot read valid JSON"):
            CACHE.command_key(argparse.Namespace(manifest=str(manifest_path)))

        manifest_path.write_text(json.dumps(manifest()), encoding="utf-8")
        result_path = self.root / "result.json"
        result_path.write_bytes(invalid_bytes)
        with self.assertRaisesRegex(CACHE.CacheError, "cannot read valid JSON"):
            CACHE.command_store(
                argparse.Namespace(
                    repo_root=str(self.root),
                    cache_dir=".deep-review-cache",
                    agent="code",
                    key=digest("key"),
                    classification="nonblocking",
                    iteration=1,
                    schema="hml",
                    manifest=str(manifest_path),
                    result=str(result_path),
                )
            )

    def test_invalid_utf8_cli_inputs_report_concise_cache_errors(self) -> None:
        invalid_path = self.root / "invalid-input"
        invalid_path.write_bytes(b"\xff\xfe")
        commands = (
            ["key", "--manifest", str(invalid_path)],
            ["validate-result", "--schema", "hml", "--file", str(invalid_path)],
        )
        for arguments in commands:
            with self.subTest(command=arguments[0]):
                completed = subprocess.run(
                    [sys.executable, str(CACHE_PATH), *arguments],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(completed.stdout, "")
                self.assertTrue(completed.stderr.startswith("cache error: cannot read"))
                self.assertNotIn("Traceback", completed.stderr)

    def test_cache_path_rejects_escape_and_symlink(self) -> None:
        with self.assertRaises(CACHE.CacheError):
            CACHE.safe_cache_dir(str(self.root), "../outside", create=True)
        external = self.root.parent / f"{self.root.name}-external"
        external.mkdir(exist_ok=True)
        link = self.root / "cache-link"
        link.symlink_to(external, target_is_directory=True)
        try:
            with self.assertRaises(CACHE.CacheError):
                CACHE.safe_cache_dir(str(self.root), "cache-link", create=True)
        finally:
            link.unlink()
            external.rmdir()

        internal = self.root / "internal-cache"
        internal.mkdir()
        internal_link = self.root / "internal-link"
        internal_link.symlink_to(internal, target_is_directory=True)
        try:
            with self.assertRaises(CACHE.CacheError):
                CACHE.safe_cache_dir(str(self.root), "internal-link", create=True)
        finally:
            internal_link.unlink()
            internal.rmdir()

    def test_unwritable_cache_failure_is_normalized(self) -> None:
        target = self.cache_dir / "state.json"
        with mock.patch.object(CACHE.tempfile, "mkstemp", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(CACHE.CacheError, "cannot prepare atomic write"):
                CACHE.atomic_write(target, {"value": 1})

    def test_convergence_state_rejects_iterations_outside_fixed_range(self) -> None:
        self.assertEqual(CACHE.MAX_ITERATIONS, 3)
        valid = {
            "schema_version": CACHE.SCHEMA_VERSION,
            "scope_key": digest("scope"),
            "reviewed_state_hash": digest("state"),
            "iteration": 1,
            "status": "blocked",
            "reuse_used": False,
            "targeted_rerun_used": False,
            "generation": 1,
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        for invalid in (-1, 0, 4, True, 1.0, "3"):
            with self.subTest(iteration=invalid), self.assertRaisesRegex(
                CACHE.CacheError, "invalid iteration"
            ):
                CACHE.validate_state_record({**valid, "iteration": invalid})

    def advance_state(
        self,
        reviewed: str,
        *,
        scope: str = "scope-key",
        reuse_used: bool = False,
        targeted_rerun_used: bool = False,
        final_guard_run: bool = False,
        start_new_sequence: bool = False,
        expected_generation: int | None | object = AUTO_GENERATION,
        status: str = "blocked",
    ) -> dict[str, object]:
        output = io.StringIO()
        scope_key = digest(scope)
        if expected_generation is AUTO_GENERATION:
            states = CACHE.read_scope_states(self.cache_dir / "state.json")
            prior = states.get(scope_key)
            expected_generation = None if prior is None else prior["generation"]
        args = argparse.Namespace(
            repo_root=str(self.root),
            cache_dir=".deep-review-cache",
            scope_key=scope_key,
            reviewed_state_hash=reviewed,
            status=status,
            reuse_used=reuse_used,
            targeted_rerun_used=targeted_rerun_used,
            final_guard_run=final_guard_run,
            start_new_sequence=start_new_sequence,
            expected_generation=expected_generation,
        )
        with redirect_stdout(output):
            CACHE.command_state(args)
        return json.loads(output.getvalue())

    def test_state_counts_only_changed_reviewed_state(self) -> None:
        def advance(reviewed: str) -> dict[str, object]:
            return self.advance_state(reviewed)

        first = advance(digest("one"))
        unchanged = advance(digest("one"))
        second = advance(digest("two"))
        third = advance(digest("three"))
        unchanged_at_cap = advance(digest("three"))
        with self.assertRaisesRegex(CACHE.CacheError, "must use --start-new-sequence"):
            advance(digest("four"))
        restarted = self.advance_state(digest("four"), start_new_sequence=True)
        self.assertEqual(first["iteration"], 1)
        self.assertEqual(unchanged["iteration"], 1)
        self.assertEqual(second["iteration"], 2)
        self.assertEqual(third["iteration"], 3)
        self.assertEqual(unchanged_at_cap["iteration"], 3)
        self.assertEqual(restarted["iteration"], 1)

        (self.cache_dir / "state.json").write_text("{broken", encoding="utf-8")
        with self.assertRaises(CACHE.CacheError):
            advance(digest("five"))

    def test_state_preserves_interleaved_scopes(self) -> None:
        first_a = self.advance_state(digest("a-one"), scope="scope-a")
        first_b = self.advance_state(digest("b-one"), scope="scope-b")
        second_a = self.advance_state(digest("a-two"), scope="scope-a")
        self.assertEqual(first_a["iteration"], 1)
        self.assertEqual(first_b["iteration"], 1)
        self.assertEqual(second_a["iteration"], 2)

        state_path = self.cache_dir / "state.json"
        states = CACHE.read_scope_states(state_path)
        self.assertEqual(set(states), {digest("scope-a"), digest("scope-b")})

    def test_state_accumulates_guard_history_until_guard_runs(self) -> None:
        first = self.advance_state(digest("one"), reuse_used=True)
        second = self.advance_state(digest("one"), targeted_rerun_used=True)
        self.assertTrue(first["reuse_used"])
        self.assertTrue(second["reuse_used"])
        self.assertTrue(second["targeted_rerun_used"])

        guarded = self.advance_state(
            digest("one"), final_guard_run=True, expected_generation=second["generation"]
        )
        self.assertFalse(guarded["reuse_used"])
        self.assertFalse(guarded["targeted_rerun_used"])
        self.assertEqual(guarded["iteration"], second["iteration"])

    def test_ready_state_with_guard_history_requires_final_guard(self) -> None:
        observed = self.advance_state(digest("one"), reuse_used=True)
        with self.assertRaisesRegex(CACHE.CacheError, "requires a successful final guard"):
            self.advance_state(digest("one"), status="ready")

        state = CACHE.read_scope_states(self.cache_dir / "state.json")[digest("scope-key")]
        self.assertEqual(state["generation"], observed["generation"])
        guarded = self.advance_state(
            digest("one"),
            status="ready",
            final_guard_run=True,
            expected_generation=observed["generation"],
        )
        self.assertEqual(guarded["status"], "ready")
        self.assertFalse(guarded["reuse_used"])
        self.assertFalse(guarded["targeted_rerun_used"])

    def test_final_guard_rejects_stale_generation(self) -> None:
        observed = self.advance_state(digest("one"), reuse_used=True)
        self.advance_state(digest("one"), targeted_rerun_used=True)
        with self.assertRaisesRegex(CACHE.CacheError, "changed during final guard"):
            self.advance_state(
                digest("one"),
                final_guard_run=True,
                expected_generation=observed["generation"],
            )

    def test_final_guard_rejects_a_different_reviewed_state(self) -> None:
        observed = self.advance_state(digest("one"), reuse_used=True)
        with self.assertRaisesRegex(CACHE.CacheError, "reviewed state changed during final guard"):
            self.advance_state(
                digest("two"),
                final_guard_run=True,
                expected_generation=observed["generation"],
            )

    def test_existing_scope_updates_require_current_generation(self) -> None:
        observed = self.advance_state(digest("one"))
        with self.assertRaisesRegex(CACHE.CacheError, "requires --expected-generation"):
            self.advance_state(digest("one"), expected_generation=None)

        self.advance_state(digest("one"))
        with self.assertRaisesRegex(CACHE.CacheError, "changed during review"):
            self.advance_state(
                digest("two"), expected_generation=observed["generation"]
            )

    def test_changed_state_after_ready_starts_a_new_sequence(self) -> None:
        first = self.advance_state(digest("first"), status="blocked")
        second = self.advance_state(digest("second"), status="blocked")
        ready = self.advance_state(digest("ready"), status="ready")
        restarted = self.advance_state(digest("changed"), status="blocked")
        advanced = self.advance_state(digest("changed-again"), status="blocked")
        self.assertEqual(first["iteration"], 1)
        self.assertEqual(second["iteration"], 2)
        self.assertEqual(ready["iteration"], 3)
        self.assertEqual(restarted["iteration"], 1)
        self.assertEqual(advanced["iteration"], 2)

    def test_changed_state_after_exhausted_sequence_starts_a_new_sequence(self) -> None:
        first = self.advance_state(digest("first"), reuse_used=True)
        second = self.advance_state(digest("second"), targeted_rerun_used=True)
        third = self.advance_state(digest("third"), status="incomplete")

        agent_dir = self.cache_dir / "agents"
        agent_dir.mkdir()
        cached_result = agent_dir / "code.json"
        cached_result.write_text('{"preserved": true}\n', encoding="utf-8")

        restarted = self.advance_state(
            digest("fixed"), status="blocked", start_new_sequence=True
        )

        self.assertEqual(first["iteration"], 1)
        self.assertEqual(second["iteration"], 2)
        self.assertEqual(third["iteration"], 3)
        self.assertEqual(restarted["iteration"], 1)
        self.assertFalse(restarted["reuse_used"])
        self.assertFalse(restarted["targeted_rerun_used"])
        self.assertEqual(cached_result.read_text(encoding="utf-8"), '{"preserved": true}\n')

    def test_new_sequence_flag_is_valid_only_for_changed_terminal_state(self) -> None:
        with self.assertRaisesRegex(CACHE.CacheError, "terminal iteration-3"):
            self.advance_state(digest("first"), start_new_sequence=True)

        first = self.advance_state(digest("first"))
        with self.assertRaisesRegex(CACHE.CacheError, "terminal iteration-3"):
            self.advance_state(digest("second"), start_new_sequence=True)

        second = self.advance_state(digest("second"))
        third = self.advance_state(digest("third"))
        with self.assertRaisesRegex(CACHE.CacheError, "changed reviewed state"):
            self.advance_state(digest("third"), start_new_sequence=True)
        with self.assertRaisesRegex(CACHE.CacheError, "cannot start"):
            self.advance_state(
                digest("third"),
                final_guard_run=True,
                start_new_sequence=True,
            )

        self.assertEqual(first["iteration"], 1)
        self.assertEqual(second["iteration"], 2)
        self.assertEqual(third["iteration"], 3)

    def test_exhausted_sequence_rolls_over_across_process_invocations(self) -> None:
        command = [
            sys.executable,
            str(CACHE_PATH),
            "state",
            "--repo-root",
            str(self.root),
            "--cache-dir",
            ".deep-review-cache",
            "--scope-key",
            digest("scope-key"),
            "--status",
            "blocked",
        ]
        generation: int | None = None
        iterations = []
        for reviewed in ("first", "second", "third", "fixed"):
            arguments = [*command, "--reviewed-state-hash", digest(reviewed)]
            if generation is not None:
                arguments.extend(("--expected-generation", str(generation)))
            if reviewed == "fixed":
                arguments.append("--start-new-sequence")
            completed = subprocess.run(
                arguments,
                check=True,
                capture_output=True,
                text=True,
            )
            state = json.loads(completed.stdout)
            iterations.append(state["iteration"])
            generation = state["generation"]

        self.assertEqual(iterations, [1, 2, 3, 1])

    def test_state_read_requires_scope_for_multiple_records(self) -> None:
        self.advance_state(digest("a-one"), scope="scope-a")
        self.advance_state(digest("b-one"), scope="scope-b")
        with self.assertRaises(CACHE.CacheError):
            CACHE.command_state_read(
                argparse.Namespace(
                    repo_root=str(self.root), cache_dir=".deep-review-cache", scope_key=None
                )
            )
        output = io.StringIO()
        with redirect_stdout(output):
            CACHE.command_state_read(
                argparse.Namespace(
                    repo_root=str(self.root),
                    cache_dir=".deep-review-cache",
                    scope_key=digest("scope-b"),
                )
            )
        self.assertEqual(json.loads(output.getvalue())["scope_key"], digest("scope-b"))

    def test_concurrent_scope_updates_do_not_lose_records(self) -> None:
        processes = []
        for index in range(8):
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        str(CACHE_PATH),
                        "state",
                        "--repo-root",
                        str(self.root),
                        "--cache-dir",
                        ".deep-review-cache",
                        "--scope-key",
                        digest(f"concurrent-scope-{index}"),
                        "--reviewed-state-hash",
                        digest(f"concurrent-state-{index}"),
                        "--status",
                        "blocked",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        completed = [process.communicate(timeout=10) for process in processes]
        self.assertEqual([process.returncode for process in processes], [0] * len(processes), completed)
        states = CACHE.read_scope_states(self.cache_dir / "state.json")
        self.assertEqual(len(states), len(processes))

    def test_legacy_single_scope_state_is_migrated(self) -> None:
        legacy = {
            "schema_version": 1,
            "scope_key": digest("legacy-scope"),
            "reviewed_state_hash": digest("legacy-state"),
            "iteration": 2,
            "status": "blocked",
            "reuse_used": True,
            "targeted_rerun_used": False,
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        CACHE.atomic_write(self.cache_dir / "state.json", legacy)
        current = self.advance_state(digest("current-state"), scope="current-scope")
        states = CACHE.read_scope_states(self.cache_dir / "state.json")
        self.assertEqual(current["iteration"], 1)
        self.assertEqual(set(states), {digest("legacy-scope"), digest("current-scope")})
        self.assertEqual(states[digest("legacy-scope")]["generation"], 1)

    def test_scope_capacity_evicts_only_completed_reviews(self) -> None:
        self.advance_state(digest("ready-state"), scope="ready-scope", status="ready")
        for index in range(CACHE.MAX_SCOPE_STATES - 1):
            self.advance_state(digest(f"blocked-state-{index}"), scope=f"blocked-scope-{index}")
        self.advance_state(digest("new-state"), scope="new-scope")
        states = CACHE.read_scope_states(self.cache_dir / "state.json")
        self.assertEqual(len(states), CACHE.MAX_SCOPE_STATES)
        self.assertNotIn(digest("ready-scope"), states)

    def test_scope_capacity_evicts_exhausted_reviews(self) -> None:
        self.advance_state(digest("terminal-one"), scope="terminal-scope")
        self.advance_state(digest("terminal-two"), scope="terminal-scope")
        self.advance_state(digest("terminal-three"), scope="terminal-scope")
        for index in range(CACHE.MAX_SCOPE_STATES - 1):
            self.advance_state(digest(f"active-state-{index}"), scope=f"active-scope-{index}")

        self.advance_state(digest("new-state"), scope="new-scope")

        states = CACHE.read_scope_states(self.cache_dir / "state.json")
        self.assertEqual(len(states), CACHE.MAX_SCOPE_STATES)
        self.assertNotIn(digest("terminal-scope"), states)
        self.assertIn(digest("new-scope"), states)

    def test_scope_capacity_preserves_unfinished_reviews(self) -> None:
        for index in range(CACHE.MAX_SCOPE_STATES):
            self.advance_state(digest(f"state-{index}"), scope=f"scope-{index}")
        with self.assertRaisesRegex(CACHE.CacheError, "capacity is exhausted"):
            self.advance_state(digest("overflow"), scope="overflow")

    def test_windows_lock_backend_is_selected_without_fcntl(self) -> None:
        class FakeMsvcrt:
            LK_LOCK = 1
            LK_UNLCK = 2

            def __init__(self) -> None:
                self.calls: list[tuple[int, int]] = []

            def locking(self, _descriptor: int, mode: int, size: int) -> None:
                self.calls.append((mode, size))

        backend = FakeMsvcrt()
        with (
            mock.patch.object(CACHE, "_fcntl", None),
            mock.patch.object(CACHE, "_msvcrt", backend),
            CACHE.cache_lock(self.cache_dir, "windows-test"),
        ):
            pass
        self.assertEqual(backend.calls, [(backend.LK_LOCK, 1), (backend.LK_UNLCK, 1)])

    def test_private_descriptor_mode_is_optional(self) -> None:
        with mock.patch.object(CACHE.os, "fchmod", None):
            CACHE.set_private_descriptor_mode(123)

    def test_clear_removes_only_validated_cache_directory(self) -> None:
        marker = self.root / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        CACHE.atomic_write(self.cache_dir / "state.json", {"value": 1})
        CACHE.command_clear(
            argparse.Namespace(repo_root=str(self.root), cache_dir=".deep-review-cache")
        )
        self.assertFalse(self.cache_dir.exists())
        CACHE.command_clear(
            argparse.Namespace(repo_root=str(self.root), cache_dir=".deep-review-cache")
        )
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
