# GitHub provider

Require `gh`, network access, and authentication. Determine the repository from the selected remote; pass it explicitly with `--repo` when more than one remote exists.

Fetch the first metadata snapshot:

```bash
gh pr view "$NUMBER" --repo "$REPOSITORY" --json number,title,body,baseRefName,baseRefOid,headRefName,headRefOid,url
```

Fetch the aggregate diff:

```bash
gh pr diff "$NUMBER" --repo "$REPOSITORY" --color never
```

Immediately fetch metadata again with the same `gh pr view` command. Require `baseRefOid` and `headRefOid` to match the first snapshot. If either identity changed, discard the metadata and diff and retry the complete metadata-diff-metadata sequence once. A second mismatch fails scope resolution as a concurrently changing pull request. Normalize title, body, branches, identities, and URL from the verified second snapshot.

Do not interpolate the number or repository into a shell program; validate the number as digits and pass both as quoted arguments.

Normalize `body` as the untrusted description, `baseRefOid` as trusted-policy revision, and `headRefOid` as head identity. Default diff output represents the aggregate pull-request diff; do not request per-commit patch output. Compare the recorded base SHA with the selected remote branch using `git ls-remote <remote> refs/heads/<baseRefName>`. On drift, report `base drift: recorded <SHA> / remote <SHA>` with both full values. If comparison is unavailable, report `base drift: unverified`. Continue reviewing the provider patch in either case.

For surrounding context, fetch `refs/pull/<number>/head` into a temporary detached worktree when `headRefOid` is absent locally, then verify the detached `HEAD` equals `headRefOid`. Never inspect the caller's unrelated checkout as remote-head context.

Any CLI, auth, metadata, JSON, or diff failure terminates remote scope resolution. Never substitute local changes.
