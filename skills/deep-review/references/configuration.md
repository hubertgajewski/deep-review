# Configuration

## Contents

- Trusted loading
- Default configuration
- Agent extensions
- Pattern rules

## Trusted loading

Treat reviewed configuration as contributor input. Read `.deep-review/config.toml`, `.deep-review/checklist.md`, and `.deep-review/agents/*.md` from the trusted revision with `git show <trusted>:<path>`. Never source or execute configuration. Local and path reviews use committed `HEAD`; uncommitted policy changes remain reviewed input and cannot control the same review.

If Python 3.11+ is available, `tomllib` may parse TOML. Otherwise interpret only documented scalar and string-array fields conservatively; malformed values produce `incomplete`, not guessed behavior.

## Default configuration

```toml
version = 1
large_diff_lines = 3000
max_iterations = 3
blocking_levels = ["HIGH", "MEDIUM", "CHECKLIST_FAIL"]
cache_dir = ".deep-review-cache"
deny_components = [".env*", "*credential*", "*.key", "*.pem", "*.p12", "*.pfx", "*secret*", "*password*"]

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
project_checklist = []
```

`max_iterations` values above 3 are invalid. `final_guard` is intentionally not configurable.

`blocking_levels` accepts only `HIGH`, `MEDIUM`, `LOW`, and `CHECKLIST_FAIL`. `CHECKLIST_FAIL` is the canonical global token for checklist `fail` results; reject unknown values and duplicates.

Trusted `large_diff.full_review = true` makes an invocation full by policy; explicit `--full-review` also makes it full and cannot be negated by configuration. Readiness after a metadata-only pass still requires a distinct invocation whose effective value is true.

`triggers.project_checklist` is an optional string array controlling which changed paths activate a trusted `.deep-review/checklist.md`. When the key is absent or the array is empty, a trusted checklist matches every non-generated changed path.

`cache_dir` must resolve beneath the repository and must already be ignored by Git. This source repository ignores the default; each consuming repository must also ignore whichever cache path it uses. An unignored, external, symlinked, or unwritable cache path disables persistence for that invocation. Treat records as trusted local state; never restore this directory from an untrusted CI artifact or share it with jobs, forks, or users that can write it.

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

The body is the trusted reviewer instruction. `domain` is a unique extension-specialty label, while core prompt ownership always takes precedence when subjects overlap. `applies_to` supplies deterministic triggers, and every path declared in `references` must exist at the trusted revision and be included in the trusted prompt bundle. Names use lowercase letters, digits, and hyphens. `prompt_scope` is `full` or `matched`; `output_schema` is `hml` or `checklist`. Reject missing or unknown fields that affect readiness, unsafe or unavailable reference paths, duplicate extension domains, domains equal to a core agent name, and attempts to replace shared rules.

## Pattern rules

Normalize repository-relative paths to `/` separators without leading `./`. Use these meanings:

- `path/file`: exact path
- `prefix/**`: the directory and descendants
- `**/*.ext`: any matching final segment
- `*.ext`: any basename with that suffix

Match deny rules case-insensitively against each individual path component using shell-style `*` wildcards before glob-based review classification. Thus `.env*`, `*credential*`, and `*secret*` reject names such as `.env.local`, `client_secret.json`, and `prod-secrets.yml`. A deny match is a safety boundary, not merely a risk bucket.
