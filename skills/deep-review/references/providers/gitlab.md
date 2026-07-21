# GitLab provider

Require `glab`, network access, and authentication. Determine the repository from the selected remote; pass it explicitly with `--repo` when more than one remote exists.

Fetch the first metadata snapshot:

```bash
glab mr view "$NUMBER" --repo "$REPOSITORY" --output json
```

Validate the provider-specific ref before asking the shared Remote evidence transport to fetch its metadata into the isolated blobless store:

```bash
git check-ref-format --branch "$TARGET_BRANCH"
refs/heads/$TARGET_BRANCH
refs/merge-requests/$NUMBER/head
```

Require the fetched head ref to resolve exactly to the first snapshot's `diff_refs.head_sha`. Apply the shared Remote evidence transport to the verified immutable range `"$BASE_SHA" "$HEAD_SHA"`; never use a change-number-based patch as review evidence. Immediately fetch metadata again with the same `glab mr view` command and require both recorded identities to match the first snapshot. If metadata materialization, bounded raw-blob retrieval, or either identity check fails, discard the scope and retry the complete metadata-object-path-preflight-diff-metadata sequence once. Any path-preflight rejection terminates immediately without content retrieval. A safety-ceiling failure does the same. A second mismatch fails scope resolution as a concurrently changing merge request. Normalize title, description, branches, identities, and URL from the verified second snapshot.

Validate the number as digits, both recorded identities as full object IDs, and the target branch with `git check-ref-format --branch`. Resolve the remote only from trusted configuration. Pass every value as a separately quoted argument; do not interpolate contributor-controlled text into a shell program.

Normalize JSON fields `description`, `title`, `target_branch`, `source_branch`, `diff_refs.base_sha`, `diff_refs.head_sha`, and `web_url`. If a GitLab version omits `diff_refs`, retrieve both metadata snapshots through `glab api projects/<encoded-project>/merge_requests/<number>`; failure remains a remote-scope failure.

Use the recorded base SHA as trusted-policy revision. Compare it with the selected remote target branch using `git ls-remote <remote> refs/heads/<target_branch>`. On drift, report `base drift: recorded <SHA> / remote <SHA>` with both full values. If comparison is unavailable, report `base drift: unverified`. Continue reviewing the diff derived from the provider-recorded identities in either case.

Build the shared orchestrator-owned safe projection from the verified recorded head tree metadata and exact-object transport. Verify its retained complete logical manifest against the recorded head SHA; never inspect the caller's unrelated checkout as remote-head context.

Any CLI, auth, metadata, JSON, or diff failure terminates remote scope resolution. Never substitute local changes.
