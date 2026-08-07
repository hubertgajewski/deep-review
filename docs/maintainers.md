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

## Releases and Claude marketplace

`skills/deep-review/` is the canonical vendor-neutral Agent Skill and the Claude plugin root. Keep Claude-specific metadata additive: do not move, rename, or duplicate `SKILL.md`, `references/`, or `scripts/` to prepare a marketplace release. OpenAI or another distributor may add its own manifest later while packaging the same skill.

The public plugin name `deep-review` is immutable after publication. Treat `skills/deep-review/.claude-plugin/plugin.json` as the authoritative explicit version. Before every release:

`release-contract.json` is the versioned source of truth for installer client destinations and required release-asset names. The POSIX and PowerShell installers contain generated copies of the client table because they must choose a destination before downloading the package; contract tests require both copies to match exactly. The publisher discovers its complete asset roster from this contract instead of duplicating the list in CI arguments.

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
   git fetch origin main
   release_version=$(git show origin/main:skills/deep-review/.claude-plugin/plugin.json | python3 -c 'import json, sys; print(json.load(sys.stdin)["version"])')
   git tag -a "v$release_version" origin/main -m "Deep Review $release_version"
   git push origin "v$release_version"
   ```

8. Open the GitLab pipeline for that tag and manually run `prepare_claude_submission`. The job accepts only a protected semantic-version tag, requires it to be annotated, verifies that its commit belongs to `main` and matches the manifest version, reruns the Python suite and Claude's strict validator, and produces checksummed TAR and ZIP packages directly from the tagged plugin tree. It also checksums the committed POSIX and PowerShell installers. It never creates or pushes a tag and never submits the plugin.

9. After preparation succeeds, `publish_release` automatically uploads those exact artifacts to the GitLab generic package registry and creates or updates the GitLab Release. The package-registry copies do not inherit the CI artifact's 30-day expiry. Publication is idempotent: an identical asset is reused, while an attempt to change an existing version's bytes fails. At the owning group, turn off **Settings > Packages and registries > Generic > Allow duplicates** with no exception for `deep-review`; restrict package deletion to the smallest maintainer group and exclude `deep-review` from cleanup policies. Confirm those settings and all eight Release links before announcing the release.

10. Submit or update the plugin through the [Claude Console submission form](https://platform.claude.com/plugins/submit). Identify the repository as `https://gitlab.com/hubertgajewski-ai/deep-review.git` and the plugin subdirectory as `skills/deep-review`. Record the submission status or resulting `claude-community` catalog link in the release issue. Anthropic currently documents only the in-app submission forms, so this remains an explicit manual maintainer action.

Do not tag, publish, or submit when the manifest is missing or malformed, package tests fail, the changelog version differs, strict validation emits a warning or error, the package protections above are absent, or the local smoke test does not complete. Treat a tag and its protected generic-package assets as immutable release identities; fix a bad release with a new version. Marketplace review and publication are external post-merge steps; do not represent them as completed until they actually occur.
