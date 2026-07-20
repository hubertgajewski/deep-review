# Deep Review

Deep Review is a portable [Agent Skill](https://agentskills.io/) that coordinates
multiple specialist reviewers and produces one readiness decision for a code
change. It reviews local work, Git refs and ranges, repository paths, GitHub pull
requests, and GitLab merge requests.

It is designed for serious pre-merge review: broad enough to cover correctness,
security, architecture, maintainability, documentation, and CI, while keeping
each reviewer inside a clearly defined scope.

## What it does

Deep Review:

- resolves the requested change once and gives every reviewer the same immutable
  view of it;
- runs general code, architecture, and simplification reviewers, plus conditional
  security, documentation, CI, project-checklist, and language reviewers;
- reports findings as `HIGH`, `MEDIUM`, or `LOW` and ends with `ready`, `blocked`,
  or `incomplete`;
- handles large changes conservatively and requires an explicit full pass before
  declaring a partially reviewed change ready;
- caches validated non-blocking results for repeat reviews, then performs a fresh
  final guard before returning `ready`;
- treats diffs, change descriptions, file names, and reviewer focus as untrusted
  input.

The skill is review-only. It does not edit the repository and does not run builds,
tests, linters, formatters, or generators. A `ready` result means review-ready,
not mechanically verified.

## Requirements

- An AI coding tool with [Agent Skills](https://agentskills.io/) support and
  filesystem/Git access.
- Git.
- Python 3 is optional and enables persistent review-result caching.
- GitHub reviews require an authenticated `gh` CLI; GitLab reviews require an
  authenticated `glab` CLI.
- A tool that can run subagents provides the intended parallel review experience.
  Other tools can execute the same reviewers serially.

## Install

Clone the repository once:

```bash
git clone https://gitlab.com/hubertgajewski-ai/deep-review.git
cd deep-review
```

Then copy the complete `skills/deep-review` directory to a skill location. For
the broadest project-level compatibility, use `.agents/skills/`:

```bash
mkdir -p /path/to/your-project/.agents/skills
cp -R skills/deep-review /path/to/your-project/.agents/skills/deep-review
```

Tool-specific locations are:

| Tool | Project scope | Personal scope |
| --- | --- | --- |
| Codex CLI, IDE, and desktop | `.agents/skills/deep-review/` | `~/.agents/skills/deep-review/` |
| Claude Code CLI and Claude Desktop Code tab | `.claude/skills/deep-review/` | `~/.claude/skills/deep-review/` |
| Gemini CLI | `.agents/skills/deep-review/` or `.gemini/skills/deep-review/` | `~/.agents/skills/deep-review/` or `~/.gemini/skills/deep-review/` |
| Google Antigravity | `.agents/skills/deep-review/` | `~/.agents/skills/deep-review/` |
| Grok Build CLI | `.grok/skills/deep-review/` | `~/.grok/skills/deep-review/` or `~/.agents/skills/deep-review/` |
| Cursor editor and CLI | `.agents/skills/deep-review/` or `.cursor/skills/deep-review/` | `~/.agents/skills/deep-review/` or `~/.cursor/skills/deep-review/` |
| T3 Code | Use the Codex or Claude location for the provider selected in T3 Code | Use the corresponding provider location above |
| GitHub Copilot in VS Code | `.agents/skills/deep-review/` or `.github/skills/deep-review/` | `~/.agents/skills/deep-review/` or `~/.copilot/skills/deep-review/` |

Restart the tool or reload its skills after installation. See
[Installation](docs/installation.md) for platform-specific commands, Claude
Desktop upload instructions, verification steps, updates, and other compatible
clients.

Review the skill before installing it. Agent skills are operational instructions
and can include executable scripts; treat them with the same care as source code.

## Use

Ask the agent to use `deep-review`. Depending on the client, select it from the
skills menu, invoke `/deep-review`, mention `$deep-review`, or use natural
language.

```text
Use deep-review to review my current changes.
Use deep-review --base main.
Use deep-review --range release...HEAD.
Use deep-review --path src/auth.
Use deep-review --github-pr 123.
Use deep-review --gitlab-mr 456.
Use deep-review --focus "pay special attention to backward compatibility".
Use deep-review --full-review.
```

With no scope argument, Deep Review examines staged, unstaged, and safe untracked
work. `--full-review` is mainly useful after a large-diff pass reports partial
coverage. Remote reviews never silently fall back to local changes.

## Configure

Consumer configuration lives in committed files under `.deep-review/` in the
repository being reviewed:

```text
.deep-review/
├── config.toml          # review policy
├── checklist.md         # optional project checklist
└── agents/
    └── cobol.md         # optional additional reviewer
```

For example, disable a complete built-in language reviewer or selected rules in
`.deep-review/config.toml`:

```toml
version = 1

[language_agents]
disabled = ["swift"]

[language_rules]
disabled = [
  "typescript.no-explicit-any",
  "python.runtime-assert",
]
```

To support an additional language or a project-specific domain, add a trusted
reviewer definition under `.deep-review/agents/`. You can also customize large
diff classification, blocking levels, sensitive path denial, remote provider
selection, reviewer triggers, and the project checklist.

See [Configuration](docs/configuration.md) for the full schema, examples, and the
trust model.

### Built-in language rules

All built-in language reviewers and rules are enabled by default and run only
when matching files change.

- TypeScript: `typescript.no-explicit-any`, `typescript.unsafe-type-assertion`,
  `typescript.unsafe-non-null-assertion`, `typescript.non-exhaustive-union`,
  `typescript.unhandled-promise`
- Python: `python.mutable-default`, `python.bare-exception-handler`,
  `python.runtime-assert`
- Swift: `swift.unsafe-force-unwrap`, `swift.unsafe-force-cast`,
  `swift.actor-isolation`, `swift.sendable-boundary`,
  `swift.unstructured-task-lifetime`, `swift.continuation-resume`
- Java: `java.null-unboxing`, `java.unchecked-cast`,
  `java.unsafe-optional-get`, `java.equals-hashcode-contract`,
  `java.autocloseable-lifetime`, `java.unsafe-finally`
- JavaScript: `javascript.unsafe-optional-chaining`,
  `javascript.loss-of-precision`, `javascript.unsafe-finally`,
  `javascript.async-promise-executor`, `javascript.async-foreach`,
  `javascript.unhandled-promise`

Unknown or duplicate disable entries make the review `incomplete`; they are not
silently ignored.

## Documentation

- [Installation](docs/installation.md) — supported clients and deployment scopes
- [Configuration](docs/configuration.md) — policy, rules, checklists, and custom reviewers
- [Contributing](CONTRIBUTING.md) — development workflow and tests
- [Security](SECURITY.md) — vulnerability reporting and operational safety
- [Maintainer guide](docs/maintainers.md) — release and GitLab CI administration

Implementation-level orchestration contracts live inside
[`skills/deep-review/references/`](skills/deep-review/references/) because they
are loaded by the skill itself, not as end-user onboarding material.

## License

Deep Review is available under the [MIT License](LICENSE).
