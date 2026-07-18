# GitLab provider

Require `glab`, network access, and authentication. Determine the repository from the selected remote; pass it explicitly with `--repo` when more than one remote exists.

Fetch the first metadata snapshot:

```bash
glab mr view "$NUMBER" --repo "$REPOSITORY" --output json
```

Fetch the raw patch:

```bash
glab mr diff "$NUMBER" --repo "$REPOSITORY" --raw --color=never
```

Immediately fetch metadata again with the same `glab mr view` command. Require `diff_refs.base_sha` and `diff_refs.head_sha` to match the first snapshot. If either identity changed, discard the metadata and patch and retry the complete metadata-patch-metadata sequence once. A second mismatch fails scope resolution as a concurrently changing merge request. Normalize title, description, branches, identities, and URL from the verified second snapshot.

Do not interpolate the number or repository into a shell program; validate the number as digits and pass both as quoted arguments.

Normalize JSON fields `description`, `title`, `target_branch`, `source_branch`, `diff_refs.base_sha`, `diff_refs.head_sha`, and `web_url`. If a GitLab version omits `diff_refs`, retrieve both metadata snapshots through `glab api projects/<encoded-project>/merge_requests/<number>`; failure remains a remote-scope failure.

Use the recorded base SHA as trusted-policy revision. Compare it with the selected remote target branch using `git ls-remote <remote> refs/heads/<target_branch>`. On drift, report `base drift: recorded <SHA> / remote <SHA>` with both full values. If comparison is unavailable, report `base drift: unverified`. Continue reviewing the provider patch in either case.

For surrounding context, fetch `refs/merge-requests/<number>/head` into a temporary detached worktree when the recorded head SHA is absent locally, then verify the detached `HEAD` equals that SHA. Never inspect the caller's unrelated checkout as remote-head context.

Any CLI, auth, metadata, JSON, or diff failure terminates remote scope resolution. Never substitute local changes.
