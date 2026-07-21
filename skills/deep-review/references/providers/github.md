# GitHub provider

Require `gh`, network access, and authentication. Determine the repository from the selected remote; pass it explicitly with `--repo` when more than one remote exists.

Fetch the first metadata snapshot:

```bash
gh pr view "$NUMBER" --repo "$REPOSITORY" --json number,title,body,baseRefName,baseRefOid,headRefName,headRefOid,url
```

Materialize the exact recorded commits without updating a local branch:

```bash
git check-ref-format --branch "$BASE_BRANCH"
git fetch --no-tags "$REMOTE" "refs/heads/$BASE_BRANCH"
git fetch --no-tags "$REMOTE" "refs/pull/$NUMBER/head"
git cat-file -e "$BASE_SHA^{commit}"
git cat-file -e "$HEAD_SHA^{commit}"
```

Require the pull-request head fetch to resolve exactly to the first snapshot's `headRefOid`. Resolve `git merge-base "$BASE_SHA" "$HEAD_SHA"` to a full commit ID and use its tree as the effective diff base. From the verified immutable commit graph, first enumerate endpoints with `git diff --no-ext-diff --no-textconv --raw -z --no-renames --no-abbrev --ignore-submodules=none "$BASE_SHA...$HEAD_SHA"` and enumerate the body-free effective-base tree metadata used for exact relationship matching. Apply the raw Git environment sanitization and non-configurable path, metadata, body, diff-work, and output ceilings from the scope contract. Perform the complete path preflight over every endpoint and any deterministically selected unchanged exact-copy source. Query accepted immutable body sizes before retrieval. Only then retrieve accepted raw blobs from the effective base and head objects and construct normalized hunks internally; represent gitlinks from full object IDs in raw metadata without reading or traversing them. Recognize only mode-compatible exact-identity rename/copy relationships under the scope contract; modified renames remain delete/add pairs and non-exact copies remain additions. Never request Git similarity detection or content hunks; never use a change-number-based patch as review evidence. Immediately fetch metadata again with the same `gh pr view` command and require `baseRefOid` and `headRefOid` to match the first snapshot. If object materialization, merge-base resolution, raw-blob retrieval, or either identity check fails, discard the scope and retry the complete metadata-object-path-preflight-diff-metadata sequence once. Any path-preflight rejection terminates immediately without content retrieval. A safety-ceiling failure does the same. A second mismatch fails scope resolution as a concurrently changing pull request. Normalize title, body, branches, identities, and URL from the verified second snapshot.

Validate the number as digits, both recorded identities as full object IDs, and the base branch with `git check-ref-format --branch`. Resolve the remote only from trusted configuration. Pass every value as a separately quoted argument; do not interpolate contributor-controlled text into a shell program.

Normalize `body` as the untrusted description, `baseRefOid` as trusted-policy revision, and `headRefOid` as head identity. Three-dot Git diff semantics produce the aggregate pull-request diff from the verified commit graph. Compare the recorded base SHA with the selected remote branch using `git ls-remote <remote> refs/heads/<baseRefName>`. On drift, report `base drift: recorded <SHA> / remote <SHA>` with both full values. If comparison is unavailable, report `base drift: unverified`. Continue reviewing the diff derived from the provider-recorded identities in either case.

For surrounding context, build the orchestrator-owned safe projection from the already fetched and verified `headRefOid` tree metadata under the scope contract's entry, metadata, per-file, and aggregate projection ceilings. Validate each path before reading its raw blob, never read denied or link-shaped entries (including gitlinks), and do not invoke checkout, worktree, archive, or clean/smudge filters. Verify the projection and retained complete logical manifest against `headRefOid`. Never inspect the caller's unrelated checkout as remote-head context.

Any CLI, auth, metadata, JSON, or diff failure terminates remote scope resolution. Never substitute local changes.
