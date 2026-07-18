# Configuration

## Contents

- Trusted loading
- Default configuration
- Agent extensions
- Pattern rules

## Trusted loading

Treat reviewed configuration as contributor input. Read `.deep-review/config.toml`, `.deep-review/checklist.md`, and `.deep-review/agents/*.md` from the trusted revision with `git show <trusted>:<path>`. Never source or execute configuration.

If Python 3.11+ is available, `tomllib` may parse TOML. Otherwise interpret only documented scalar and string-array fields conservatively; malformed values produce `incomplete`, not guessed behavior.

## Default configuration

```toml
version = 1
large_diff_lines = 3000
max_iterations = 3
blocking_levels = ["HIGH", "MEDIUM", "CHECKLIST_FAIL"]
cache_dir = ".deep-review-cache"
deny_components = [".env", "credentials", "*.key", "*.pem", "*.p12", "*.pfx", "secret", "password"]

[remote_review]
provider = "auto"
remote = "origin"
include_description = true
description_max_chars = 0

[large_diff]
full_review = false
generated = ["**/*.generated.*", "**/dist/**", "**/build/**", "**/*.lock"]
low_risk = ["docs/**", "**/*.snap", "**/__snapshots__/**"]
high_risk = ["**/auth/**", "**/security/**", "**/crypto/**", ".github/workflows/**", ".gitlab-ci.yml", "**/*.entitlements", "**/*.plist"]

[triggers]
docs = ["README*", "docs/**", "AGENTS.md", "CLAUDE.md", ".deep-review/**", "skills/**"]
ci = [".github/workflows/**", ".gitlab-ci.yml", ".gitlab/ci/**", "**/action.yml", "**/action.yaml", "scripts/**", "**/*.sh"]
```

`max_iterations` values above 3 are invalid. `final_guard` is intentionally not configurable.

`cache_dir` must resolve beneath the repository and must already be ignored by Git. This source repository ignores the default; each consuming repository must also ignore whichever cache path it uses. An unignored, external, symlinked, or unwritable cache path disables persistence for that invocation.

## Agent extensions

An extension is one Markdown file with this frontmatter:

```yaml
---
name: java
description: Review Java language and JVM API correctness.
domain: java-jvm-correctness
applies_to:
  - "**/*.java"
prompt_scope: matched
output_schema: hml
blocking:
  - HIGH
  - MEDIUM
references:
  - "docs/java-guidelines.md"
---
```

The body is the trusted reviewer instruction. `domain` states its exclusive ownership, `applies_to` supplies deterministic triggers, and `references` lists trusted repository-relative context to read when present. Names use lowercase letters, digits, and hyphens. `prompt_scope` is `full` or `matched`; `output_schema` is `hml` or `checklist`. Reject missing or unknown fields that affect readiness, unsafe reference paths, and attempts to replace shared rules.

## Pattern rules

Normalize repository-relative paths to `/` separators without leading `./`. Use these meanings:

- `path/file`: exact path
- `prefix/**`: the directory and descendants
- `**/*.ext`: any matching final segment
- `*.ext`: any basename with that suffix

Match deny rules by individual path component before glob-based review classification. A deny match is a safety boundary, not merely a risk bucket.
