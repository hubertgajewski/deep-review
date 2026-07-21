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

Require the merge-request head fetch to resolve exactly to the first snapshot's `diff_refs.head_sha`. From the verified immutable objects, first enumerate paths with `git diff --name-status -z --find-renames --find-copies-harder "$BASE_SHA" "$HEAD_SHA"`. Perform the complete path preflight from the scope contract, including both sides of every rename or copy, before retrieving content with `git diff --find-renames --find-copies-harder "$BASE_SHA" "$HEAD_SHA"`; never use a change-number-based patch as review evidence. Immediately fetch metadata again with the same `glab mr view` command and require both recorded identities to match the first snapshot. If object materialization, diff retrieval, or either identity check fails, discard the scope and retry the complete metadata-object-path-preflight-diff-metadata sequence once. Any path-preflight rejection terminates immediately without content retrieval. A second mismatch fails scope resolution as a concurrently changing merge request. Normalize title, description, branches, identities, and URL from the verified second snapshot.

Validate the number as digits, both recorded identities as full object IDs, and the target branch with `git check-ref-format --branch`. Resolve the remote only from trusted configuration. Pass every value as a separately quoted argument; do not interpolate contributor-controlled text into a shell program.

Normalize JSON fields `description`, `title`, `target_branch`, `source_branch`, `diff_refs.base_sha`, `diff_refs.head_sha`, and `web_url`. If a GitLab version omits `diff_refs`, retrieve both metadata snapshots through `glab api projects/<encoded-project>/merge_requests/<number>`; failure remains a remote-scope failure.

Use the recorded base SHA as trusted-policy revision. Compare it with the selected remote target branch using `git ls-remote <remote> refs/heads/<target_branch>`. On drift, report `base drift: recorded <SHA> / remote <SHA>` with both full values. If comparison is unavailable, report `base drift: unverified`. Continue reviewing the diff derived from the provider-recorded identities in either case.

For surrounding context, create a temporary detached worktree directly from the already fetched and verified recorded head SHA, then verify the detached `HEAD` equals that SHA. Never inspect the caller's unrelated checkout as remote-head context.

Any CLI, auth, metadata, JSON, or diff failure terminates remote scope resolution. Never substitute local changes.
