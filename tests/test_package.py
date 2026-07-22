from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "deep-review"


class PackageTests(unittest.TestCase):
    def test_required_package_files_exist(self) -> None:
        required = [
            ".claude-plugin/plugin.json",
            "CHANGELOG.md",
            "LICENSE",
            "README.md",
            "SKILL.md",
            "agents/openai.yaml",
            "scripts/cache.py",
            "scripts/process_result.py",
            "scripts/result_processing.py",
            "references/agent-contract.md",
            "references/configuration.md",
            "references/orchestration.md",
            "references/output-schemas.md",
            "references/prompt-budgets.md",
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

    def test_claude_plugin_package_is_complete_and_consistent(self) -> None:
        manifest_path = SKILL / ".claude-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertIsInstance(manifest, dict)
        self.assertEqual(
            set(manifest),
            {
                "$schema", "name", "displayName", "version", "description", "author",
                "homepage", "repository", "license", "keywords",
            },
        )
        self.assertEqual(
            manifest["$schema"],
            "https://json.schemastore.org/claude-code-plugin-manifest.json",
        )
        self.assertEqual(manifest["name"], SKILL.name)
        self.assertEqual(manifest["displayName"], "Deep Review")
        self.assertRegex(manifest["version"], r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
        self.assertIn("multi-agent code reviews", manifest["description"])
        self.assertEqual(manifest["author"], {"name": "Hubert Gajewski"})
        self.assertEqual(
            manifest["homepage"],
            "https://gitlab.com/hubertgajewski-ai/deep-review",
        )
        self.assertEqual(manifest["repository"], manifest["homepage"])
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(
            manifest["keywords"],
            ["code-review", "security", "git", "github", "gitlab"],
        )

        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        skill_name = re.search(r"(?m)^name: ([a-z0-9-]+)$", skill_text)
        self.assertIsNotNone(skill_name)
        assert skill_name is not None
        self.assertEqual(skill_name.group(1), manifest["name"])
        self.assertEqual(
            [path.relative_to(SKILL) for path in SKILL.rglob("SKILL.md")],
            [Path("SKILL.md")],
        )

        changelog = (SKILL / "CHANGELOG.md").read_text(encoding="utf-8")
        versions = re.findall(r"(?m)^## \[([^]]+)\] - \d{4}-\d{2}-\d{2}$", changelog)
        self.assertTrue(versions)
        self.assertEqual(versions[0], manifest["version"])
        self.assertEqual((SKILL / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())

        packaged_readme = (SKILL / "README.md").read_text(encoding="utf-8")
        for token in (
            "/plugin install deep-review@claude-community",
            "/deep-review:deep-review --base main",
            "/deep-review --base main",
            "canonical portable skill package",
        ):
            self.assertIn(token, packaged_readme)

    def test_claude_marketplace_documentation_covers_release_contract(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        installation = (ROOT / "docs" / "installation.md").read_text(encoding="utf-8")
        maintainers = (ROOT / "docs" / "maintainers.md").read_text(encoding="utf-8")

        for document in (readme, installation):
            for token in (
                "/plugin marketplace add anthropics/claude-plugins-community",
                "/plugin install deep-review@claude-community",
                "/deep-review:deep-review --base main",
                "/deep-review --base main",
            ):
                self.assertIn(token, document)
        for token in (
            "canonical vendor-neutral Agent Skill",
            "public plugin name `deep-review` is immutable",
            "claude plugin validate --strict skills/deep-review",
            "python3 -m unittest discover -s tests -v",
            "claude --plugin-dir ./skills/deep-review",
            "release_version=$(python3 -c",
            "git tag -a \"v$release_version\" origin/main",
            "https://platform.claude.com/plugins/submit",
            "skills/deep-review",
        ):
            self.assertIn(token, maintainers)

        pipeline = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        for token in (
            "prepare_claude_submission:",
            "CI_COMMIT_REF_PROTECTED == \"true\"",
            "GIT_DEPTH: \"0\"",
            "git cat-file -t \"$CI_COMMIT_TAG\"",
            "git rev-parse \"$CI_COMMIT_TAG^{commit}\"",
            "git fetch --no-tags origin \"refs/heads/main:refs/remotes/origin/main\"",
            "git merge-base --is-ancestor \"$CI_COMMIT_SHA\" origin/main",
            "claude plugin validate --strict skills/deep-review",
            "git archive --format=tar.gz --prefix=deep-review/",
            "deep-review-$CI_COMMIT_TAG.tar.gz.sha256",
        ):
            self.assertIn(token, pipeline)

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

    def test_max_iterations_contract_is_fixed_at_three(self) -> None:
        main = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        config = (SKILL / "references" / "configuration.md").read_text(encoding="utf-8")
        orchestration = (SKILL / "references" / "orchestration.md").read_text(encoding="utf-8")
        user_config = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")

        self.assertIn("fixed at exactly three", main)
        self.assertIn("omitted", config)
        self.assertIn("TOML integer `3`", config)
        invalid_values = (
            "Values `0`", "negative integers", "`1`", "`2`", "above `3`",
            "booleans", "strings", "floats", "arrays",
        )
        for invalid in invalid_values:
            self.assertIn(invalid, config)
        self.assertIn("before dispatch", config)
        self.assertIn("aggregation denominators", orchestration)
        self.assertIn("exhausted-sequence", orchestration)
        self.assertIn("iterations: <N>/3", main)
        self.assertIn("does not count as a fourth", user_config)

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

    def test_prompt_budgets_and_chunk_coverage_contract_is_explicit(self) -> None:
        main = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        config = (SKILL / "references" / "configuration.md").read_text(encoding="utf-8")
        scope = (SKILL / "references" / "scope-resolution.md").read_text(encoding="utf-8")
        orchestration = (SKILL / "references" / "orchestration.md").read_text(encoding="utf-8")
        budgets = (SKILL / "references" / "prompt-budgets.md").read_text(encoding="utf-8")
        schemas = (SKILL / "references" / "output-schemas.md").read_text(encoding="utf-8")
        user_config = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")

        constants = {
            name: int(value)
            for name, value in re.findall(
                r"^([A-Z][A-Z0-9_]+) = (\d+)$",
                budgets,
                re.MULTILINE,
            )
        }
        self.assertEqual(
            constants,
            {
                "DEFAULT_DESCRIPTION_MAX_CHARS": 12000,
                "ABSOLUTE_DESCRIPTION_MAX_CHARS": 20000,
                "PROMPT_MAX_UTF8_BYTES": 120000,
                "INLINE_PROMPT_MAX_UTF8_BYTES": 96000,
                "CONTEXT_READ_MAX_UTF8_BYTES": 12000,
                "CONTEXT_READ_TOTAL_MAX_UTF8_BYTES": 24000,
                "MAX_CONTEXT_READS_PER_CHUNK": 2,
                "MAX_MODEL_TURNS_PER_CHUNK_ATTEMPT": 3,
                "MAX_CHUNKS_PER_AGENT": 32,
                "MAX_CHUNKS_PER_REVIEW": 128,
                "MAX_MODEL_CALLS_PER_REVIEW": 256,
                "MAX_TOTAL_PROMPT_UTF8_BYTES": 12000000,
                "MAX_CONCURRENT_CHUNKS": 8,
                "RESULT_MAX_UTF8_BYTES": 12000,
                "AGGREGATE_RESULT_MAX_UTF8_BYTES": 96000,
                "CACHE_RECORD_MAX_UTF8_BYTES": 524288,
            },
        )
        self.assertGreater(constants["DEFAULT_DESCRIPTION_MAX_CHARS"], 0)
        self.assertLessEqual(
            constants["DEFAULT_DESCRIPTION_MAX_CHARS"],
            constants["ABSOLUTE_DESCRIPTION_MAX_CHARS"],
        )
        self.assertEqual(
            constants["MAX_MODEL_TURNS_PER_CHUNK_ATTEMPT"],
            constants["MAX_CONTEXT_READS_PER_CHUNK"] + 1,
        )
        self.assertLessEqual(
            constants["AGGREGATE_RESULT_MAX_UTF8_BYTES"],
            constants["PROMPT_MAX_UTF8_BYTES"],
        )
        for document in (main, config, user_config):
            self.assertIn("description_max_chars = 12000", document)
        self.assertIn("never means unlimited", budgets)
        self.assertIn("cannot increase or disable the absolute maximum", budgets)
        self.assertIn("before prompt sanitization or construction", budgets)
        self.assertIn("original", budgets)
        self.assertIn("effective", budgets)
        self.assertIn("description-limit: clamped", budgets)
        self.assertIn("clamped` plus `full", budgets)
        self.assertIn("clamped` plus `omitted", budgets)
        self.assertIn("exact UTF-8 bytes placed inside", budgets)
        self.assertIn("exact UTF-8 bytes propagated", scope)

        self.assertIn("exact model-visible input on every turn", budgets)
        self.assertIn("initially dispatched inline prompt", budgets)
        self.assertIn("Before every subsequent model call", budgets)
        self.assertIn("debit its full byte length from the cumulative review budget", budgets)
        self.assertIn("cannot meter tool results and complete turn input", budgets)
        self.assertIn("No consumer configuration may change these limits", budgets)
        self.assertIn("fixed prompt framing exceeds", budgets)
        self.assertIn("complete `CHANGED_FILES` manifest", budgets)
        self.assertIn("immutable base and head identities", budgets)
        self.assertIn("reviewed_state_hash", budgets)
        self.assertIn("Before any chunk dispatch, validate the complete review plan", budgets)
        self.assertIn("fixed-size queue", budgets)
        self.assertIn("dispatch none of its chunks", budgets)
        self.assertIn("reserve the worst case of two initial attempt turns", budgets)
        self.assertIn("Charge every reserved turn at the full `PROMPT_MAX_UTF8_BYTES`", budgets)
        self.assertIn("repeated conversation, prior model output, transport metadata", budgets)
        self.assertIn("Before every model call, atomically debit one call", budgets)
        self.assertIn("Every individual or merged result body", budgets)
        self.assertIn("deterministic non-model operations", budgets)
        self.assertIn("must not be interpolated into another model prompt", budgets)
        self.assertIn("Persistent cache reads and writes", budgets)

        chunk_steps = (
            "Keep complete file blocks together",
            "Split an oversized file at existing hunk boundaries",
            "Split an oversized hunk at diff-line boundaries",
            "Split a single oversized diff line only at a Unicode-code-point boundary",
        )
        positions = [budgets.index(step) for step in chunk_steps]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("greedy first-fit in canonical stream order", budgets)
        self.assertIn("contiguous, non-overlapping, and gap-free", budgets)
        self.assertIn("One huge file", orchestration)
        self.assertIn("Several huge files", orchestration)
        self.assertIn("Full-review mode uses the same chunker", orchestration)
        self.assertIn("Normal and high-risk content remains required", orchestration)

        self.assertIn("ordered required chunk manifest", budgets)
        self.assertIn("Retry only the failed chunk once", budgets)
        self.assertIn("Partial or semantically incomplete chunk results are not cached", budgets)
        self.assertIn("scoped_prompt_hash", budgets)
        self.assertIn("derived chunk plan is excluded to avoid a cycle", orchestration)
        self.assertIn("ordered chunk identities instead belong to `scoped_prompt_hash`", orchestration)
        self.assertIn("prompt-coverage: complete", budgets)
        self.assertIn("prompt-coverage: incomplete", budgets)
        self.assertIn("never `ready`", budgets)
        self.assertIn("defines no bounded synthesis protocol", budgets)
        self.assertIn("more than one chunk is always semantically incomplete", budgets)
        self.assertIn("unsynthesized multi-chunk result", budgets)
        self.assertIn("required chunk", schemas)

        workflow_steps = [
            int(number)
            for number in re.findall(r"^### (\d+)\.", main, re.MULTILINE)
        ]
        self.assertEqual(workflow_steps, list(range(1, 10)))
        self.assertNotIn("### 4b.", main)

        cache_script = (SKILL / "scripts" / "cache.py").read_text(encoding="utf-8")
        result_script = (SKILL / "scripts" / "result_processing.py").read_text(
            encoding="utf-8"
        )
        for name, source in (
            ("RESULT_MAX_UTF8_BYTES", result_script),
            ("CACHE_RECORD_MAX_UTF8_BYTES", cache_script),
        ):
            match = re.search(rf"^{name} = ([\d_]+)$", source, re.MULTILINE)
            self.assertIsNotNone(match)
            assert match is not None
            self.assertEqual(int(match.group(1).replace("_", "")), constants[name])

    def test_remote_context_and_drift_contracts_are_explicit(self) -> None:
        scope = (SKILL / "references" / "scope-resolution.md").read_text(encoding="utf-8")
        for provider in ("github", "gitlab"):
            text = (SKILL / "references" / "providers" / f"{provider}.md").read_text(encoding="utf-8")
            self.assertIn("description", text)
            self.assertIn("base drift: unverified", text)
            self.assertIn("git ls-remote", text)
            self.assertIn("Never substitute local changes", text)
            self.assertIn("orchestrator-owned safe projection", text)
            self.assertIn("shared Remote evidence transport", text)
            self.assertIn("isolated blobless store", text)
            self.assertIn("exact-object streaming capability", text)
            self.assertIn("untouched HTTP response", text)
            self.assertIn("retained complete logical manifest", text)
            self.assertIn("metadata again", text)
            self.assertIn("retry the complete metadata-object-path-preflight-diff-metadata", text)
            self.assertIn("second mismatch fails scope resolution", text)
            self.assertIn("verified immutable", text)
            self.assertIn("never use a change-number-based patch", text)
            self.assertIn("git check-ref-format --branch", text)
            self.assertIn("exact-object transport", text)
            self.assertNotIn("when `headRefOid` is absent locally", text)
            self.assertNotIn("when the recorded head SHA is absent locally", text)
        self.assertIn("original and effective character counts", scope)

        github = (SKILL / "references" / "providers" / "github.md").read_text(encoding="utf-8")
        gitlab = (SKILL / "references" / "providers" / "gitlab.md").read_text(encoding="utf-8")
        self.assertIn('verified immutable range `"$BASE_SHA...$HEAD_SHA"`', github)
        self.assertIn('verified immutable range `"$BASE_SHA" "$HEAD_SHA"`', gitlab)
        self.assertIn("GET /repos/{owner}/{repo}/git/blobs/{file_sha}", github)
        self.assertIn("Accept: application/vnd.github.raw+json", github)
        self.assertIn(
            "GET /api/v4/projects/{url-encoded-project}/repository/blobs/{sha}/raw",
            gitlab,
        )
        self.assertIn("diff_refs.start_sha", gitlab)
        self.assertIn("recorded start SHA", gitlab)
        self.assertNotIn("\nrefs/heads/", github)
        self.assertNotIn("\nrefs/heads/", gitlab)
        self.assertNotIn("\nrefs/pull/", github)
        self.assertNotIn("\nrefs/merge-requests/", gitlab)
        for text in (github, gitlab):
            self.assertIn("A safety-ceiling failure does the same", text)
            self.assertIn("bounded raw-blob retrieval", text)
        self.assertNotIn("gh pr diff", github)
        self.assertNotIn("glab mr diff", gitlab)
        self.assertIn("## Remote evidence transport", scope)
        self.assertIn("Use the raw-diff, relationship, hunk, gitlink", scope)
        self.assertIn("one authenticated exact-object byte stream", scope)
        self.assertIn("exact-object streaming capability", scope)
        self.assertIn("Require status `200`", scope)
        self.assertIn("reject cross-origin redirects", scope)
        self.assertIn("without adapter buffering, decoding, logging", scope)

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

    def test_credential_redaction_contract_is_package_wide(self) -> None:
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        contract = (SKILL / "references" / "agent-contract.md").read_text(encoding="utf-8")
        security = (SKILL / "references" / "agents" / "security.md").read_text(
            encoding="utf-8"
        )
        output = (SKILL / "references" / "output-schemas.md").read_text(
            encoding="utf-8"
        )
        budgets = (SKILL / "references" / "prompt-budgets.md").read_text(
            encoding="utf-8"
        )
        orchestration = (SKILL / "references" / "orchestration.md").read_text(
            encoding="utf-8"
        )
        user_config = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
        cache_script = (SKILL / "scripts" / "cache.py").read_text(encoding="utf-8")
        processor = (SKILL / "scripts" / "process_result.py").read_text(encoding="utf-8")
        result_processing = (SKILL / "scripts" / "result_processing.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("Never reproduce a complete credential", contract)
        self.assertIn("Never quote or partially reproduce", security)
        self.assertIn("every built-in and consumer extension result", output)
        self.assertIn("Only the redacted body", output)
        self.assertIn(
            "without a command argument, log entry, diagnostic, or temporary file",
            budgets,
        )
        self.assertIn("scripts/process_result.py", skill)
        self.assertIn("consumer-extension output", orchestration)
        self.assertIn("not a general-purpose secret scanner", user_config)
        self.assertIn("Do not restore it from an untrusted CI artifact", user_config)
        self.assertNotIn('"process-result"', cache_script)
        self.assertIn("from result_processing import", cache_script)
        self.assertIn("process_result_body", processor)
        self.assertIn("def process_result_body", result_processing)

    def test_effective_blocking_policy_is_consistent_across_contracts(self) -> None:
        config = (SKILL / "references" / "configuration.md").read_text(encoding="utf-8")
        contract = (SKILL / "references" / "agent-contract.md").read_text(encoding="utf-8")
        output = (SKILL / "references" / "output-schemas.md").read_text(encoding="utf-8")
        orchestration = (SKILL / "references" / "orchestration.md").read_text(
            encoding="utf-8"
        )
        user_config = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")

        self.assertIn("For a built-in agent", config)
        self.assertIn("For a consumer extension, intersect", config)
        self.assertIn("CHECKLIST_FAIL` to schema-native `fail`", config)
        self.assertIn("duplicate `blocking` key", config)
        self.assertIn("blocking_policy: canonical schema-native array", orchestration)
        self.assertIn("do not trust a caller-provided classification", orchestration)
        self.assertIn("same effective policy", output)
        self.assertIn("mixes global and native tokens", contract)
        self.assertIn("(stricter)", user_config)
        self.assertIn("(looser)", user_config)

        for path in (SKILL / "references" / "agents").glob("*.md"):
            text = path.read_text(encoding="utf-8")
            if "output_schema: hml" in text:
                self.assertIn("output_schema: hml\nblocking:\n  - HIGH\n  - MEDIUM", text)
            else:
                self.assertIn("output_schema: checklist\nblocking:\n  - fail", text)

    def test_gitlab_start_and_base_identities_remain_distinct(self) -> None:
        gitlab = (SKILL / "references" / "providers" / "gitlab.md").read_text(
            encoding="utf-8"
        )
        metadata = {
            "diff_refs": {
                "start_sha": "1" * 40,
                "base_sha": "2" * 40,
                "head_sha": "3" * 40,
            }
        }
        self.assertNotEqual(
            metadata["diff_refs"]["start_sha"], metadata["diff_refs"]["base_sha"]
        )
        advanced_target_sha = "4" * 40
        self.assertNotEqual(advanced_target_sha, metadata["diff_refs"]["start_sha"])
        start_object_available = False
        self.assertFalse(start_object_available)
        self.assertIn("fetched target-ref identity only as the current drift value", gitlab)
        self.assertIn("mismatch with `start_sha` is reported", gitlab)
        self.assertIn("does not fail scope or change the immutable range", gitlab)
        self.assertIn("Materialize and verify only the evidence commits", gitlab)
        self.assertIn("without requiring its Git object to be present", gitlab)
        self.assertIn("use `base_sha` as the effective diff base", gitlab)
        self.assertIn("recorded start SHA", gitlab)
        self.assertIn("`start_sha`, `base_sha`, and `head_sha`", gitlab)

    def test_denied_paths_are_preflighted_before_content_in_every_mode(self) -> None:
        main = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        scope = (SKILL / "references" / "scope-resolution.md").read_text(encoding="utf-8")
        orchestration = (SKILL / "references" / "orchestration.md").read_text(encoding="utf-8")
        user_config = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")

        self.assertLess(main.index("metadata-only path preflight"), main.index("Only after preflight succeeds"))
        self.assertIn("rename/copy source and destination", main)
        self.assertIn("never reduce a mixed scope to an allowed subset", main)

        local_metadata = (
            "git diff --no-ext-diff --no-textconv --cached --raw -z --no-renames "
            "--no-abbrev --ignore-submodules=none HEAD"
        )
        local_content = "construct tracked hunks and deterministic relationships internally"
        self.assertLess(scope.index(local_metadata), scope.index(local_content))
        self.assertIn("Do not run `git diff HEAD`, `git diff-files`, `git status`", scope)
        self.assertIn("git ls-files --stage -z", scope)
        self.assertIn("git ls-files -v -z", scope)
        self.assertIn("git ls-files --debug -z", scope)
        self.assertIn("git ls-files --others --exclude-standard -z", scope)
        self.assertIn("Reject an exact path collision", scope)
        self.assertIn("cannot have two owners in the normalized manifest", scope)
        self.assertIn("newly appearing denied candidate", scope)
        empty_exit = "If the staged manifest, mutable-candidate set"
        primary_capture = "Capture every accepted regular mutable candidate"
        self.assertLess(scope.index(empty_exit), scope.index(primary_capture))
        self.assertIn("immediately repeat the staged diff, complete index metadata", scope)
        self.assertIn("stat-cache metadata", scope)
        self.assertIn("exactly one stage-0 entry", scope)
        self.assertIn("no stage 1, 2, or 3 entry", scope)
        self.assertIn("Reject an unmerged index globally", scope)
        self.assertIn("unstaged gitlink", scope)
        self.assertIn("complete index metadata and flags", scope)
        self.assertIn("mutable local tracked, local untracked", scope)
        self.assertIn("Raw comparison intentionally bypasses clean/smudge", scope)
        self.assertIn("not racily clean", scope)
        self.assertIn("never against the caller's mutable working tree", scope)
        self.assertIn("caller's mutable working tree", scope)
        tracked_snapshot = "Materialize a tracked-only snapshot"
        untracked_append = "append them to the normalized review diff"
        self.assertLess(scope.index(tracked_snapshot), scope.index(untracked_append))
        self.assertIn("Do not place untracked files in this tracked snapshot", scope)
        self.assertIn("independent synthetic additions", scope)
        self.assertIn("Assign every untracked path status `A`", scope)
        self.assertIn("Never run rename or copy detection", scope)

        path_enumeration = "enumerate entry names and link-aware file metadata"
        path_preflight = "Run the complete path preflight over every enumerated path"
        primary_capture_section = "## Primary input capture"
        immutable_context = "## Immutable review context"
        path_binary_read = "perform binary detection"
        path_synthetic_hunk = "construct synthetic hunks"
        self.assertLess(scope.index(path_enumeration), scope.index(path_preflight))
        self.assertLess(scope.index(path_preflight), scope.index(primary_capture_section))
        self.assertLess(scope.index(primary_capture_section), scope.index(immutable_context))
        self.assertLess(
            scope.index(primary_capture_section),
            scope.index(path_binary_read, scope.index(primary_capture_section)),
        )
        self.assertLess(
            scope.index(primary_capture_section),
            scope.index(path_synthetic_hunk, scope.index(primary_capture_section)),
        )
        self.assertIn("accepted local tracked files with unstaged bodies", scope)
        self.assertIn("platform secure-open adapter", scope)
        self.assertIn("anchored to a repository-root capability", scope)
        self.assertIn("POSIX adapters", scope)
        self.assertIn("Windows adapters", scope)
        self.assertIn("reparse points in every path component", scope)
        self.assertIn("fail scope resolution before reading any primary bytes", scope)
        self.assertIn("post-open metadata has the same stable file identity", scope)
        self.assertIn("reject a file that changed during capture", scope)
        self.assertIn("before/after `fstat`", scope)
        self.assertIn("fails the complete atomic scope", scope)
        self.assertIn("never fall back to a path-based reopen", scope)
        self.assertIn("Primary capture never refers to a snapshot root", scope)
        self.assertIn("anchored to the snapshot-root capability", scope)
        self.assertIn("never fall back to an ordinary or unbounded path open", scope)
        self.assertIn("Primary inputs are never reopened here", scope)
        self.assertIn("Trusted extension references were separately validated", scope)
        self.assertNotIn("file descriptor-relative to an anchored", scope)

        range_metadata = (
            "git diff --no-ext-diff --no-textconv --raw -z --no-renames "
            "--no-abbrev --ignore-submodules=none "
            "<validated-immutable-range>"
        )
        range_content = "Only after every candidate is accepted and immutable body sizes pass"
        self.assertLess(scope.index(range_metadata), scope.index(range_content))
        self.assertIn("both endpoints were accepted", scope)
        self.assertIn("malformed, truncated, or unknown status record fails scope resolution", scope)
        self.assertIn("reject an undecodable path", scope)
        self.assertIn("three-dot range's merge base", scope)
        self.assertIn("Treat the manifest as one atomic scope", scope)
        self.assertIn("before any candidate content reaches tool output or model context", scope)
        self.assertIn("before retrieving content diffs", scope)
        self.assertIn(
            "Only after the complete path preflight and every mode-owned primary capture",
            scope,
        )

        provider_ranges = {
            "github": 'verified immutable range `"$BASE_SHA...$HEAD_SHA"`',
            "gitlab": 'verified immutable range `"$BASE_SHA" "$HEAD_SHA"`',
        }
        for provider, immutable_range in provider_ranges.items():
            text = (SKILL / "references" / "providers" / f"{provider}.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(immutable_range, text)
            self.assertIn("shared Remote evidence transport", text)
            self.assertIn("Any path-preflight rejection terminates immediately", text)
        github = (SKILL / "references" / "providers" / "github.md").read_text(encoding="utf-8")
        self.assertIn('git merge-base "$BASE_SHA" "$HEAD_SHA"', github)
        self.assertIn("use its tree as the effective diff base", github)

        self.assertIn("No trigger, snapshot, prompt, bucket, or dependency hash", orchestration)
        self.assertIn("before blob retrieval or hunk construction", orchestration)
        self.assertIn("One denied path fails the entire scope", user_config)
        self.assertIn("allowed/denied mixed change", user_config)

    def test_git_diff_evidence_disables_external_helpers(self) -> None:
        scope = (SKILL / "references" / "scope-resolution.md").read_text(encoding="utf-8")
        self.assertIn("## Raw Git diff safety", scope)
        self.assertIn("--no-ext-diff", scope)
        self.assertIn("--no-textconv", scope)
        self.assertIn("--raw -z --no-renames", scope)
        self.assertIn("--no-abbrev", scope)
        self.assertIn("--ignore-submodules=none", scope)
        self.assertIn("diff.renameLimit", scope)
        self.assertIn("GIT_EXTERNAL_DIFF", scope)
        self.assertIn("GIT_DIFF_OPTS", scope)
        self.assertIn("every `GIT_CONFIG_*` entry", scope)
        self.assertIn("GIT_INDEX_FILE", scope)
        self.assertIn("GIT_OBJECT_DIRECTORY", scope)
        self.assertIn("core.fsmonitor=false", scope)
        self.assertIn("GIT_NO_REPLACE_OBJECTS=1", scope)
        self.assertIn("GIT_NO_LAZY_FETCH=1", scope)
        self.assertIn("GIT_REPLACE_REF_BASE", scope)
        self.assertIn("never accept Git-produced patch bodies", scope)
        self.assertIn("similarity scoring reads blob contents", scope)
        self.assertIn("git ls-tree -r -z --full-tree <effective-base-tree>", scope)
        self.assertIn("every endpoint is an accepted candidate", scope)
        self.assertIn("non-exact copies from unchanged sources as additions", scope)
        self.assertIn("modified renames as delete/add pairs", scope)
        self.assertIn("package-owned binary detection", scope)
        self.assertIn("contains no NUL byte and decodes as strict UTF-8", scope)
        self.assertIn("Never use locale decoding or replacement characters", scope)
        self.assertIn("three context lines", scope)
        self.assertIn("explicit no-final-newline marker", scope)
        self.assertIn("reversible package-owned form", scope)
        self.assertIn("must not execute helpers", scope)
        self.assertIn("classify evidence as binary", scope)
        self.assertIn("never write objects, refs, or index state", scope)
        self.assertIn("compatible Git mode classes", scope)
        self.assertIn("gitlink mode `160000`", scope)
        self.assertIn("Subproject commit <full-object-id>", scope)
        self.assertIn("git cat-file --batch-check", scope)
        for ceiling in (
            "10,000 candidate paths",
            "200,000 logical-tree entries",
            "64 MiB of retained metadata",
            "16 MiB per changed body",
            "128 MiB across unique changed bodies",
            "20,000,000 edit operations",
            "64 MiB of normalized diff output",
            "512 MiB total projected context",
        ):
            self.assertIn(ceiling, scope)
        self.assertIn("fails the complete atomic scope without prompt construction or caching", scope)
        self.assertIn("makes required context incomplete", scope)
        for remote_limit in (
            "64 MiB of compressed input",
            "256 MiB of expanded commit/tree objects",
            "320 MiB of isolated-store disk use",
        ):
            self.assertIn(remote_limit, scope)
        self.assertIn("--filter=blob:none", scope)
        self.assertIn("response includes a blob body", scope)
        self.assertIn("provider's authenticated raw-blob endpoint", scope)
        self.assertIn("Verify each completed body's Git object ID", scope)

    def test_git_raw_preflight_does_not_run_copy_similarity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(
                ["git", "config", "user.email", "tests@example.invalid"],
                cwd=repository, check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Deep Review Tests"],
                cwd=repository, check=True,
            )
            (repository / "source.txt").write_text("copied content\n", encoding="utf-8")
            subprocess.run(["git", "add", "source.txt"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=repository, check=True)
            (repository / "copy.txt").write_text("copied content\n", encoding="utf-8")
            subprocess.run(["git", "add", "copy.txt"], cwd=repository, check=True)

            raw = subprocess.run(
                [
                    "git", "diff", "--cached", "--raw", "-z", "--no-renames",
                    "--no-abbrev", "--ignore-submodules=none", "HEAD",
                ],
                cwd=repository, check=True, capture_output=True,
            ).stdout

            self.assertIn(b"A\x00copy.txt\x00", raw)
            self.assertNotIn(b"source.txt", raw)
            object_id = subprocess.run(
                ["git", "hash-object", "copy.txt"],
                cwd=repository, check=True, capture_output=True,
            ).stdout.strip()
            self.assertIn(object_id, raw)
            scope = (SKILL / "references" / "scope-resolution.md").read_text(encoding="utf-8")
            self.assertIn("body-free object-ID matching", scope)

    def test_local_raw_preflight_does_not_run_clean_filters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            marker = repository / "filter-ran"
            filter_script = repository / "filter_probe.py"
            filter_script.write_text(
                "import os, sys\n"
                "data = sys.stdin.buffer.read()\n"
                "with open(os.environ['TASK_MARKER'], 'wb') as marker:\n"
                "    marker.write(data)\n"
                "sys.stdout.buffer.write(data)\n",
                encoding="utf-8",
            )
            environment = {**os.environ, "TASK_MARKER": str(marker)}
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(
                ["git", "config", "user.email", "tests@example.invalid"],
                cwd=repository, check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Deep Review Tests"],
                cwd=repository, check=True,
            )
            subprocess.run(
                [
                    "git", "config", "filter.probe.clean",
                    f'"{sys.executable}" "{filter_script}"',
                ],
                cwd=repository, check=True,
            )
            (repository / ".gitattributes").write_text("*.txt filter=probe\n", encoding="utf-8")
            (repository / "tracked.txt").write_text("before\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", ".gitattributes", "tracked.txt"],
                cwd=repository, env=environment, check=True,
            )
            subprocess.run(
                ["git", "commit", "-qm", "base"], cwd=repository, env=environment, check=True,
            )
            marker.unlink(missing_ok=True)
            (repository / "tracked.txt").write_text("after\n", encoding="utf-8")

            subprocess.run(
                ["git", "diff", "--name-status", "HEAD"],
                cwd=repository, env=environment, check=True, capture_output=True,
            )
            self.assertTrue(marker.exists(), "control command should demonstrate the filter risk")
            marker.unlink()

            safe_commands = (
                [
                    "git", "diff", "--no-ext-diff", "--no-textconv", "--cached",
                    "--raw", "-z", "--no-renames", "--no-abbrev",
                    "--ignore-submodules=none", "HEAD",
                ],
                ["git", "ls-files", "--stage", "-z"],
                ["git", "ls-files", "-v", "-z"],
                ["git", "ls-files", "--debug", "-z"],
                ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            )
            for command in safe_commands:
                subprocess.run(
                    command, cwd=repository, env=environment, check=True, capture_output=True,
                )
                self.assertFalse(marker.exists(), command)

    def test_local_path_handling_requires_literal_pathspecs(self) -> None:
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
            self.assertIn("Literal pathspec mode is mandatory", scope)

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
