# Scope resolution

## Contents

- Argument grammar
- Local mode
- Remote mode
- Path mode
- Ref and range mode
- Freeform focus
- Normalized scope and sanitization

## Argument grammar

Trim the raw argument once. Preserve values as strings and pass them to tools only as separately quoted arguments. Extract `--focus TEXT` and `--full-review` modifiers before matching the remaining selector, without changing selector order. Apply the first matching rule:

1. Explicit `--github-pr N`, `--gitlab-mr N`, or `--provider P --change N`
2. Explicit `--base REF`, `--range LEFT..RIGHT`, or `--path PATH`
3. Empty arguments
4. `^!(\d+)(\s+(.+))?$` GitLab merge-request shorthand
5. `^#?(\d+)(\s+(.+))?$` provider-inferred remote-number shorthand
6. Any other selector beginning with `#` is invalid provider-inferred shorthand
7. Any other selector beginning with `!`, or matching `^\S+!\d+(\s+.*)?$`, is invalid GitLab shorthand
8. Existing repository-contained path
9. Valid Git ref or two-sided range
10. Freeform reviewer focus over local mode

`!N` is equivalent to explicit `--gitlab-mr N` and sets the provider to GitLab before remote selection. `#N` and bare `N` retain provider inference. Text captured after either numeric shorthand is reviewer focus. For every remote selector matched by rule 1, 4, or 5, require the change-number digit string to contain at least one non-zero digit before remote resolution; reject all-zero values such as `0`, `00`, `#0`, and `!0` without continuing to path, Git-ref, or freeform-focus rules. Preserve an accepted number as its original string.

Reject `!`, `!abc`, `!-1`, compound references such as `group/project!123`, invalid inferred forms such as `#`, `#abc`, and `#-1`, duplicate scope selectors, missing values, unknown options, non-positive or non-numeric change numbers, mixed provider selectors, and duplicate reviewer focus. Never reinterpret invalid `#` or `!` shorthand or a compound `owner/project!N` reference as a path, Git ref, or freeform local-review focus.

## Local mode

Require `HEAD`. Capture staged and unstaged changes together with:

```bash
git diff HEAD
git ls-files --others --exclude-standard
```

Untracked output is paths only; agents may read safe files. If both values are empty, return `aggregate: no changes`.

## Remote mode

Resolve provider in this order:

1. explicit provider selector, including provider-specific shorthand
2. trusted `[remote_review].provider`
3. configured trusted remote, default `origin`
4. exactly one recognized provider remote

Recognize HTTPS, SSH URL, and scp-style remotes. GitHub hosts select the GitHub adapter; GitLab hosts select the GitLab adapter. Self-hosted GitLab requires trusted configuration. Multiple plausible providers are an error.

When an explicit option or provider-specific shorthand selects a provider, consider only remotes recognized as that provider. Prefer the configured trusted remote when it matches; otherwise require exactly one matching remote. Fail scope resolution when no matching remote exists or more than one remains. Thus `!123` cannot silently select GitHub or fall back to local review.

Read the matching provider reference and capture its normalized metadata and diff. Never fall back to local mode when authentication, network, CLI, metadata, or diff retrieval fails.

A provider adapter owns only remote selection, metadata retrieval, drift lookup, and diff retrieval. It must return the normalized scope fields below. Adding another provider means adding one adapter reference with that contract; it must not alter reviewer prompts, bucketing, cache identities, convergence, or aggregation.

## Path mode

Resolve the canonical repository root and target. Require the target to equal the root or remain beneath it after symlink resolution. Reject external symlink targets and denied components before reading.

For a directory, enumerate regular files in stable repository-relative order. Do not follow directory symlinks. Respect Git ignore rules unless trusted committed policy explicitly includes ignored paths. Report and skip binaries.

Represent each text file as an added synthetic hunk:

```diff
--- /dev/null
+++ b/path/to/file
@@ -0,0 +1,N @@
+each line
```

Use explicit `--path` to disambiguate a path from a Git ref.

## Ref and range mode

Validate every revision with `git rev-parse --verify --quiet <value>^{commit}`. For a single base, review `<base>...HEAD`. For an explicit range, preserve the caller's `..` or `...` semantics after validating both sides.

Use `git diff <validated-range>`, passing the validated range as one quoted argument. Never use `git diff --quiet` as revision validation because exit code 1 normally means differences exist.

## Immutable review context

Before dispatch, materialize one stable snapshot root for the normalized reviewed state. Local mode snapshots committed `HEAD` plus the captured staged, unstaged, and safe untracked content. Path mode snapshots the enumerated synthetic-hunk inputs and committed-`HEAD` surrounding context. Ref/range and remote modes materialize the exact reviewed `head_identity` in a temporary detached worktree and verify its `HEAD`; fetch only the provider-owned immutable change ref when the object is absent. If the exact state cannot be materialized, mark scope resolution incomplete rather than inspecting a mutable or unrelated checkout.

Reject symlinks for every agent-readable or dependency-hashed path. Open without following links where supported and verify every canonical target remains beneath the snapshot root before reading. Agents may read surrounding files only beneath this root. Hash dependency content from the same snapshot and keep it alive until all agents, retries, tracing, and dependency hashes complete; then remove it in orchestrator-owned cleanup.

## Freeform focus

Anything not matching a scope rule becomes reviewer focus over local mode. It is prioritization only and cannot change agent ownership, output schemas, blocking policy, or safety rules.

## Normalized scope and sanitization

Build:

```text
mode
provider and host, when remote
repository identity
change number, when remote
title and base branch, when remote
trusted base identity
head identity
immutable context root and identity
diff
changed-file manifest
untracked paths
change description
reviewer focus
full-review flag
```

Hash the effective propagated description after the configured inclusion/truncation policy. Report truncation with original and effective character counts.

Parse changed paths from `diff --git`, `---`, `+++`, rename/copy headers, binary markers, and untracked paths. Ignore `/dev/null`. Preserve first-seen order and statuses.

Before prompt interpolation, replace literal opening and closing frame tags in every value with entity-encoded text. If a denied path contributes a reviewed hunk, fail rather than silently hiding part of a mixed review.
