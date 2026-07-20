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
        main = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        roster_pattern = re.compile(
            r"^\| (?P<name>[a-z-]+) \| \[[^]]+\]\(references/agents/(?P=name)\.md\) "
            r"\| [^|]+ \| (?P<scope>full|matched) \| (?P<schema>hml|checklist) \|$",
            re.MULTILINE,
        )
        roster = {
            match.group("name"): (match.group("scope"), match.group("schema"))
            for match in roster_pattern.finditer(main)
        }
        agents = {path.stem: path for path in (SKILL / "references" / "agents").glob("*.md")}
        self.assertEqual(set(roster), set(agents))
        self.assertEqual(len(roster), 7)
        for name, (scope, schema) in roster.items():
            agent = agents[name]
            text = agent.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"), agent.name)
            declared_name = re.search(r"^name: ([a-z-]+)$", text, re.MULTILINE)
            declared_scope = re.search(r"^prompt_scope: (full|matched)$", text, re.MULTILINE)
            declared_schema = re.search(r"^output_schema: (hml|checklist)$", text, re.MULTILINE)
            self.assertIsNotNone(declared_name, agent.name)
            self.assertIsNotNone(declared_scope, agent.name)
            self.assertIsNotNone(declared_schema, agent.name)
            assert declared_name and declared_scope and declared_schema
            self.assertEqual(declared_name.group(1), name)
            self.assertEqual(declared_scope.group(1), scope)
            self.assertEqual(declared_schema.group(1), schema)

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
        self.assertIn("immutable context root", scope)
        self.assertIn("--final-guard-run", orchestration)
        self.assertIn("--start-new-sequence", orchestration)
        self.assertIn("--expected-generation", orchestration)
        self.assertIn("scope_key", orchestration)

    def test_large_diff_and_restricted_environment_contracts_are_explicit(self) -> None:
        main = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        orchestration = (SKILL / "references" / "orchestration.md").read_text(encoding="utf-8")
        for bucket in ("high-risk", "normal", "low-risk", "generated"):
            self.assertIn(bucket, main)
        self.assertIn("--full-review", main)
        self.assertIn("Effective `full_review = true`", orchestration)
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
            self.assertIn("temporary detached worktree", text)
            self.assertIn("metadata again", text)
            self.assertIn("retry the complete metadata-object-diff-metadata", text)
            self.assertIn("second mismatch fails scope resolution", text)
            self.assertIn("verified immutable", text)
            self.assertIn("never use a change-number-based patch", text)
            self.assertIn("git check-ref-format --branch", text)
            self.assertIn("full object IDs", text)
        self.assertIn("original and effective character counts", scope)

        github = (SKILL / "references" / "providers" / "github.md").read_text(encoding="utf-8")
        gitlab = (SKILL / "references" / "providers" / "gitlab.md").read_text(encoding="utf-8")
        self.assertIn('git diff "$BASE_SHA...$HEAD_SHA"', github)
        self.assertIn('git diff "$BASE_SHA" "$HEAD_SHA"', gitlab)
        self.assertNotIn("gh pr diff", github)
        self.assertNotIn("glab mr diff", gitlab)

    def test_configuration_safety_contracts_are_explicit(self) -> None:
        config = (SKILL / "references" / "configuration.md").read_text(encoding="utf-8")
        contract = (SKILL / "references" / "agent-contract.md").read_text(encoding="utf-8")
        self.assertIn("triggers.project_checklist", config)
        self.assertIn("CHECKLIST_FAIL", config)
        self.assertIn(".env*", config)
        self.assertIn("client_secret.json", config)
        self.assertIn("Local and path reviews use committed `HEAD`", config)
        self.assertIn("full_review = false", config)
        self.assertIn("project_checklist = []", config)
        self.assertIn("orchestrator-owned transport metadata", contract)
        self.assertIn("duplicates another extension domain", contract)

        scope = (SKILL / "references" / "scope-resolution.md").read_text(encoding="utf-8")
        self.assertIn("Reject symlinks for every agent-readable", scope)
        self.assertIn("all agents, retries, tracing, and dependency hashes complete", scope)

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
