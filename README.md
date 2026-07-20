# Deep Review

Deep Review is a configurable, review-only Agent Skill that coordinates specialized reviewers over repository changes. It can review uncommitted work, Git references and ranges, selected paths, GitHub pull requests, and GitLab merge requests, then aggregate the results into a single readiness decision.

## What it does

- Resolves the requested review scope once and gives every reviewer a consistent view of the change.
- Runs general correctness, security, architecture, simplification, documentation, CI, and project-checklist reviews when relevant.
- Adds language-semantic review for supported file types.
- Reports findings with consistent severities and returns `ready`, `blocked`, or `incomplete`.
- Reuses validated nonblocking results during repeated fix-and-review loops while requiring a fresh final guard before reporting readiness.

## Important boundaries

Deep Review reviews code; it does not edit consumer source files or apply fixes. Diffs, change-request descriptions, paths, checklists, and reviewer focus are treated as untrusted input. A `ready` result means the configured review completed without blockers—it does not claim that builds, tests, linters, or other project validation passed.

## Quick start

1. [Install the skill](docs/installation.md) for your AI client.
2. Open the repository you want to review.
3. Ask the client to use Deep Review:

```text
Use the deep-review skill to review my current repository changes.
```

Common scopes include:

```text
Use deep-review --base main
Use deep-review --range release..HEAD
Use deep-review --path src/payments
Use deep-review --github-pr 123
Use deep-review --gitlab-mr 123
Use deep-review --focus "pay particular attention to retry behavior"
```

The GitHub and GitLab modes require their respective authenticated command-line clients. See [installation](docs/installation.md) for client-specific locations and verification steps.

## Built-in review coverage

The general roster covers correctness, security, architecture, simplification, documentation, CI, and an optional project checklist. Matching changes also receive one repository-neutral language review for each supported language:

- TypeScript
- Python
- Swift
- Java
- JavaScript
- Groovy, including Gradle Groovy DSL and Jenkins Shared Libraries
- Kotlin, including Gradle Kotlin DSL

Language reviewers own only their documented language-semantic rules. General concerns such as dead imports, unused symbols, runtime correctness, security, architecture, and simplification remain with the corresponding general reviewers. The complete rule catalog is in [Configuration](docs/configuration.md#built-in-language-rules).

## Configuration

All built-in language reviewers and rules are enabled by default. A trusted `.deep-review/config.toml` can disable a complete language reviewer or selected rules:

```toml
[language_agents]
disabled = ["swift"]

[language_rules]
disabled = ["typescript.no-explicit-any", "python.runtime-assert"]
```

You can also adjust blocking levels, diff classification, triggers, remote-review settings, and add project-specific reviewers—for example, a COBOL reviewer backed by your own guidelines. See [Configuration](docs/configuration.md) for supported fields, safe extension naming, and examples.

## Documentation

- [Installation](docs/installation.md): supported clients, paths, operating-system notation, and update options
- [Configuration](docs/configuration.md): settings, language rules, and custom reviewers
- [Contributing](CONTRIBUTING.md): development workflow and validation
- [Security policy](SECURITY.md): private vulnerability reporting
- [Maintainer operations](docs/maintainers.md): CI and repository administration

The files under `skills/deep-review/references/` are the normative runtime contract. User guides summarize that contract and link to it where implementation-level detail matters.

## License

Deep Review is available under the [MIT License](LICENSE).
