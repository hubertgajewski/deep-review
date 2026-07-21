from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile
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
            "architecture", "ci", "code", "docs", "groovy", "java", "javascript", "kotlin",
            "project-checklist", "python", "security", "simplification", "swift", "typescript"
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
        self.assertEqual(len(roster), 14)
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

    def test_gitlab_merge_request_shorthand_contract(self) -> None:
        scope = (SKILL / "references" / "scope-resolution.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        installation = (ROOT / "docs" / "installation.md").read_text(encoding="utf-8")
        gitlab_pattern = re.compile(r"^!(\d+)(\s+(.+))?$")
        inferred_pattern = re.compile(r"^#?(\d+)(\s+(.+))?$")

        self.assertIn(r"^!(\d+)(\s+(.+))?$", scope)
        self.assertIn(r"^#?(\d+)(\s+(.+))?$", scope)
        self.assertIn("equivalent to explicit `--gitlab-mr N`", scope)
        self.assertIn("sets the provider to GitLab", scope)
        self.assertIn("consider only remotes recognized as that provider", scope)
        self.assertIn("no matching remote exists or more than one remains", scope)
        self.assertIn("Never reinterpret invalid `#` or `!` shorthand", scope)
        self.assertIn(r"^\S+!\d+(\s+.*)?$", scope)
        self.assertIn("Extract `--focus TEXT` and `--full-review` modifiers before matching", scope)
        self.assertIn("duplicate reviewer focus", scope)
        self.assertIn("For every remote selector matched by rule 1, 4, or 5", scope)
        self.assertIn("require the change-number digit string to contain at least one non-zero digit", scope)
        self.assertIn("without continuing to path, Git-ref, or freeform-focus rules", scope)

        self.assertEqual(gitlab_pattern.fullmatch("!123").group(1), "123")
        self.assertEqual(gitlab_pattern.fullmatch("!123 retry behavior").group(3), "retry behavior")
        for invalid in ("!", "!abc", "!-1", "group/project!123"):
            self.assertIsNone(gitlab_pattern.fullmatch(invalid), invalid)
        for compatible, number in (("123", "123"), ("#123", "123"), ("001", "001"), ("#001", "001")):
            self.assertEqual(inferred_pattern.fullmatch(compatible).group(1), number)
        for invalid_zero in ("0", "00", "#0", "#00", "!0", "!00"):
            pattern = gitlab_pattern if invalid_zero.startswith("!") else inferred_pattern
            captured = pattern.fullmatch(invalid_zero).group(1)
            self.assertFalse(any(digit != "0" for digit in captured), invalid_zero)

        for example in (
            "Use deep-review #123", "Use deep-review !123",
            "/deep-review #123", "/deep-review !123",
            "$deep-review #123", "$deep-review !123",
            "@skills:deep-review #123", "@skills:deep-review !123",
            "@deep-review #123", "@deep-review !123",
        ):
            self.assertIn(example, readme)
            self.assertIn(example, installation)
        for document in (readme, installation):
            self.assertIn("`#123` is the familiar GitHub-style reference", document)
            self.assertIn("`!123` is GitLab merge-request notation", document)

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
            self.assertIn("retry the complete metadata-object-path-preflight-diff-metadata", text)
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
        self.assertIn('git diff --find-renames --find-copies-harder "$BASE_SHA...$HEAD_SHA"', github)
        self.assertIn('git diff --find-renames --find-copies-harder "$BASE_SHA" "$HEAD_SHA"', gitlab)
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

    def test_denied_paths_are_preflighted_before_content_in_every_mode(self) -> None:
        main = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        scope = (SKILL / "references" / "scope-resolution.md").read_text(encoding="utf-8")
        orchestration = (SKILL / "references" / "orchestration.md").read_text(encoding="utf-8")
        user_config = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")

        self.assertLess(main.index("metadata-only path preflight"), main.index("Only after preflight succeeds"))
        self.assertIn("rename/copy source and destination", main)
        self.assertIn("never reduce a mixed scope to an allowed subset", main)

        local_metadata = "git diff --name-status -z --find-renames --find-copies-harder HEAD"
        local_content = "retrieve the tracked content diff"
        self.assertLess(scope.index(local_metadata), scope.index(local_content))
        self.assertIn("git ls-files --others --exclude-standard -z", scope)
        self.assertIn("newly appearing denied path", scope)
        self.assertIn("byte-for-byte", scope)

        path_enumeration = "enumerate entry names and link-aware file metadata"
        path_preflight = "Run the complete path preflight over every enumerated path"
        primary_capture = "## Primary input capture"
        immutable_context = "## Immutable review context"
        path_binary_read = "perform binary detection"
        path_synthetic_hunk = "construct synthetic hunks"
        self.assertLess(scope.index(path_enumeration), scope.index(path_preflight))
        self.assertLess(scope.index(path_preflight), scope.index(primary_capture))
        self.assertLess(scope.index(primary_capture), scope.index(immutable_context))
        self.assertLess(scope.index(primary_capture), scope.index(path_binary_read, scope.index(primary_capture)))
        self.assertLess(scope.index(primary_capture), scope.index(path_synthetic_hunk, scope.index(primary_capture)))
        self.assertIn("mutable primary inputs only", scope)
        self.assertIn("platform secure-open adapter", scope)
        self.assertIn("anchored to a repository-root capability", scope)
        self.assertIn("POSIX adapters", scope)
        self.assertIn("Windows adapters", scope)
        self.assertIn("reparse points in every path component", scope)
        self.assertIn("fail scope resolution before reading any primary bytes", scope)
        self.assertIn("post-open metadata has the same stable file identity", scope)
        self.assertIn("fails the complete atomic scope", scope)
        self.assertIn("never fall back to a path-based reopen", scope)
        self.assertIn("Primary capture never refers to a snapshot root", scope)
        self.assertIn("anchored to the snapshot-root capability", scope)
        self.assertIn("never fall back to an ordinary path open", scope)
        self.assertIn("Primary inputs are never reopened here", scope)
        self.assertIn("Trusted extension references were separately validated", scope)
        self.assertNotIn("file descriptor-relative to an anchored", scope)

        range_metadata = (
            "git diff --name-status -z --find-renames --find-copies-harder "
            "<validated-immutable-range>"
        )
        range_content = "git diff --find-renames --find-copies-harder <validated-immutable-range>"
        self.assertLess(scope.index(range_metadata), scope.index(range_content))
        self.assertIn("both source and destination", scope)
        self.assertIn("malformed, truncated, or unknown status record fails scope resolution", scope)
        self.assertIn("three-dot range's merge base", scope)
        self.assertIn("Treat the manifest as one atomic scope", scope)
        self.assertIn("before any candidate content reaches tool output or model context", scope)
        self.assertIn("before retrieving content diffs", scope)
        self.assertIn("Only after the complete path preflight and content retrieval succeed", scope)

        provider_commands = {
            "github": (
                'git diff --name-status -z --find-renames --find-copies-harder '
                '"$BASE_SHA...$HEAD_SHA"',
                'git diff --find-renames --find-copies-harder "$BASE_SHA...$HEAD_SHA"',
            ),
            "gitlab": (
                'git diff --name-status -z --find-renames --find-copies-harder '
                '"$BASE_SHA" "$HEAD_SHA"',
                'git diff --find-renames --find-copies-harder "$BASE_SHA" "$HEAD_SHA"',
            ),
        }
        for provider, (metadata_command, content_command) in provider_commands.items():
            text = (SKILL / "references" / "providers" / f"{provider}.md").read_text(
                encoding="utf-8"
            )
            self.assertLess(text.index(metadata_command), text.index(content_command))
            self.assertIn("including both sides of every rename or copy", text)
            self.assertIn("Any path-preflight rejection terminates immediately", text)
        github = (SKILL / "references" / "providers" / "github.md").read_text(encoding="utf-8")
        self.assertIn('git merge-base "$BASE_SHA" "$HEAD_SHA"', github)
        self.assertIn("use its tree as the effective diff base", github)

        self.assertIn("No trigger, snapshot, prompt, bucket, or dependency hash", orchestration)
        self.assertIn("before content diff retrieval", orchestration)
        self.assertIn("One denied path fails the entire scope", user_config)
        self.assertIn("allowed/denied mixed change", user_config)

    def test_git_preflight_detects_unchanged_copy_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Deep Review Tests"], cwd=repository, check=True)
            (repository / "source.txt").write_text("copied content\n", encoding="utf-8")
            subprocess.run(["git", "add", "source.txt"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=repository, check=True)
            (repository / "copy.txt").write_text("copied content\n", encoding="utf-8")
            subprocess.run(["git", "add", "copy.txt"], cwd=repository, check=True)

            ordinary = subprocess.run(
                ["git", "diff", "--name-status", "--find-copies", "HEAD"],
                cwd=repository, check=True, capture_output=True, text=True,
            ).stdout
            harder = subprocess.run(
                ["git", "diff", "--name-status", "--find-copies-harder", "HEAD"],
                cwd=repository, check=True, capture_output=True, text=True,
            ).stdout

            self.assertEqual(ordinary, "A\tcopy.txt\n")
            self.assertEqual(harder, "C100\tsource.txt\tcopy.txt\n")

    def test_local_content_diff_uses_literal_pathspecs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Deep Review Tests"], cwd=repository, check=True)
            magic_name = ":(literal)name.txt"
            (repository / magic_name).write_text("before\n", encoding="utf-8")
            subprocess.run(
                ["git", "--literal-pathspecs", "add", "--", magic_name],
                cwd=repository, check=True,
            )
            subprocess.run(["git", "commit", "-qm", "base"], cwd=repository, check=True)
            (repository / magic_name).write_text("after\n", encoding="utf-8")

            interpreted = subprocess.run(
                ["git", "diff", "HEAD", "--", magic_name],
                cwd=repository, check=True, capture_output=True, text=True,
            ).stdout
            literal = subprocess.run(
                ["git", "--literal-pathspecs", "diff", "HEAD", "--", magic_name],
                cwd=repository, check=True, capture_output=True, text=True,
            ).stdout

            self.assertEqual(interpreted, "")
            self.assertIn(f"a/{magic_name}", literal)
            scope = (SKILL / "references" / "scope-resolution.md").read_text(encoding="utf-8")
            self.assertIn("git --literal-pathspecs diff", scope)

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
            "java": (
                "java.null-unboxing",
                "java.unchecked-cast",
                "java.unsafe-optional-get",
                "java.equals-hashcode-contract",
                "java.autocloseable-lifetime",
                "java.unsafe-finally",
            ),
            "javascript": (
                "javascript.unsafe-optional-chaining",
                "javascript.loss-of-precision",
                "javascript.unsafe-finally",
                "javascript.async-promise-executor",
                "javascript.async-foreach",
                "javascript.unhandled-promise",
            ),
            "groovy": (
                "groovy.elvis-falsy-default",
                "groovy.unsafe-safe-navigation",
                "groovy.gstring-map-key",
                "groovy.equality-identity-confusion",
                "groovy.regex-find-vs-match",
                "groovy.division-semantics",
            ),
            "kotlin": (
                "kotlin.unsafe-not-null-assertion",
                "kotlin.platform-type-nullability",
                "kotlin.array-equality",
                "kotlin.shallow-data-class-copy",
                "kotlin.swallowed-cancellation",
                "kotlin.run-blocking-in-suspend",
            ),
        }
        expected_patterns = {
            "typescript": ("**/*.ts", "**/*.tsx", "**/*.mts", "**/*.cts"),
            "python": ("**/*.py", "**/*.pyi"),
            "swift": ("**/*.swift", "Package.swift"),
            "java": ("**/*.java",),
            "javascript": ("**/*.js", "**/*.jsx", "**/*.mjs", "**/*.cjs"),
            "groovy": ("**/*.groovy", "**/*.gradle", "Jenkinsfile"),
            "kotlin": ("**/*.kt", "**/*.kts"),
        }
        user_config = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
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
                self.assertIn(rule_id, user_config)

        fragments = list((SKILL / "references" / "language-rules").glob("*/*.md"))
        self.assertEqual(len(fragments), len(seen))

    def test_language_prompts_are_repository_neutral_and_exclude_general_dead_code(self) -> None:
        paths = [
            SKILL / "references" / "agents" / f"{language}.md"
            for language in ("typescript", "python", "swift", "java", "javascript", "groovy", "kotlin")
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

        for language in ("typescript", "python", "swift", "java", "javascript", "groovy", "kotlin"):
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
        user_config = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")

        for token in (
            "[language_agents]", "[language_rules]", "disabled = []", "unknown agent names",
            "unknown rule IDs", "duplicates", "aggregate `incomplete`"
        ):
            self.assertIn(token, config)
        for language in ("typescript", "python", "swift", "java", "javascript", "groovy", "kotlin"):
            self.assertIn(f"`{language}`", config)
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
            "typescript.no-explicit-any", "python.mutable-default", "swift.actor-isolation",
            "java.null-unboxing", "javascript.unsafe-optional-chaining",
            "groovy.elvis-falsy-default", "kotlin.unsafe-not-null-assertion"
        ):
            self.assertIn(rule_id, user_config)

        scope = (SKILL / "references" / "scope-resolution.md").read_text(encoding="utf-8")
        self.assertIn("After snapshot materialization", scope)
        self.assertIn("Reject denied components, traversal", scope)
        self.assertIn("unchanged credential-bearing path", scope)
        self.assertIn("all agents, retries, tracing, and dependency hashes complete", scope)
        self.assertIn("Trusted-policy reads never use the reviewed-head snapshot root", config)

    def test_synthetic_extension_fixture_is_complete(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "consumer" / ".deep-review"
        self.assertTrue((fixture / "config.toml").is_file())
        self.assertTrue((fixture / "checklist.md").is_file())
        agent = (fixture / "agents" / "x-example-cobol.md").read_text(encoding="utf-8")
        for field in (
            "name:", "domain:", "applies_to:", "prompt_scope:", "output_schema:", "blocking:", "references:"
        ):
            self.assertIn(field, agent)
        self.assertIn('name: x-example-cobol', agent)
        self.assertIn('domain: x-example-cobol-data-layout', agent)
        self.assertIn('docs/cobol-guidelines.md', agent)
        self.assertTrue((fixture.parent / "docs" / "cobol-guidelines.md").is_file())
        self.assertTrue((fixture.parent / "src" / "batch" / "CustomerReport.cbl").is_file())

        config = (SKILL / "references" / "configuration.md").read_text(encoding="utf-8")
        self.assertIn("name: x-example-cobol", config)
        self.assertIn("domain: x-example-cobol-data-layout", config)
        self.assertIn("`x-` prefix is reserved for consumer extensions", config)
        self.assertNotRegex(config, r"(?m)^name: java$")

    def test_user_and_governance_documentation_is_present(self) -> None:
        for relative in (
            "README.md", "LICENSE", "CONTRIBUTING.md", "SECURITY.md", "AGENTS.md", "CLAUDE.md",
            "docs/installation.md", "docs/configuration.md", "docs/maintainers.md",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        maintainers = (ROOT / "docs" / "maintainers.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        installation = (ROOT / "docs" / "installation.md").read_text(encoding="utf-8")
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("review-only Agent Skill", readme)
        self.assertIn("does not edit consumer source files", readme)
        self.assertNotIn("Disabling automatic pipelines", readme)
        for invocation in (
            "/deep-review --base main", "$deep-review --base main",
            "@skills:deep-review --base main", "@deep-review --base main",
        ):
            self.assertIn(invocation, readme)
            self.assertIn(invocation, installation)
        self.assertIn("Disable automatic pipelines", maintainers)
        self.assertIn("user-facing installation", agents)
        self.assertIn("@AGENTS.md", claude)
        self.assertIn("MIT License", license_text)
        self.assertIn("Copyright (c) 2026 Hubert Gajewski", license_text)
        self.assertIn("Turn on confidentiality", security)
        self.assertNotIn("This issue is confidential", security)

    def test_installation_clients_are_alphabetical_and_complete(self) -> None:
        installation = (ROOT / "docs" / "installation.md").read_text(encoding="utf-8")
        table = installation.split("## AI client locations", 1)[1].split(
            "### Enterprise and system locations", 1
        )[0]
        clients = [
            line.split("|", 2)[1].strip()
            for line in table.splitlines()
            if line.startswith("| ") and not line.startswith("| AI client") and not line.startswith("| ---")
        ]
        self.assertEqual(clients, sorted(clients, key=str.casefold))
        self.assertEqual(len(clients), 20)
        for expected in (
            "Amp", "Claude Code CLI and Claude Desktop", "Cline", "Codex CLI, IDE, and desktop",
            "Cursor", "Devin", "Gemini CLI", "GitHub Copilot CLI, VS Code, and coding agent",
            "Google Antigravity", "Goose", "Grok Build CLI", "JetBrains Junie", "Kiro",
            "Mistral Vibe Code", "OpenCode", "OpenHands", "Qwen Code", "T3 Code", "Warp",
            "Windsurf Cascade",
        ):
            self.assertIn(expected, clients)

    def test_consumer_namespace_is_not_used_by_built_ins(self) -> None:
        config = (SKILL / "references" / "configuration.md").read_text(encoding="utf-8")
        contract = (SKILL / "references" / "agent-contract.md").read_text(encoding="utf-8")
        self.assertIn("Package-owned built-ins must never use it", contract)
        self.assertIn("`x-<owner>-<purpose>`", config)
        for path in (SKILL / "references" / "agents").glob("*.md"):
            name = re.search(r"(?m)^name: ([a-z0-9-]+)$", path.read_text(encoding="utf-8"))
            self.assertIsNotNone(name, path.name)
            assert name
            self.assertFalse(name.group(1).startswith("x-"), path.name)

    def test_extension_names_are_unique_independently_of_domains(self) -> None:
        config = (SKILL / "references" / "configuration.md").read_text(encoding="utf-8")
        contract = (SKILL / "references" / "agent-contract.md").read_text(encoding="utf-8")
        user_config = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")

        self.assertIn("two files cannot share a `name` even when their domains differ", config)
        self.assertIn("name duplicates another extension name, even when their domains differ", contract)
        self.assertIn("Duplicate extension names or domains", user_config)

    def test_javascript_promise_rule_precedence_is_explicit(self) -> None:
        rules = SKILL / "references" / "language-rules" / "javascript"
        unhandled = (rules / "unhandled-promise.md").read_text(encoding="utf-8")
        for specific in (
            "javascript.async-promise-executor",
            "javascript.async-foreach",
        ):
            self.assertIn(specific, unhandled)

    def test_kotlin_null_rule_precedence_is_explicit(self) -> None:
        agent = (SKILL / "references" / "agents" / "kotlin.md").read_text(encoding="utf-8")
        rules = SKILL / "references" / "language-rules" / "kotlin"
        assertion = (rules / "unsafe-not-null-assertion.md").read_text(encoding="utf-8")
        platform = (rules / "platform-type-nullability.md").read_text(encoding="utf-8")
        self.assertIn("kotlin.unsafe-not-null-assertion", agent)
        self.assertIn("kotlin.platform-type-nullability", agent)
        self.assertIn("kotlin.platform-type-nullability", assertion)
        self.assertIn("kotlin.unsafe-not-null-assertion", platform)

    def test_groovy_kotlin_dsl_and_jenkins_ownership_is_explicit(self) -> None:
        config = (SKILL / "references" / "configuration.md").read_text(encoding="utf-8")
        contract = (SKILL / "references" / "agent-contract.md").read_text(encoding="utf-8")
        orchestration = (SKILL / "references" / "orchestration.md").read_text(encoding="utf-8")
        groovy = (SKILL / "references" / "agents" / "groovy.md").read_text(encoding="utf-8")
        kotlin = (SKILL / "references" / "agents" / "kotlin.md").read_text(encoding="utf-8")
        ci = (SKILL / "references" / "agents" / "ci.md").read_text(encoding="utf-8")
        ci_trigger = next(line for line in config.splitlines() if line.startswith("ci = "))
        self.assertIn('"Jenkinsfile"', ci_trigger)
        self.assertIn('"**/*.groovy"', ci_trigger)
        for language in ("groovy", "kotlin"):
            self.assertIn(f"`{language}`", config)
        self.assertIn("equals a built-in agent name or language-rule namespace", contract)
        self.assertIn("`build.gradle` as Groovy", orchestration)
        self.assertIn("`build.gradle.kts` as Kotlin", orchestration)
        self.assertIn("Any changed `**/*.groovy` path dispatches both", orchestration)
        self.assertIn("A Groovy suffix alone is not evidence", ci)
        self.assertIn("custom Pipeline Script Paths", config)
        self.assertIn("non-Groovy Shared Library resources", config)
        for agent in (groovy, kotlin):
            self.assertIn("code reviewer", agent)
            self.assertIn("security reviewer", agent)
            self.assertIn("CI reviewer", agent)
        self.assertIn("Jenkins Pipelines", ci)

    def test_cache_is_ignored(self) -> None:
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".deep-review-cache/", ignore)


if __name__ == "__main__":
    unittest.main()
