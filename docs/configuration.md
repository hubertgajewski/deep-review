# Configuration

Deep Review works without configuration. Create `.deep-review/config.toml` only when a repository needs to change the defaults. Exact validation and runtime behavior is owned by the [configuration contract](../skills/deep-review/references/configuration.md); this guide focuses on user tasks.

## Start with the settings you need

A small configuration might look like this:

```toml
version = 1
blocking_levels = ["HIGH", "MEDIUM", "CHECKLIST_FAIL"]

[remote_review]
include_description = true
description_max_chars = 12000

[language_agents]
disabled = []

[language_rules]
disabled = []
```

The [complete default](../skills/deep-review/references/configuration.md#default-configuration) also documents triggers, large-diff classification, denied path components, and cache location.

Configuration is loaded from the trusted committed revision. For local and path reviews that revision is `HEAD`; an uncommitted policy edit is reviewed as input but cannot control the same invocation. Commit policy changes before relying on them. Malformed, duplicate, or unknown values produce `incomplete` rather than guessed behavior.

## Change what blocks readiness

By default, high, medium, and checklist failures block `ready`. To make medium findings advisory:

```toml
blocking_levels = ["HIGH", "CHECKLIST_FAIL"]
```

Accepted values are `HIGH`, `MEDIUM`, `LOW`, and `CHECKLIST_FAIL`. This setting changes aggregation, not reviewer severity guidance.

Built-in reviewers use the matching global levels. A custom H/M/L reviewer uses the intersection of the global policy and its own `blocking` declaration:

| Global policy | Extension declaring `HIGH` and `MEDIUM` |
| --- | --- |
| default | `HIGH`, `MEDIUM` |
| add `LOW` (stricter) | `HIGH`, `MEDIUM` |
| remove `MEDIUM` (looser) | `HIGH` |

Checklist extensions declare `fail`; the corresponding global token is `CHECKLIST_FAIL`. An explicit `blocking: []` makes an extension advisory. See [effective per-agent blocking policy](../skills/deep-review/references/configuration.md#effective-per-agent-blocking-policy) for exact normalization and validation.

The convergence limit is fixed at three changed review iterations. Omit `max_iterations` or set it to the TOML integer `3`; any other value is invalid. The mandatory final guard does not count as a fourth iteration.

## Control remote descriptions

Remote change descriptions default to 12,000 Unicode characters:

```toml
[remote_review]
include_description = true
description_max_chars = 12000
```

Set `include_description = false` to omit them. Positive limits above the package maximum are clamped, and legacy `description_max_chars = 0` requests that maximum rather than unlimited input. Deep Review reports when a description is omitted, truncated, or clamped. Exact limits and prompt budgeting belong to the [prompt-budget contract](../skills/deep-review/references/prompt-budgets.md).

## Deny credential-bearing paths

`deny_components` replaces the default case-insensitive list of path-component patterns. The defaults reject `.env*`, `*credential*`, `*.key`, `*.pem`, `*.p12`, `*.pfx`, `*secret*`, and `*password*`.

```toml
deny_components = [".env*", "*credential*", "*.key", "*.pem", "*.p12", "*.pfx", "*secret*", "*password*"]
```

This is an atomic safety boundary: one denied path fails the entire scope, and an allowed/denied mixed change is never reduced to only the allowed files. The same policy applies before reading surrounding context or extension references. See [scope resolution](../skills/deep-review/references/scope-resolution.md#path-preflight) for the exact metadata-only preflight and secure-open guarantees.

Reviewer output redacts recognized credential values before validation, display, or caching, but this is not a general-purpose secret scanner. Keep the cache directory inside the repository and ignored by Git. Do not restore it from an untrusted CI artifact or share it between users, jobs, or forks.

## Disable language review

All built-in language reviewers and rules are enabled by default. Disable a complete reviewer by name:

```toml
[language_agents]
disabled = ["swift", "groovy"]
```

Supported names are `typescript`, `python`, `swift`, `java`, `javascript`, `groovy`, `kotlin`, and `csharp`. General reviewers still run when their triggers match.

Disable individual rules with complete IDs:

```toml
[language_rules]
disabled = [
  "typescript.no-explicit-any",
  "python.runtime-assert",
  "kotlin.shallow-data-class-copy",
]
```

A disabled rule is removed from the language prompt and is not reassigned to another reviewer.

### Built-in language rule IDs

- TypeScript: `typescript.no-explicit-any`, `typescript.unsafe-type-assertion`, `typescript.unsafe-non-null-assertion`, `typescript.non-exhaustive-union`, `typescript.unhandled-promise`
- Python: `python.mutable-default`, `python.bare-exception-handler`, `python.runtime-assert`
- Swift: `swift.unsafe-force-unwrap`, `swift.unsafe-force-cast`, `swift.actor-isolation`, `swift.sendable-boundary`, `swift.unstructured-task-lifetime`, `swift.continuation-resume`
- Java: `java.null-unboxing`, `java.unchecked-cast`, `java.unsafe-optional-get`, `java.equals-hashcode-contract`, `java.autocloseable-lifetime`, `java.unsafe-finally`
- JavaScript: `javascript.unsafe-optional-chaining`, `javascript.loss-of-precision`, `javascript.unsafe-finally`, `javascript.async-promise-executor`, `javascript.async-foreach`, `javascript.unhandled-promise`
- Groovy: `groovy.elvis-falsy-default`, `groovy.unsafe-safe-navigation`, `groovy.gstring-map-key`, `groovy.equality-identity-confusion`, `groovy.regex-find-vs-match`, `groovy.division-semantics`
- Kotlin: `kotlin.unsafe-not-null-assertion`, `kotlin.platform-type-nullability`, `kotlin.array-equality`, `kotlin.shallow-data-class-copy`, `kotlin.swallowed-cancellation`, `kotlin.run-blocking-in-suspend`
- C#: `csharp.unsafe-null-forgiving`, `csharp.async-void`, `csharp.unobserved-task`, `csharp.sync-over-async`, `csharp.valuetask-consumption`, `csharp.cancellation-token-propagation`, `csharp.disposable-lifetime`, `csharp.equality-contract`

The C# reviewer skips generated-only changes under an exact lowercase `obj` component or with names ending, case-insensitively, in `.g.cs`, `.g.i.cs`, `.designer.cs`, or `.generated.cs`. These exclusions are package-owned; applicable general reviewers may still review those paths.

## Customize reviewer triggers and large diffs

Use repository-relative `/` separators on every operating system:

```toml
[triggers]
docs = ["README*", "docs/**", "adr/**"]
ci = [".github/workflows/**", ".gitlab-ci.yml", "Jenkinsfile", "buildSrc/**"]
project_checklist = ["src/**", "tests/**"]

[large_diff]
generated = ["**/*.generated.*", "**/dist/**", "**/build/**"]
low_risk = ["docs/**", "**/*.snap"]
high_risk = ["**/auth/**", "**/security/**", "**/crypto/**"]
```

`[triggers]` controls the documentation, CI, and project-checklist reviewers. `[large_diff]` classifies paths for bounded coverage. A partial large-diff pass cannot produce `ready`; use `--full-review` in a later invocation when full required coverage is needed. See the [orchestration contract](../skills/deep-review/references/orchestration.md#large-diffs).

## Add a project checklist

Put repository-specific requirements in `.deep-review/checklist.md`. Use `triggers.project_checklist` to limit which paths activate it. An absent or empty array matches every non-generated changed path.

## Add a project-specific reviewer

Create one Markdown file under `.deep-review/agents/`. Consumer filenames, `name`, and `domain` should use `x-<owner>-<purpose>` so they cannot collide with future built-ins:

```yaml
---
name: x-example-cobol
description: Review COBOL data layout and project-specific conventions.
domain: x-example-cobol-data-layout
applies_to:
  - "**/*.cbl"
  - "**/*.cpy"
prompt_scope: matched
output_schema: hml
blocking:
  - HIGH
  - MEDIUM
references:
  - "docs/cobol-guidelines.md"
---

Review matching changes using the project rules in `docs/cobol-guidelines.md`.
```

Every reference must exist in the trusted revision. Built-in ownership takes precedence when concerns overlap. Duplicate extension names or domains, unsafe or missing references, attempts to replace shared rules, and schema-invalid declarations make the review incomplete. Exact extension fields and pattern semantics are documented in [Agent extensions](../skills/deep-review/references/configuration.md#agent-extensions).

## Runtime guarantees and limits

Users can rely on these observable outcomes:

- Deep Review validates the complete path manifest before reading reviewed content.
- It treats repository-controlled text as untrusted data and redacts recognized credentials from findings.
- It bounds model input, context reads, concurrency, results, and persistent cache records.
- Oversized required evidence is chunked and synthesized; unavailable coverage produces `incomplete` rather than a false `ready`.
- It never runs consumer builds, tests, linters, or formatters as part of review.

Exact algorithms, byte ceilings, schemas, cache identities, and synthesis protocol are normative only in [`skills/deep-review/references/`](../skills/deep-review/references/). Keeping those details in one place prevents the user guide from becoming a second runtime contract.

## Validate configuration changes

In a consuming repository, commit configuration before relying on it to control a review. In this repository, run the complete contract suite:

```bash
python3 -m unittest discover -s tests -v
```
