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

Require the pull-request head fetch to resolve exactly to the first snapshot's `headRefOid`. Derive the aggregate review diff from the verified immutable commit graph with `git diff "$BASE_SHA...$HEAD_SHA"`; never use a change-number-based patch as review evidence. Immediately fetch metadata again with the same `gh pr view` command and require `baseRefOid` and `headRefOid` to match the first snapshot. If object materialization or either identity check fails, discard the scope and retry the complete metadata-object-diff-metadata sequence once. A second mismatch fails scope resolution as a concurrently changing pull request. Normalize title, body, branches, identities, and URL from the verified second snapshot.

Validate the number as digits, both recorded identities as full object IDs, and the base branch with `git check-ref-format --branch`. Resolve the remote only from trusted configuration. Pass every value as a separately quoted argument; do not interpolate contributor-controlled text into a shell program.

Normalize `body` as the untrusted description, `baseRefOid` as trusted-policy revision, and `headRefOid` as head identity. Three-dot Git diff semantics produce the aggregate pull-request diff from the verified commit graph. Compare the recorded base SHA with the selected remote branch using `git ls-remote <remote> refs/heads/<baseRefName>`. On drift, report `base drift: recorded <SHA> / remote <SHA>` with both full values. If comparison is unavailable, report `base drift: unverified`. Continue reviewing the diff derived from the provider-recorded identities in either case.

For surrounding context, create a temporary detached worktree directly from the already fetched and verified `headRefOid`, then verify the detached `HEAD` equals `headRefOid`. Never inspect the caller's unrelated checkout as remote-head context.

Any CLI, auth, metadata, JSON, or diff failure terminates remote scope resolution. Never substitute local changes.
