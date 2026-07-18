from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "deep-review"


class PackageTests(unittest.TestCase):
    def test_required_package_files_exist(self) -> None:
        required = [
            "SKILL.md",
            "agents/openai.yaml",
            "scripts/cache.py",
            "references/agent-contract.md",
            "references/configuration.md",
            "references/orchestration.md",
            "references/output-schemas.md",
            "references/scope-resolution.md",
            "references/providers/github.md",
            "references/providers/gitlab.md",
        ]
        required.extend(f"references/agents/{name}.md" for name in (
            "architecture", "ci", "code", "docs", "project-checklist", "security", "simplification"
        ))
        for relative in required:
            self.assertTrue((SKILL / relative).is_file(), relative)

    def test_skill_is_concise_and_has_valid_frontmatter(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(text.splitlines()), 500)
        self.assertRegex(text, r"(?s)^---\nname: deep-review\ndescription: .+\n---\n")
        self.assertNotIn("TODO", text)

    def test_ui_metadata_mentions_skill(self) -> None:
        text = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "Deep Review"', text)
        self.assertIn("$deep-review", text)

    def test_core_agents_declare_fixed_schemas(self) -> None:
        agents = list((SKILL / "references" / "agents").glob("*.md"))
        self.assertEqual(len(agents), 7)
        for agent in agents:
            text = agent.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"), agent.name)
            schema = re.search(r"^output_schema: (hml|checklist)$", text, re.MULTILINE)
            self.assertIsNotNone(schema, agent.name)

    def test_scope_and_guard_contracts_are_explicit(self) -> None:
        scope = (SKILL / "references" / "scope-resolution.md").read_text(encoding="utf-8")
        orchestration = (SKILL / "references" / "orchestration.md").read_text(encoding="utf-8")
        main = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for token in ("--github-pr", "--gitlab-mr", "--base", "--range", "--path", "Freeform"):
            self.assertIn(token, scope)
        self.assertIn("three changed iterations", main)
        self.assertIn("disable reuse", orchestration)
        self.assertIn("metadata-only", orchestration)
        self.assertIn("description_hash", orchestration)
        self.assertIn("cache.py probe", orchestration)

    def test_large_diff_and_restricted_environment_contracts_are_explicit(self) -> None:
        main = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        orchestration = (SKILL / "references" / "orchestration.md").read_text(encoding="utf-8")
        for bucket in ("high-risk", "normal", "low-risk", "generated"):
            self.assertIn(bucket, main)
        self.assertIn("--full-review", main)
        self.assertIn("cannot produce `ready`", orchestration)
        self.assertIn("dispatch: serial fallback", main)
        self.assertIn("Do not run builds, tests, linters", main)

    def test_remote_context_and_drift_contracts_are_explicit(self) -> None:
        scope = (SKILL / "references" / "scope-resolution.md").read_text(encoding="utf-8")
        for provider in ("github", "gitlab"):
            text = (SKILL / "references" / "providers" / f"{provider}.md").read_text(encoding="utf-8")
            self.assertIn("description", text)
            self.assertIn("base drift: unverified", text)
            self.assertIn("git ls-remote", text)
            self.assertIn("Never substitute local changes", text)
        self.assertIn("original and effective character counts", scope)

    def test_synthetic_extension_fixture_is_complete(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "consumer" / ".deep-review"
        self.assertTrue((fixture / "config.toml").is_file())
        self.assertTrue((fixture / "checklist.md").is_file())
        agent = (fixture / "agents" / "java.md").read_text(encoding="utf-8")
        for field in (
            "name:", "domain:", "applies_to:", "prompt_scope:", "output_schema:", "blocking:", "references:"
        ):
            self.assertIn(field, agent)
        self.assertTrue((ROOT / "tests" / "fixtures" / "consumer" / "docs" / "java-guidelines.md").is_file())

    def test_cache_is_ignored(self) -> None:
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".deep-review-cache/", ignore)


if __name__ == "__main__":
    unittest.main()
