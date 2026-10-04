# Deep Review package

This directory is the canonical portable skill package and the Claude Code plugin root. Deep Review coordinates specialized reviewers over local changes, Git references and ranges, repository paths, GitHub pull requests, and GitLab merge requests.

Deep Review is review-only: it does not edit consumer source files. A `ready` result means the configured review completed without blockers; it does not claim that builds, tests, or linters passed.

## Invoke the Claude plugin

When loaded as a local Claude Code plugin, use the fully qualified command:

```text
/hg-deep-review:deep-review --base main
```

On Claude Code 2.1.216 and newer, `/deep-review --base main` is the short alias available when no other installed command has that name. Other clients should use the portable natural-language invocation or their documented skill prefix.

## Requirements and documentation

Deep Review requires Git. Python 3 optionally enables deterministic cache, result-processing, and quota-enforced remote-fetch helpers; remote review requires the authenticated provider CLI.

- [Quick start and usage](https://gitlab.com/hubertgajewski-ai/deep-review)
- [Installation and trust model](https://gitlab.com/hubertgajewski-ai/deep-review/-/blob/main/docs/installation.md)
- [Configuration](https://gitlab.com/hubertgajewski-ai/deep-review/-/blob/main/docs/configuration.md)
- [Contributor validation](https://gitlab.com/hubertgajewski-ai/deep-review/-/blob/main/CONTRIBUTING.md)

Exact runtime behavior is defined by `SKILL.md` and `references/`. Claude-specific release validation belongs in the repository maintainer guide rather than this portable package landing page.
