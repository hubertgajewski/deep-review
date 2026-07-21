# Scope resolution

## Contents

- Argument grammar
- Raw Git diff safety
- Local mode
- Remote mode
- Path mode
- Ref and range mode
- Path preflight
- Primary input capture
- Immutable review context
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

## Raw Git diff safety

Git diff machinery is metadata-only in every mode; never accept Git-produced patch bodies as review evidence and never ask it to inspect mutable worktree content. The first changed-path enumeration must use `--raw -z --no-renames --no-ext-diff --no-textconv`. Rename and copy discovery is forbidden during preflight because similarity scoring reads blob contents even when the requested output is name-only. Raw records supply only statuses, modes, object IDs, and paths; reject malformed records and preflight every added, deleted, modified, or type-changed endpoint before retrieving a blob.

Enumerate the logical base tree with `git ls-tree -r -z --full-tree <effective-base-tree>` as path, mode, and object ID without blob bodies. Before endpoint preflight, exact object-ID equality may select a relationship source and add that source path to the same candidate manifest; do not read it first. Resolve collisions in bytewise path order, preferring an unmatched deleted endpoint as an exact rename source and otherwise selecting the first base path as an exact copy source. A delete is consumed by at most one rename; a copy source may be reused. After the complete candidate preflight, retrieve only accepted raw immutable blobs or securely captured bytes and construct normalized hunks internally. Apply relationships only when exact identity was established from metadata and every endpoint is an accepted candidate; leave modified renames as delete/add pairs and non-exact copies from unchanged sources as additions. Contributor-controlled or host attributes must not execute helpers, convert content, classify evidence as binary, or replace raw evidence presentation. Apply package-owned binary detection; Git's `diff.renameLimit` and similarity heuristics never participate.

The internal evidence builder treats a body as text only when it contains no NUL byte and decodes as strict UTF-8; otherwise emit a binary marker without decoded body content. Never use locale decoding or replacement characters. For text, produce deterministic unified hunks with three context lines, preserve line terminators, and emit an explicit no-final-newline marker when required. Represent mode-only changes without inventing a content hunk. Keep the `/dev/null` sentinel literal; double-quote every repository header path as bytes: keep printable ASCII except `\` and `"`, encode those two as `\\` and `\"`, use `\t`, `\n`, and `\r`, and encode every other byte as `\xHH`. Decode this reversible package-owned form only to cross-check already accepted path bytes; raw path bytes can never create a false header.

Invoke Git without a pager or optional locks, with `core.fsmonitor=false` and `GIT_NO_REPLACE_OBJECTS=1`, so a replace ref cannot change the meaning of a retained object ID. Remove inherited repository, worktree, index, object-database, replacement, shallow-boundary, executable-path, diff-helper, and configuration-injection environment overrides, including `GIT_DIR`, `GIT_COMMON_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY`, `GIT_ALTERNATE_OBJECT_DIRECTORIES`, `GIT_REPLACE_REF_BASE`, `GIT_SHALLOW_FILE`, `GIT_EXEC_PATH`, `GIT_EXTERNAL_DIFF`, `GIT_DIFF_OPTS`, and every `GIT_CONFIG_*` entry; supply only orchestrator-resolved paths or isolated-object values required by the specific command.

## Local mode

Require `HEAD`. Do not run `git diff HEAD`, `git diff-files`, `git status`, or another Git operation that compares the index with mutable worktree files: even a name-only form can invoke a configured clean filter before preflight. First obtain only immutable staged relationships, complete index metadata, and untracked path names without emitting file contents:

```bash
git diff --no-ext-diff --no-textconv --cached --raw -z --no-renames HEAD
git ls-files --stage -z
git ls-files -v -z
git ls-files --debug -z
git ls-files --others --exclude-standard -z
```

Parse the NUL-delimited streams without shell interpolation. Reject an unmerged index globally: every tracked index path must have exactly one stage-0 entry and no stage 1, 2, or 3 entry. Retain its mode, object ID, stat-cache metadata, and skip-worktree state. Every staged raw endpoint contributes to the candidate manifest; any exact-copy source selected by body-free object-ID matching contributes too.

Inspect every stage-0 worktree path with link-aware, no-follow metadata only. A missing skip-worktree path represents the retained index state. Otherwise, conservatively classify the path as a mutable candidate unless its regular-file identity, size, executable mode, and timestamps match the retained index stat cache and are not racily clean. Missing non-skip-worktree paths, link-shaped or non-regular paths, and metadata changes are candidates. This classification must not open a file or invoke Git conversion, attribute, filter, or content-diff machinery. Combine the staged endpoints, mutable candidates, and untracked names, then run the complete path preflight over that atomic candidate set before opening any file.

Reject an exact path collision between a staged deletion and the untracked list. A staged deletion followed by an untracked file at the same path cannot have two owners in the normalized manifest; require the caller to stage the replacement or move the untracked file before review.

If the staged manifest, mutable-candidate set, and untracked list are all empty, immediately repeat the staged diff, complete index metadata, untracked enumeration, and no-follow worktree metadata before any blob lookup, primary capture, or snapshot. Return `aggregate: no changes` only when every retained value remains byte-identical. On drift, restart the complete local preflight once; a second change fails scope resolution as a concurrently changing working tree.

For an accepted staged endpoint or mutable candidate, reject a staged symlink mode even when an unstaged change would replace or delete it; snapshot construction must never materialize a link-shaped intermediate state. A mutable body candidate must be a regular file captured through Primary input capture; a deletion contributes no body. Fail scope resolution for an unstaged gitlink or another non-regular state that cannot be represented by those two cases.

Capture every accepted regular mutable candidate and every accepted untracked file through Primary input capture below. Compare each retained raw tracked body and executable mode internally with its stage-0 raw blob and mode; discard metadata-only false positives and retain the actual unstaged modifications. Raw comparison intentionally bypasses clean/smudge and end-of-line conversion. Then repeat the staged diff, complete index metadata and flags, untracked enumeration, and no-follow worktree metadata classification. If any retained stream, entry, flag, candidate, or metadata value differs byte-for-byte, discard every captured byte without prompt construction, snapshotting, or dependency hashing and restart the complete local preflight once. A second change fails scope resolution as a concurrently changing working tree. A newly appearing denied candidate therefore fails the scope without its content being read; a newly appearing allowed candidate triggers the same retry rather than being silently omitted.

Materialize a tracked-only snapshot from committed `HEAD`, the retained stage-0 index identities, and the securely captured actual unstaged bodies, deletions, and executable modes. Absence of a stage-0 entry records a staged deletion. Read staged and `HEAD` bodies by retained object ID and write raw bytes directly into an orchestrator-owned private root; never use checkout, restore, archive, worktree, or clean/smudge filters. Create any temporary blob/tree identities in an isolated object database that reads consumer objects only as alternates; never write objects, refs, or index state into the consumer repository. Do not place untracked files in this tracked snapshot. Run `git diff --no-ext-diff --no-textconv --raw -z --no-renames HEAD <isolated-tree>` against the two immutable trees, never against the caller's mutable working tree, and treat its endpoints as the final tracked manifest. Then construct tracked hunks and deterministic relationships internally from committed-`HEAD` blobs and retained snapshot bytes; never request content hunks from Git. A staged change canceled by the captured raw worktree state correctly disappears here.

After freezing the tracked diff, add retained untracked files to the immutable context root and append them to the normalized review diff as independent synthetic additions in accepted manifest order. Build text hunks directly from the retained bytes using the path-mode synthetic format; represent a binary input with an added-file binary marker. Assign every untracked path status `A`. Never run rename or copy detection between untracked inputs and tracked content. Cross-check the combined tracked blocks and synthetic untracked blocks against the complete accepted manifest before prompt construction.

Literal pathspec mode is mandatory for every Git command that receives accepted paths; repository filenames beginning with pathspec magic or containing wildcard characters remain data, not selection syntax.

## Remote mode

Resolve provider in this order:

1. explicit provider selector, including provider-specific shorthand
2. trusted `[remote_review].provider`
3. configured trusted remote, default `origin`
4. exactly one recognized provider remote

Recognize HTTPS, SSH URL, and scp-style remotes. GitHub hosts select the GitHub adapter; GitLab hosts select the GitLab adapter. Self-hosted GitLab requires trusted configuration. Multiple plausible providers are an error.

When an explicit option or provider-specific shorthand selects a provider, consider only remotes recognized as that provider. Prefer the configured trusted remote when it matches; otherwise require exactly one matching remote. Fail scope resolution when no matching remote exists or more than one remains. Thus `!123` cannot silently select GitHub or fall back to local review.

Read the matching provider reference and capture its normalized metadata and diff. Provider adapters must enumerate and preflight raw endpoints from verified immutable base and head identities before retrieving raw blobs or constructing hunks. Never fall back to local mode when authentication, network, CLI, metadata, or evidence retrieval fails.

A provider adapter owns only remote selection, metadata retrieval, drift lookup, and diff retrieval. It must return the normalized scope fields below. Adding another provider means adding one adapter reference with that contract; it must not alter reviewer prompts, bucketing, cache identities, convergence, or aggregation.

## Path mode

Resolve the canonical repository root and target. Require the target to equal the root or remain beneath it after symlink resolution. Reject external symlink targets and denied components before reading.

For a directory, enumerate entry names and link-aware file metadata in stable repository-relative order before opening any file. Record the repository-root-relative path plus the no-follow identity needed to recognize the same regular file later. Do not traverse directory symlinks or Windows reparse points. Run the complete path preflight over every enumerated path as one batch, so one denied path fails the whole path scope before any binary probe or synthetic hunk is built. Respect Git ignore rules unless trusted committed policy explicitly includes ignored paths.

After preflight succeeds, capture every accepted primary file through Primary input capture below. Perform binary detection and build synthetic hunks only from those captured bytes.

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

First run `git diff --no-ext-diff --no-textconv --raw -z --no-renames <validated-immutable-range>`, enumerate body-free base-tree metadata for exact-copy matching, and perform the complete path preflight over every endpoint and any selected exact-copy source. Only after every candidate is accepted may the orchestrator retrieve accepted raw blobs from the effective base and head objects and construct normalized hunks and relationships internally. Never request content hunks or similarity detection from Git. Pass the validated range as one quoted argument. Never use `git diff --quiet` as revision validation because exit code 1 normally means differences exist.

## Path preflight

Every mode completes this phase before retrieving content diffs, opening reviewed files, materializing snapshots, building prompts, or hashing dependencies. Metadata-only means command output contains statuses, modes, object identities, and paths, but no patch hunks or file bodies.

Build the complete candidate manifest from the mode's raw metadata source. Include every added, deleted, modified, type-changed, and untracked path, plus any unchanged exact-copy source selected by body-free object-ID matching. A later internal rename or copy relationship may use only candidates accepted by this preflight, so both endpoints were accepted even when only the destination will appear as `CHANGED_FILES.path`. A malformed, truncated, or unknown status record fails scope resolution; never guess its paths or status.

Normalize each candidate from its raw path bytes to a strict UTF-8, repository-relative `/`-separated path without a leading `./`; reject an undecodable path rather than applying policy to a lossy name. Reject empty paths, absolute paths, NULs, `.` or `..` traversal components, paths outside the repository, and any component matching `deny_components`. Reject symlinks, Windows reparse points, and external canonical targets using metadata APIs that inspect links without traversing them: retain type and stable file identity for mutable local tracked, local untracked, and path-mode primary inputs; use the committed `HEAD` tree modes for local base-side paths; and use verified tree modes from the immutable effective diff base and head objects for ref/range and remote inputs. Validate both object sides when they exist, including rename/copy sources in the effective diff base and destinations in the head.

Treat the manifest as one atomic scope. If any candidate fails, emit `Failed at scope resolution: <reason>.` before any candidate content reaches tool output or model context. Do not retrieve the allowed members of a mixed allowed/denied scope, do not construct a partial snapshot, and do not hash any dependency.

After acceptance, freeze the candidate manifest as the only content-read and relationship allowlist. Content retrieval must use the same immutable identities as enumeration. Derive the final changed-file manifest as a subset after raw comparison and internal relationship detection. Cross-check every normalized file header and status against the accepted candidates; any mismatch fails scope resolution and never expands the allowlist.

## Primary input capture

This pre-snapshot phase owns mutable primary inputs only: accepted local tracked files with unstaged bodies, accepted local untracked files, and accepted path-mode files. Open each file through a platform secure-open adapter anchored to a repository-root capability. The adapter must reject traversal through symlinks or reparse points in every path component, open the leaf without following a link, prove that post-open metadata has the same stable file identity and regular-file type recorded by preflight, and prove that the opened target remains beneath the repository root before reading any bytes. After reading, repeat handle-based identity, type, size, and change-time checks and reject a file that changed during capture. POSIX adapters may use descriptor-relative component traversal, no-follow flags, and before/after `fstat`; Windows adapters may use root-scoped handles, open-reparse-point semantics, stable file IDs, final-path verification, and equivalent before/after file information. An equivalent platform adapter is valid only when it proves all of these invariants; if the host cannot provide one, fail scope resolution before reading any primary bytes rather than weakening the checks.

For path mode, perform binary detection and construct synthetic hunks only from the retained bytes. For local mode, retain unstaged tracked and untracked bytes as separate input sets; staged content comes only from the retained stage-0 index identities. Any open, type, identity, or containment mismatch fails the complete atomic scope without using content already captured from another member; never fall back to a path-based reopen. Primary capture never refers to a snapshot root, because snapshot materialization has not occurred yet.

## Immutable review context

Only after the complete path preflight and every mode-owned primary capture or immutable content retrieval succeeds, create one stable snapshot capability for the normalized reviewed state. Enumerate and retain the complete logical reviewed tree as path, mode, and object-ID or captured-byte identity metadata without reading any additional blob body. Build the reviewer-visible context root as a safe projection: validate each path against containment, denied-component, symlink, reparse-point, platform-name, and case-collision rules before its blob read; never read or materialize a denied, link-shaped, or unrepresentable entry. Write only accepted raw blob or captured bytes directly into an orchestrator-owned private root without invoking checkout, restore, archive, worktree, or clean/smudge filters. Retain the complete logical manifest, including omitted unsafe entries, and verify every projected path's mode and identity against the reviewed state.

Local mode first constructs its tracked-only logical state from committed `HEAD`, retained stage-0 identities, and captured unstaged tracked changes; it derives and freezes the tracked diff before adding captured untracked inputs to the safe context projection and normalized diff. Path mode adds the enumerated synthetic-hunk inputs to the safe projection of committed-`HEAD` surrounding context. Ref/range and remote modes use verified head-tree metadata and raw blob object IDs for the exact reviewed `head_identity`; fetch only the provider-owned immutable change ref when an object is absent. If the safe projection for that exact state cannot be established, mark scope resolution incomplete rather than inspecting a mutable or unrelated checkout.

After snapshot materialization, normalize and validate every surrounding-context or dependency-content path before reading it. Reject denied components, traversal, paths outside the snapshot root, symlinks, and reparse points. Use a platform secure-open adapter anchored to the snapshot-root capability and require the same component-traversal, no-follow leaf, post-open type and identity, and containment guarantees as Primary input capture before reading from the verified handle. If the host cannot prove those guarantees, omit the read and mark its required review evidence or dependency identity incomplete; never fall back to an ordinary path open. These checks apply to unchanged paths absent from the changed-file manifest, so changed code cannot cause an unchanged credential-bearing path to enter model context or dependency hashing. Primary inputs are never reopened here; local and path modes use the bytes retained by Primary input capture. Trusted extension references were separately validated and read from the trusted revision during policy loading; they are not reopened from the reviewed snapshot. Use literal path handling for Git commands that accept a validated repository path. Hash dependency content from the same snapshot and keep it alive until all agents, retries, tracing, and dependency hashes complete; then remove it in orchestrator-owned cleanup.

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

Use the internally derived final manifest, which must be a subset of the accepted candidate manifest, as the authority for changed paths and statuses. Parse `diff --git`, `---`, `+++`, rename/copy headers, and binary markers only to partition accepted content and cross-check it against that final manifest. Ignore `/dev/null`. Preserve first-seen order and statuses.

Before prompt interpolation, replace literal opening and closing frame tags in every value with entity-encoded text. A denied path must already have failed path preflight before any reviewed hunk was retrieved; if later evidence contradicts that invariant, fail scope resolution rather than emitting or hiding the hunk.
