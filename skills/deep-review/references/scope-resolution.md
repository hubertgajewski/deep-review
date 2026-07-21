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

Require `HEAD`. First enumerate tracked changes and untracked paths without emitting their contents:

```bash
git diff --name-status -z --find-renames --find-copies HEAD
git ls-files --others --exclude-standard -z
```

Parse the NUL-delimited status stream without shell interpolation. A rename or copy record contributes both its source and destination to the path preflight. Run the complete path preflight below, including no-follow metadata checks for every untracked path, before asking Git for hunks or opening an untracked file.

After preflight succeeds, retrieve the tracked content diff with `git diff --find-renames --find-copies HEAD -- <accepted-pathspecs>`, passing every accepted tracked path as a separate quoted argument. Read accepted untracked files only through the no-follow rules in Immutable review context. Immediately repeat both metadata-only enumeration commands. If either status stream differs byte-for-byte, discard all captured content without prompt construction, snapshotting, or dependency hashing and restart the complete local preflight once. A second change fails scope resolution as a concurrently changing working tree. A newly appearing denied path therefore fails the scope without its content being read; a newly appearing allowed path triggers the same retry rather than being silently omitted.

If both accepted metadata streams are empty, return `aggregate: no changes` without retrieving content.

## Remote mode

Resolve provider in this order:

1. explicit provider selector, including provider-specific shorthand
2. trusted `[remote_review].provider`
3. configured trusted remote, default `origin`
4. exactly one recognized provider remote

Recognize HTTPS, SSH URL, and scp-style remotes. GitHub hosts select the GitHub adapter; GitLab hosts select the GitLab adapter. Self-hosted GitLab requires trusted configuration. Multiple plausible providers are an error.

When an explicit option or provider-specific shorthand selects a provider, consider only remotes recognized as that provider. Prefer the configured trusted remote when it matches; otherwise require exactly one matching remote. Fail scope resolution when no matching remote exists or more than one remains. Thus `!123` cannot silently select GitHub or fall back to local review.

Read the matching provider reference and capture its normalized metadata and diff. Provider adapters must enumerate and preflight paths from verified immutable base and head identities before retrieving content hunks. Never fall back to local mode when authentication, network, CLI, metadata, or diff retrieval fails.

A provider adapter owns only remote selection, metadata retrieval, drift lookup, and diff retrieval. It must return the normalized scope fields below. Adding another provider means adding one adapter reference with that contract; it must not alter reviewer prompts, bucketing, cache identities, convergence, or aggregation.

## Path mode

Resolve the canonical repository root and target. Require the target to equal the root or remain beneath it after symlink resolution. Reject external symlink targets and denied components before reading.

For a directory, enumerate entry names and no-follow file metadata in stable repository-relative order before opening any file. Do not follow directory symlinks. Run the complete path preflight over every enumerated path as one batch, so one denied path fails the whole path scope before any synthetic hunk is built. Respect Git ignore rules unless trusted committed policy explicitly includes ignored paths. After preflight succeeds, report and skip binaries.

Represent each text file as an added synthetic hunk:

```diff
--- /dev/null
+++ b/path/to/file
@@ -0,0 +1,N @@
+each line
```

Use explicit `--path` to disambiguate a path from a Git ref.

## Ref and range mode

Validate every revision with `git rev-parse --verify --quiet <value>^{commit}` and retain the resulting full object ID rather than later dereferencing a movable name. For a single base, resolve both `<base>` and `HEAD`, then review their immutable three-dot range. For an explicit range, preserve the caller's `..` or `...` semantics after resolving both sides to full commit IDs. Resolve a three-dot range's merge base to a full commit ID before path preflight and use that immutable tree as the effective source side for mode, symlink, and containment validation.

First run `git diff --name-status -z --find-renames --find-copies <validated-immutable-range>` and perform the complete path preflight. Only after every emitted path is accepted may `git diff --find-renames --find-copies <validated-immutable-range>` retrieve content hunks. Pass the validated range as one quoted argument. Never use `git diff --quiet` as revision validation because exit code 1 normally means differences exist.

## Path preflight

Every mode completes this phase before retrieving content diffs, opening reviewed files, materializing snapshots, building prompts, or hashing dependencies. Metadata-only means command output contains statuses, modes, object identities, and paths, but no patch hunks or file bodies.

Build the complete candidate manifest from the mode's metadata source. Include every changed and untracked path. For every rename or copy, include and retain the status relationship plus both source and destination, even when only the destination will appear as `CHANGED_FILES.path`. A malformed, truncated, or unknown status record fails scope resolution; never guess its paths or status.

Normalize each candidate to a repository-relative `/`-separated path without a leading `./`. Reject empty paths, absolute paths, NULs, `.` or `..` traversal components, paths outside the repository, and any component matching `deny_components`. Reject symlinks and external canonical targets using metadata only: use no-follow filesystem inspection for local working-tree, untracked, and path inputs; use the committed `HEAD` tree modes for local base-side paths; and use verified tree modes from the immutable effective diff base and head objects for ref/range and remote inputs. Validate both object sides when they exist, including rename/copy sources in the effective diff base and destinations in the head.

Treat the manifest as one atomic scope. If any candidate fails, emit `Failed at scope resolution: <reason>.` before any candidate content reaches tool output or model context. Do not retrieve the allowed members of a mixed allowed/denied scope, do not construct a partial snapshot, and do not hash any dependency.

After acceptance, freeze the manifest as the only content-read allowlist. Content retrieval must use the same immutable identities and rename/copy settings as enumeration. Cross-check its file headers and status metadata against the accepted manifest; any mismatch fails scope resolution and never expands the allowlist.

## Immutable review context

Only after the complete path preflight and content retrieval succeed, materialize one stable snapshot root for the normalized reviewed state. Local mode snapshots committed `HEAD` plus the captured staged, unstaged, and safe untracked content. Path mode snapshots the enumerated synthetic-hunk inputs and committed-`HEAD` surrounding context. Ref/range and remote modes materialize the exact reviewed `head_identity` in a temporary detached worktree and verify its `HEAD`; fetch only the provider-owned immutable change ref when the object is absent. If the exact state cannot be materialized, mark scope resolution incomplete rather than inspecting a mutable or unrelated checkout.

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

Use the accepted preflight manifest as the authority for changed paths and statuses. Parse `diff --git`, `---`, `+++`, rename/copy headers, and binary markers only to partition accepted content and cross-check it against that manifest. Ignore `/dev/null`. Preserve first-seen order and statuses.

Before prompt interpolation, replace literal opening and closing frame tags in every value with entity-encoded text. A denied path must already have failed path preflight before any reviewed hunk was retrieved; if later evidence contradicts that invariant, fail scope resolution rather than emitting or hiding the hunk.
