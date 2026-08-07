# Deep Review

Deep Review is a configurable, review-only Agent Skill that coordinates specialized reviewers over repository changes and returns one result: `ready`, `blocked`, or `incomplete`.

## Install

Download the verified installer and checksum for your operating system from the [`v1.1.0` GitLab Release](https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.0), then follow the short [installation and update instructions](docs/installation.md#install-from-a-release). The installer supports user and project scope and selects the correct directory from your client ID.

## Quick start

1. [Install Deep Review](docs/installation.md) for your AI client.
2. Open the repository you want to review.
3. Ask your client:

```text
Use the deep-review skill to review my current repository changes.
```

The final status tells you what to do next:

| Status | Meaning |
| --- | --- |
| `ready` | The configured review completed without blockers. Run the repository's normal tests and checks separately. |
| `blocked` | One or more findings must be addressed before readiness. Fix them and run Deep Review again. |
| `incomplete` | Required evidence was unavailable or could not be reviewed safely. Resolve the reported gap and retry. |

Deep Review does not edit consumer source files or apply fixes. A `ready` result is review readiness, not proof that builds, tests, linters, or other project validation passed.

## Choose a review scope

Natural language works in every supported client. Clients may also expose a prefix:

| Client | Example |
| --- | --- |
| Claude Code | `/deep-review --base main` |
| Codex CLI and IDE | `$deep-review --base main` |
| Devin | `@skills:deep-review --base main` |
| Windsurf Cascade | `@deep-review --base main` |

Use the syntax supported by your client with one of these selectors:

| Task | Selector |
| --- | --- |
| Review current changes | no selector |
| Compare with a base branch | `--base main` |
| Review a Git range | `--range release..HEAD` |
| Review a file or directory | `--path src/payments` |
| Review a GitHub pull request | `--github-pr 123` |
| Review a GitLab merge request | `--gitlab-mr 123` |
| Prioritize a concern | `--focus "pay particular attention to retry behavior"` |

Remote shorthand is also supported: `Use deep-review #123` infers the provider from the trusted repository remote, while `Use deep-review !123` explicitly selects GitLab. Prefer `--github-pr` or `--gitlab-mr` when provider selection should be unambiguous.

Remote reviews require the corresponding authenticated GitHub or GitLab command-line client. See [Installation](docs/installation.md#requirements).

## Important safety boundary

A skill stored inside a repository is trusted client configuration. Do not initiate a review from an untrusted checkout that can replace that copy. To review a pull request, merge request, or fork safely, start the client in a separate trusted checkout and invoke a user- or administrator-installed Deep Review with `--github-pr` or `--gitlab-mr`. See the [installation trust model](docs/installation.md#review-untrusted-remote-changes).

Diffs, descriptions, paths, checklists, and reviewer focus are treated as untrusted input. Deep Review fails closed when it cannot establish the required evidence or filesystem guarantees.

## What it reviews

The general roster covers correctness, security, architecture, simplification, documentation, CI, and an optional project checklist. Matching changes also receive repository-neutral language review for:

- TypeScript
- Python
- Swift
- Java
- JavaScript
- Groovy, including Gradle Groovy DSL and Jenkins Shared Libraries
- Kotlin, including Gradle Kotlin DSL
- C#, including Razor C# regions

Language reviewers own only their documented language-semantic rules. General correctness, security, architecture, and simplification remain with the corresponding general reviewers.

Deep Review safely bounds descriptions, model input, context reads, parallel work, results, and cache records. Oversized reviews are split and synthesized under package-owned limits; unavailable coverage produces `incomplete`, never a false `ready`. Exact behavior is defined by the [runtime contracts](skills/deep-review/references/).

## Configuration

Configuration is optional. Defaults enable all matching reviewers and make high, medium, and checklist failures blocking. Create `.deep-review/config.toml` only when you need to change behavior:

```toml
[language_agents]
disabled = ["swift"]

[language_rules]
disabled = ["typescript.no-explicit-any", "python.runtime-assert"]
```

See [Configuration](docs/configuration.md) for task-oriented examples, supported language-rule IDs, triggers, checklists, and project-specific reviewers.

## Documentation

- [Installation](docs/installation.md): prerequisites, client locations, installation, verification, and updates
- [Configuration](docs/configuration.md): user-settable behavior and examples
- [Contributing](CONTRIBUTING.md): development workflow and validation
- [Security policy](SECURITY.md): private vulnerability reporting
- [Maintainer operations](docs/maintainers.md): CI and repository administration

The files under `skills/deep-review/references/` are the normative runtime contract. User guides describe tasks and observable behavior; the references own exact algorithms, schemas, and limits.

## License

Deep Review is available under the [MIT License](LICENSE).
