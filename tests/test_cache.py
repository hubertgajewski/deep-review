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
            CACHE.validate_hml("findings: none\nsummary: 1 high / 0 medium / 0 low\n")
        with self.assertRaises(CACHE.CacheError):
            CACHE.validate_hml("Looks good\nsummary: 0 high / 0 medium / 0 low\n")
        with self.assertRaises(CACHE.CacheError):
            CACHE.validate_hml(
                "HIGH | functionality | ../outside.py:1 | unsafe path | fix it\n"
                "summary: 1 high / 0 medium / 0 low\n"
            )

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
        tampered["result"]["body"] = "findings: none\nsummary: 1 high / 0 medium / 0 low\n"
        CACHE.atomic_write(record_path, tampered)
        with self.assertRaises(CACHE.CacheError):
            CACHE.command_lookup(argparse.Namespace(**common))

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

    def test_state_counts_only_changed_reviewed_state(self) -> None:
        def advance(reviewed: str) -> dict[str, object]:
            output = io.StringIO()
            args = argparse.Namespace(
                repo_root=str(self.root),
                cache_dir=".deep-review-cache",
                scope_key=digest("scope-key"),
                reviewed_state_hash=reviewed,
                status="blocked",
                reuse_used=False,
                targeted_rerun_used=False,
            )
            with redirect_stdout(output):
                CACHE.command_state(args)
            return json.loads(output.getvalue())

        first = advance(digest("one"))
        unchanged = advance(digest("one"))
        second = advance(digest("two"))
        third = advance(digest("three"))
        self.assertEqual(first["iteration"], 1)
        self.assertEqual(unchanged["iteration"], 1)
        self.assertEqual(second["iteration"], 2)
        self.assertEqual(third["iteration"], 3)
        with self.assertRaises(CACHE.CacheError):
            advance(digest("four"))

        (self.cache_dir / "state.json").write_text("{broken", encoding="utf-8")
        with self.assertRaises(CACHE.CacheError):
            advance(digest("five"))

    def test_clear_removes_only_validated_cache_directory(self) -> None:
        marker = self.root / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        CACHE.atomic_write(self.cache_dir / "state.json", {"value": 1})
        CACHE.command_clear(
            argparse.Namespace(repo_root=str(self.root), cache_dir=".deep-review-cache")
        )
        self.assertFalse(self.cache_dir.exists())
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
