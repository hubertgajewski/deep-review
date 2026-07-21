# GitHub provider

Require `gh`, network access, and authentication. Determine the repository from the selected remote; pass it explicitly with `--repo` when more than one remote exists.

Fetch the first metadata snapshot:

```bash
gh pr view "$NUMBER" --repo "$REPOSITORY" --json number,title,body,baseRefName,baseRefOid,headRefName,headRefOid,url
```

Validate the base branch before asking the shared Remote evidence transport to fetch metadata for `refs/heads/$BASE_BRANCH` and `refs/pull/$NUMBER/head` into its isolated blobless store:

```bash
git check-ref-format --branch "$BASE_BRANCH"
```

Require the fetched head ref to resolve exactly to the first snapshot's `headRefOid`. Resolve `git merge-base "$BASE_SHA" "$HEAD_SHA"` to a full commit ID and use its tree as the effective diff base. Apply the shared Remote evidence transport to the verified immutable range `"$BASE_SHA...$HEAD_SHA"`; never use a change-number-based patch as review evidence. Immediately fetch metadata again with the same `gh pr view` command and require `baseRefOid` and `headRefOid` to match the first snapshot. If metadata materialization, merge-base resolution, bounded raw-blob retrieval, or either identity check fails, discard the scope and retry the complete metadata-object-path-preflight-diff-metadata sequence once. Any path-preflight rejection terminates immediately without content retrieval. A safety-ceiling failure does the same. A second mismatch fails scope resolution as a concurrently changing pull request. Normalize title, body, branches, identities, and URL from the verified second snapshot.

Validate the number as digits, both recorded identities as full object IDs, and the base branch with `git check-ref-format --branch`. Resolve the remote only from trusted configuration. Pass every value as a separately quoted argument; do not interpolate contributor-controlled text into a shell program.

Normalize `body` as the untrusted description, `baseRefOid` as trusted-policy revision, and `headRefOid` as head identity. Three-dot Git diff semantics produce the aggregate pull-request diff from the verified commit graph. Compare the recorded base SHA with the selected remote branch using `git ls-remote <remote> refs/heads/<baseRefName>`. On drift, report `base drift: recorded <SHA> / remote <SHA>` with both full values. If comparison is unavailable, report `base drift: unverified`. Continue reviewing the diff derived from the provider-recorded identities in either case.

Build the shared orchestrator-owned safe projection from the verified `headRefOid` tree metadata and exact-object transport. Verify its retained complete logical manifest against `headRefOid`; never inspect the caller's unrelated checkout as remote-head context.

The GitHub adapter's exact-object streaming capability sends an authenticated `GET /repos/{owner}/{repo}/git/blobs/{file_sha}` request with `Accept: application/vnd.github.raw+json`, using the same resolved repository and credential source as metadata retrieval. Require status `200` and expose the raw response body only as a byte stream to the shared private-capture sink; never decode it as JSON, buffer it in the adapter, log it, or return it as tool output. Reject cross-origin redirects and every non-`200` response. The requested `file_sha` is the accepted full object ID, never a path or ref; the shared transport enforces byte limits and verifies the completed Git blob identity.

Any CLI, auth, metadata, JSON, or diff failure terminates remote scope resolution. Never substitute local changes.
