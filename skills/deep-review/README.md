# Deep Review plugin

Deep Review is a review-only Agent Skill that coordinates specialized reviewers over local changes, Git references and ranges, repository paths, GitHub pull requests, and GitLab merge requests. This directory is both the canonical portable skill package and the Claude Code plugin root.

Deep Review does not edit consumer source files. A `ready` result means the configured review completed without blockers; it does not claim that builds, tests, or linters passed.

Oversized reviewer scopes are split deterministically. Multi-chunk reviewers use
bounded, credential-redacted handoffs and a package-owned synthesis stage to check
cross-chunk relationships without passing an unbounded raw diff. Synthesis failure
remains fail-closed; single-chunk reviews do not pay for an extra model call.

## Invoke

When Deep Review is loaded locally as a Claude Code plugin, the fully qualified command is:

```text
/deep-review:deep-review --base main
```

On Claude Code 2.1.216 and newer, `/deep-review --base main` is also available as a convenience alias when no other command has that name. Natural-language invocation remains portable across clients:

```text
Use the deep-review skill to review my current repository changes.
```

## Test a local checkout

From the repository root:

```bash
claude plugin validate --strict skills/deep-review
claude --plugin-dir ./skills/deep-review
```

In the new Claude Code session, invoke `/deep-review:deep-review` against a small known change and confirm that the review reaches a documented terminal state.

## Requirements and documentation

Deep Review requires Git. Remote pull-request and merge-request modes require the corresponding authenticated GitHub or GitLab command-line client. Python 3 enables the bundled deterministic cache and result-processing helpers. Host filesystem capabilities and the trust model are documented in the [installation guide](https://gitlab.com/hubertgajewski-ai/deep-review/-/blob/main/docs/installation.md).

For configuration, supported reviewers, and complete usage guidance, see the [Deep Review repository](https://gitlab.com/hubertgajewski-ai/deep-review).
