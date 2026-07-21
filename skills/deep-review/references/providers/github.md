# GitHub provider

Require `gh`, network access, and authentication. Determine the repository from the selected remote; pass it explicitly with `--repo` when more than one remote exists.

Fetch the first metadata snapshot:

```bash
gh pr view "$NUMBER" --repo "$REPOSITORY" --json number,title,body,baseRefName,baseRefOid,headRefName,headRefOid,url
```

Validate the provider-specific refs before asking the shared Remote evidence transport to fetch their metadata into its isolated blobless store:

```bash
git check-ref-format --branch "$BASE_BRANCH"
refs/heads/$BASE_BRANCH
refs/pull/$NUMBER/head
```

Require the fetched head ref to resolve exactly to the first snapshot's `headRefOid`. Resolve `git merge-base "$BASE_SHA" "$HEAD_SHA"` to a full commit ID and use its tree as the effective diff base. Apply the shared Remote evidence transport to the verified immutable range `"$BASE_SHA...$HEAD_SHA"`; never use a change-number-based patch as review evidence. Immediately fetch metadata again with the same `gh pr view` command and require `baseRefOid` and `headRefOid` to match the first snapshot. If metadata materialization, merge-base resolution, bounded raw-blob retrieval, or either identity check fails, discard the scope and retry the complete metadata-object-path-preflight-diff-metadata sequence once. Any path-preflight rejection terminates immediately without content retrieval. A safety-ceiling failure does the same. A second mismatch fails scope resolution as a concurrently changing pull request. Normalize title, body, branches, identities, and URL from the verified second snapshot.

Validate the number as digits, both recorded identities as full object IDs, and the base branch with `git check-ref-format --branch`. Resolve the remote only from trusted configuration. Pass every value as a separately quoted argument; do not interpolate contributor-controlled text into a shell program.

Normalize `body` as the untrusted description, `baseRefOid` as trusted-policy revision, and `headRefOid` as head identity. Three-dot Git diff semantics produce the aggregate pull-request diff from the verified commit graph. Compare the recorded base SHA with the selected remote branch using `git ls-remote <remote> refs/heads/<baseRefName>`. On drift, report `base drift: recorded <SHA> / remote <SHA>` with both full values. If comparison is unavailable, report `base drift: unverified`. Continue reviewing the diff derived from the provider-recorded identities in either case.

Build the shared orchestrator-owned safe projection from the verified `headRefOid` tree metadata and exact-object transport. Verify its retained complete logical manifest against `headRefOid`; never inspect the caller's unrelated checkout as remote-head context.

Any CLI, auth, metadata, JSON, or diff failure terminates remote scope resolution. Never substitute local changes.
