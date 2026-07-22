# Maintainer operations

This guide contains repository-administration details that are not needed by ordinary Deep Review users.

## Continuous integration

GitLab CI runs the complete Python unit-test suite on Python 3.10 and 3.14. Python container images are pinned to reviewed multi-platform manifest digests; update those digests explicitly and review the change like other code.

Pipeline selection works as follows:

- A push to a branch without an open merge request creates a branch pipeline.
- After a merge request is open, its pipeline runs and the duplicate branch pipeline is suppressed.
- A pipeline started with **Build > Pipelines > New pipeline** remains available when automatic pipelines are disabled.

### Disable automatic pipelines

Create a project or group CI/CD variable with these settings:

```text
Key: CI_ENABLED
Value: false
Type: Variable
Environment scope: All (*)
Protect variable: cleared
```

The value must be the exact lowercase string `false`. For a project variable, open **Settings > CI/CD**, expand **Variables**, and select **Add variable**. Leave **Protect variable** cleared if the gate should also apply to unprotected branches and merge requests.

Delete the variable or change it to `true` to re-enable automatic pipelines. Manually started web pipelines intentionally remain enabled because the `web` pipeline-source rule is evaluated before the automatic-pipeline gate.

## Runtime documentation

The files under `skills/deep-review/references/` are normative. Update them and their contract tests together when behavior changes; keep this guide focused on repository operations.

## Claude marketplace releases

`skills/deep-review/` is the canonical vendor-neutral Agent Skill and the Claude plugin root. Keep Claude-specific metadata additive: do not move, rename, or duplicate `SKILL.md`, `references/`, or `scripts/` to prepare a marketplace release. OpenAI or another distributor may add its own manifest later while packaging the same skill.

The public plugin name `deep-review` is immutable after publication. Treat `skills/deep-review/.claude-plugin/plugin.json` as the authoritative explicit version. Before every release:

1. Choose the semantic version: increment the major version for breaking changes, the minor version for backward-compatible features, or the patch version for backward-compatible fixes.
2. Update `version` in `skills/deep-review/.claude-plugin/plugin.json` and add the same version to `skills/deep-review/CHANGELOG.md`.
3. Confirm the packaged `skills/deep-review/LICENSE` is byte-for-byte identical to the repository `LICENSE`.
4. Run the deterministic package and runtime tests:

   ```bash
   python3 -m unittest discover -s tests -v
   ```

5. Run Claude's strict plugin validator:

   ```bash
   claude plugin validate --strict skills/deep-review
   ```

6. Load the release package locally:

   ```bash
   claude --plugin-dir ./skills/deep-review
   ```

   In the new session, confirm `/deep-review:deep-review` is available, run it against a small known diff, and verify that the review reaches a documented terminal state. On Claude Code 2.1.216 and newer, also confirm the `/deep-review` convenience alias when no conflicting command is installed.

7. Review the complete release diff and merge it to `main`. In GitLab, protect the `v*` tag pattern so only maintainers can create release tags. After explicit release authorization, fetch the merged state, derive the version from the manifest, and tag that exact commit—never an unmerged feature branch:

   ```bash
   release_version=$(python3 -c 'import json; print(json.load(open("skills/deep-review/.claude-plugin/plugin.json"))["version"])')
   git fetch origin main
   git tag -a "v$release_version" origin/main -m "Deep Review $release_version"
   git push origin "v$release_version"
   ```

8. Open the GitLab pipeline for that tag and manually run `prepare_claude_submission`. The job accepts only a protected semantic-version tag, requires it to be annotated, verifies that its commit belongs to `main` and matches the manifest version, reruns the Python suite and Claude's strict validator, and produces a checksummed archive directly from the tagged plugin tree. It never creates or pushes a tag and never submits the plugin.

9. Submit or update the plugin through the [Claude Console submission form](https://platform.claude.com/plugins/submit). Identify the repository as `https://gitlab.com/hubertgajewski-ai/deep-review.git` and the plugin subdirectory as `skills/deep-review`. Record the submission status or resulting `claude-community` catalog link in the release issue. Anthropic currently documents only the in-app submission forms, so this remains an explicit manual maintainer action.

Do not tag or submit when the manifest is missing or malformed, package tests fail, the changelog version differs, strict validation emits a warning or error, or the local smoke test does not complete. Marketplace review and publication are external post-merge steps; do not represent them as completed until they actually occur.
