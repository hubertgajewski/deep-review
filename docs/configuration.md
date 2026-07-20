# Configuration

Deep Review uses reviewed repository configuration rather than uncommitted policy changes. The normative behavior is defined in [`skills/deep-review/references/configuration.md`](../skills/deep-review/references/configuration.md); this guide focuses on common user tasks.

## Configuration file

Create `.deep-review/config.toml` in the repository being reviewed. Start with only the settings you need to change. The complete default is documented in the [runtime configuration contract](../skills/deep-review/references/configuration.md#default-configuration).

```toml
version = 1
large_diff_lines = 3000
max_iterations = 3
blocking_levels = ["HIGH", "MEDIUM", "CHECKLIST_FAIL"]
cache_dir = ".deep-review-cache"

[remote_review]
provider = "auto"
remote = "origin"
include_description = true
description_max_chars = 0

[language_agents]
disabled = []

[language_rules]
disabled = []
```

Configuration is loaded from the trusted committed revision. For local and path reviews, that revision is `HEAD`; an uncommitted policy edit is reviewed as input but cannot control the same review. Malformed, duplicate, or unknown values make the result `incomplete` rather than being guessed or ignored.

## Blocking levels

`blocking_levels` controls which global finding severities block readiness. It accepts `HIGH`, `MEDIUM`, `LOW`, and `CHECKLIST_FAIL` without duplicates:

```toml
blocking_levels = ["HIGH", "CHECKLIST_FAIL"]
```

This changes aggregation, not reviewer instructions or severity guidance. A consumer cannot disable the final guard or increase `max_iterations` above 3.

## Disable a language reviewer

All built-in language reviewers are enabled by default. Disable a complete reviewer by name:

```toml
[language_agents]
disabled = ["swift", "groovy"]
```

Supported names are `typescript`, `python`, `swift`, `java`, `javascript`, `groovy`, and `kotlin`. General reviewers still run when their triggers match.

## Disable individual language rules

Use complete rule IDs. A disabled rule is removed from the effective language prompt and is not reassigned to another reviewer.

```toml
[language_rules]
disabled = [
  "typescript.no-explicit-any",
  "python.runtime-assert",
  "kotlin.shallow-data-class-copy",
]
```

### Built-in language rules

- TypeScript: `typescript.no-explicit-any`, `typescript.unsafe-type-assertion`, `typescript.unsafe-non-null-assertion`, `typescript.non-exhaustive-union`, `typescript.unhandled-promise`
- Python: `python.mutable-default`, `python.bare-exception-handler`, `python.runtime-assert`
- Swift: `swift.unsafe-force-unwrap`, `swift.unsafe-force-cast`, `swift.actor-isolation`, `swift.sendable-boundary`, `swift.unstructured-task-lifetime`, `swift.continuation-resume`
- Java: `java.null-unboxing`, `java.unchecked-cast`, `java.unsafe-optional-get`, `java.equals-hashcode-contract`, `java.autocloseable-lifetime`, `java.unsafe-finally`
- JavaScript: `javascript.unsafe-optional-chaining`, `javascript.loss-of-precision`, `javascript.unsafe-finally`, `javascript.async-promise-executor`, `javascript.async-foreach`, `javascript.unhandled-promise`
- Groovy: `groovy.elvis-falsy-default`, `groovy.unsafe-safe-navigation`, `groovy.gstring-map-key`, `groovy.equality-identity-confusion`, `groovy.regex-find-vs-match`, `groovy.division-semantics`
- Kotlin: `kotlin.unsafe-not-null-assertion`, `kotlin.platform-type-nullability`, `kotlin.array-equality`, `kotlin.shallow-data-class-copy`, `kotlin.swallowed-cancellation`, `kotlin.run-blocking-in-suspend`

Consumers can disable these rules but cannot redefine their instructions, severity guidance, output schema, or safety constraints.

## Customize triggers and diff handling

The `[triggers]` table controls when the documentation, CI, and project-checklist reviewers run. `[large_diff]` classifies generated, low-risk, and high-risk paths. Use repository-relative `/` separators on every operating system.

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

The cache directory must remain inside the repository and be ignored by Git. Do not restore it from an untrusted CI artifact or share it between users, jobs, or forks.

## Add a language or domain reviewer

Add one Markdown file per reviewer under `.deep-review/agents/`. The frontmatter declares deterministic path matching and output behavior; the body contains the trusted reviewer instructions.

Consumer extension filenames, `name` values, and `domain` values should use the reserved `x-` namespace. Use `x-<owner>-<purpose>` so a future built-in reviewer cannot collide with the customization. The filename, `name`, and `domain` must each be unique across extension files; two files cannot share a `name` even when their domains differ.

For example, add `.deep-review/agents/x-example-cobol.md`:

```yaml
---
name: x-example-cobol
description: Review COBOL data layout and project-specific conventions.
domain: x-example-cobol-data-layout
applies_to:
  - "**/*.cbl"
  - "**/*.cob"
  - "**/*.ccp"
  - "**/*.cpy"
prompt_scope: matched
output_schema: hml
blocking:
  - HIGH
  - MEDIUM
references:
  - "docs/cobol-guidelines.md"
---

Review COBOL changes for concrete data-layout, numeric representation,
copybook compatibility, and arithmetic-semantic defects. Apply the project
rules in `docs/cobol-guidelines.md` and follow the shared Deep Review contract.
```

Every reference must exist at the trusted revision. Names use lowercase letters, digits, and hyphens. `prompt_scope` is `full` or `matched`; `output_schema` is `hml` or `checklist`. Extension `blocking` values follow the selected schema.

Built-in ownership takes precedence when subjects overlap. Duplicate extension names or domains, identities equal to built-in names or language-rule namespaces, attempts to replace shared rules, missing references, or unsafe paths make the review incomplete.

### Temporary compatibility reviewers

When an extension temporarily fills a missing built-in language, use a purpose-specific name such as `x-example-cobol-compat`. If built-in COBOL support arrives later, the reserved name remains intact, but audit the extension: remove it or narrow it to organization-specific rules to prevent duplicate findings. Deep Review does not currently support a `fallback_for` field.

## Project checklist

Add trusted repository requirements to `.deep-review/checklist.md`. Use `triggers.project_checklist` to limit the paths that activate it; an absent or empty array matches every non-generated changed path.

## Validate changes

In this repository, run:

```bash
python3 -m unittest discover -s tests -v
```

In a consuming repository, commit configuration before relying on it to control a review. An uncommitted change to `.deep-review/config.toml`, the checklist, or an extension is intentionally unable to govern the same local invocation.
