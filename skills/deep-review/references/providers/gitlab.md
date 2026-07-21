# GitLab provider

Require `glab`, network access, and authentication. Determine the repository from the selected remote; pass it explicitly with `--repo` when more than one remote exists.

Fetch the first metadata snapshot:

```bash
glab mr view "$NUMBER" --repo "$REPOSITORY" --output json
```

Materialize the exact recorded commits without updating a local branch:

```bash
git check-ref-format --branch "$TARGET_BRANCH"
git fetch --no-tags "$REMOTE" "refs/heads/$TARGET_BRANCH"
git fetch --no-tags "$REMOTE" "refs/merge-requests/$NUMBER/head"
git cat-file -e "$BASE_SHA^{commit}"
git cat-file -e "$HEAD_SHA^{commit}"
```

Require the merge-request head fetch to resolve exactly to the first snapshot's `diff_refs.head_sha`. From the verified immutable objects, first enumerate endpoints with `git diff --no-ext-diff --no-textconv --raw -z --no-renames --no-abbrev --ignore-submodules=none "$BASE_SHA" "$HEAD_SHA"` and enumerate the body-free base-tree metadata used for exact relationship matching. Apply the raw Git environment sanitization and non-configurable path, metadata, body, diff-work, and output ceilings from the scope contract. Perform the complete path preflight over every endpoint and any deterministically selected unchanged exact-copy source. Query accepted immutable body sizes before retrieval. Only then retrieve accepted raw blobs from the verified base and head objects and construct normalized hunks internally; represent gitlinks from full object IDs in raw metadata without reading or traversing them. Recognize only mode-compatible exact-identity rename/copy relationships under the scope contract; modified renames remain delete/add pairs and non-exact copies remain additions. Never request Git similarity detection or content hunks; never use a change-number-based patch as review evidence. Immediately fetch metadata again with the same `glab mr view` command and require both recorded identities to match the first snapshot. If object materialization, raw-blob retrieval, or either identity check fails, discard the scope and retry the complete metadata-object-path-preflight-diff-metadata sequence once. Any path-preflight rejection terminates immediately without content retrieval. A safety-ceiling failure does the same. A second mismatch fails scope resolution as a concurrently changing merge request. Normalize title, description, branches, identities, and URL from the verified second snapshot.

Validate the number as digits, both recorded identities as full object IDs, and the target branch with `git check-ref-format --branch`. Resolve the remote only from trusted configuration. Pass every value as a separately quoted argument; do not interpolate contributor-controlled text into a shell program.

Normalize JSON fields `description`, `title`, `target_branch`, `source_branch`, `diff_refs.base_sha`, `diff_refs.head_sha`, and `web_url`. If a GitLab version omits `diff_refs`, retrieve both metadata snapshots through `glab api projects/<encoded-project>/merge_requests/<number>`; failure remains a remote-scope failure.

Use the recorded base SHA as trusted-policy revision. Compare it with the selected remote target branch using `git ls-remote <remote> refs/heads/<target_branch>`. On drift, report `base drift: recorded <SHA> / remote <SHA>` with both full values. If comparison is unavailable, report `base drift: unverified`. Continue reviewing the diff derived from the provider-recorded identities in either case.

For surrounding context, build the orchestrator-owned safe projection from the already fetched and verified recorded head tree metadata under the scope contract's entry, metadata, per-file, and aggregate projection ceilings. Validate each path before reading its raw blob, never read denied or link-shaped entries (including gitlinks), and do not invoke checkout, worktree, archive, or clean/smudge filters. Verify the projection and retained complete logical manifest against the recorded head SHA. Never inspect the caller's unrelated checkout as remote-head context.

Any CLI, auth, metadata, JSON, or diff failure terminates remote scope resolution. Never substitute local changes.
