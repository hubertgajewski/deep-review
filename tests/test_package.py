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
            "architecture", "ci", "code", "docs", "project-checklist", "python", "security",
            "simplification", "swift", "typescript"
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
        self.assertEqual(len(roster), 10)
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
            self.assertIn("already fetched and verified", text)
            self.assertNotIn("when `headRefOid` is absent locally", text)
            self.assertNotIn("when the recorded head SHA is absent locally", text)
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

    def test_language_rule_catalogs_are_complete_and_unique(self) -> None:
        expected = {
            "typescript": (
                "typescript.no-explicit-any",
                "typescript.unsafe-type-assertion",
                "typescript.unsafe-non-null-assertion",
                "typescript.non-exhaustive-union",
                "typescript.unhandled-promise",
            ),
            "python": (
                "python.mutable-default",
                "python.bare-exception-handler",
                "python.runtime-assert",
            ),
            "swift": (
                "swift.unsafe-force-unwrap",
                "swift.unsafe-force-cast",
                "swift.actor-isolation",
                "swift.sendable-boundary",
                "swift.unstructured-task-lifetime",
                "swift.continuation-resume",
            ),
        }
        expected_patterns = {
            "typescript": ("**/*.ts", "**/*.tsx", "**/*.mts", "**/*.cts"),
            "python": ("**/*.py", "**/*.pyi"),
            "swift": ("**/*.swift", "Package.swift"),
        }
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        orchestration = (SKILL / "references" / "orchestration.md").read_text(encoding="utf-8")
        seen: set[str] = set()
        for language, rule_ids in expected.items():
            agent = (SKILL / "references" / "agents" / f"{language}.md").read_text(encoding="utf-8")
            patterns = tuple(re.findall(r'^  - "([^"]+)"$', agent, re.MULTILINE))
            self.assertEqual(patterns, expected_patterns[language])
            for pattern in patterns:
                self.assertIn(f"`{pattern}`", orchestration)
            declared = tuple(re.findall(rf"^  - ({language}\.[a-z0-9-]+)$", agent, re.MULTILINE))
            self.assertEqual(declared, rule_ids)
            for rule_id in rule_ids:
                self.assertNotIn(rule_id, seen)
                seen.add(rule_id)
                suffix = rule_id.split(".", 1)[1]
                fragment = SKILL / "references" / "language-rules" / language / f"{suffix}.md"
                self.assertTrue(fragment.is_file(), rule_id)
                text = fragment.read_text(encoding="utf-8")
                self.assertRegex(text, rf"(?m)^rule_id: {re.escape(rule_id)}$")
                self.assertIn("Public reference", text)
                self.assertIn("Recommend", text)
                self.assertIn(rule_id, readme)

        fragments = list((SKILL / "references" / "language-rules").glob("*/*.md"))
        self.assertEqual(len(fragments), len(seen))

    def test_language_prompts_are_repository_neutral_and_exclude_general_dead_code(self) -> None:
        paths = [
            SKILL / "references" / "agents" / f"{language}.md"
            for language in ("typescript", "python", "swift")
        ]
        paths.extend((SKILL / "references" / "language-rules").glob("*/*.md"))
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths).lower()
        for repository_term in ("orwellstat", "meow & purr", "meowandpurr", "playwright", "bruno"):
            self.assertNotIn(repository_term, combined)

        swift = "\n".join(
            path.read_text(encoding="utf-8")
            for path in paths
            if path.name == "swift.md" or "language-rules/swift" in path.as_posix()
        ).lower()
        for platform_term in (
            "swiftui", "webkit", "xcode", "human interface guidelines", "application sandbox",
            "localization", "project verification"
        ):
            self.assertNotIn(platform_term, swift)

        for language in ("typescript", "python", "swift"):
            agent = (SKILL / "references" / "agents" / f"{language}.md").read_text(encoding="utf-8")
            self.assertIn("dead imports", agent)
            self.assertRegex(agent, r"unused (?:variables or )?symbols")

        fragments = "\n".join(
            path.read_text(encoding="utf-8").lower()
            for path in (SKILL / "references" / "language-rules").glob("*/*.md")
        )
        self.assertNotIn("unused import", fragments)
        self.assertNotIn("unused variable", fragments)

    def test_language_configuration_and_dispatch_contracts_are_explicit(self) -> None:
        config = (SKILL / "references" / "configuration.md").read_text(encoding="utf-8")
        orchestration = (SKILL / "references" / "orchestration.md").read_text(encoding="utf-8")
        output = (SKILL / "references" / "output-schemas.md").read_text(encoding="utf-8")
        main = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        for token in (
            "[language_agents]", "[language_rules]", "disabled = []", "unknown agent names",
            "unknown rule IDs", "duplicates", "aggregate `incomplete`"
        ):
            self.assertIn(token, config)
        self.assertIn("only the enabled rule fragments", orchestration)
        self.assertIn("Never include a disabled fragment", orchestration)
        self.assertIn("--allowed-category", orchestration)
        self.assertIn("Dispatch each matching language at most once", main)
        self.assertIn("SKIPPED: language trigger did not match", main)
        self.assertIn("disabled or unknown rule category is malformed", main)
        self.assertIn("exact namespaced rule IDs enabled", output)
        self.assertIn("config_hash", orchestration)
        self.assertIn("agent_prompt_hash", orchestration)
        for rule_id in (
            "typescript.no-explicit-any", "python.mutable-default", "swift.actor-isolation"
        ):
            self.assertIn(rule_id, readme)

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
