# GitHub provider

Require `gh`, network access, and authentication. Determine the repository from the selected remote; pass it explicitly with `--repo` when more than one remote exists.

Fetch metadata once:

```bash
gh pr view "$NUMBER" --repo "$REPOSITORY" --json number,title,body,baseRefName,baseRefOid,headRefName,headRefOid,url
```

Fetch the patch:

```bash
gh pr diff "$NUMBER" --repo "$REPOSITORY" --patch --color never
```

Do not interpolate the number or repository into a shell program; validate the number as digits and pass both as quoted arguments.

Normalize `body` as the untrusted description, `baseRefOid` as trusted-policy revision, and `headRefOid` as head identity. Compare the recorded base SHA with the selected remote branch using `git ls-remote <remote> refs/heads/<baseRefName>`. On drift, report `base drift: recorded <SHA> / remote <SHA>` with both full values. If comparison is unavailable, report `base drift: unverified`. Continue reviewing the provider patch in either case.

Any CLI, auth, metadata, JSON, or diff failure terminates remote scope resolution. Never substitute local changes.
