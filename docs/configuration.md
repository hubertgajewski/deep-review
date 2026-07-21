# Configuration

Deep Review uses reviewed repository configuration rather than uncommitted policy changes. The normative behavior is defined in [`skills/deep-review/references/configuration.md`](../skills/deep-review/references/configuration.md); this guide focuses on common user tasks.

## Configuration file

Create `.deep-review/config.toml` in the repository being reviewed. Start with only the settings you need to change. The complete default is documented in the [runtime configuration contract](../skills/deep-review/references/configuration.md#default-configuration).

```toml
version = 1
large_diff_lines = 3000
blocking_levels = ["HIGH", "MEDIUM", "CHECKLIST_FAIL"]
cache_dir = ".deep-review-cache"

[remote_review]
provider = "auto"
remote = "origin"
include_description = true
description_max_chars = 12000

[language_agents]
disabled = []

[language_rules]
disabled = []
```

Configuration is loaded from the trusted committed revision. For local and path reviews, that revision is `HEAD`; an uncommitted policy edit is reviewed as input but cannot control the same review. Malformed, duplicate, or unknown values make the result `incomplete` rather than being guessed or ignored.

## Bound descriptions and reviewer prompts

Remote change descriptions default to at most 12,000 Unicode characters. You may choose another limit up to the package's 20,000-character absolute maximum; larger values are clamped. Legacy `description_max_chars = 0` requests that maximum rather than unlimited propagation. Set `include_description = false` to omit descriptions.

Deep Review reports original and effective description character counts whenever it omits or truncates a description. When a configured limit exceeds the absolute maximum, a separate clamp diagnostic is emitted before the full, omitted, or truncated state, so short and intentionally omitted descriptions remain truthful. Its cache identity uses the exact effective text sent to reviewers, not the oversized original.

Every complete reviewer model turn is limited to 120,000 UTF-8 bytes. Initial inline prompts use at most 96,000 bytes, leaving a metered 24,000-byte reserve for safe context reads. Package-owned ceilings also bound chunks per agent and review, total prompt bytes and model calls, concurrency, result bodies, and persistent cache records. Plans over a ceiling fail closed before dispatch.

When required normal, high-risk, or full-review hunks do not fit one inline prompt, Deep Review deterministically splits them into bounded chunks while repeating the complete changed-file manifest and immutable review identity. Independent chunks can surface blockers but cannot prove relationships across separated hunks. Until a bounded synthesis protocol is defined, a multi-chunk logical reviewer is reported `incomplete` and cannot produce `ready`; a single bounded chunk retains the normal readiness path.

## Iteration limit

The convergence limit is fixed at three changed review iterations. Omit
`max_iterations`, as above, or set it to the TOML integer `3`. Any other value makes the
configuration `incomplete`. The final guard is separate and does not count as a fourth
iteration.

## Blocking levels

`blocking_levels` controls which global finding severities block readiness. It accepts `HIGH`, `MEDIUM`, `LOW`, and `CHECKLIST_FAIL` without duplicates:

```toml
blocking_levels = ["HIGH", "CHECKLIST_FAIL"]
```

This changes aggregation, not reviewer instructions or severity guidance. A consumer cannot disable the final guard or change the fixed three-iteration limit.

Deep Review normalizes the global list into each reviewer's output schema. For built-in
reviewers, the normalized global list is the effective policy; built-in frontmatter
records the package default (`HIGH` and `MEDIUM` for H/M/L, `fail` for checklist).
For an extension, the effective policy is the intersection of its schema-native
`blocking` list and the normalized global list. Checklist frontmatter uses `fail`, while
the equivalent global token is `CHECKLIST_FAIL`.

For an extension declaring `blocking: [HIGH, MEDIUM]`, the results are concrete:

| Global `blocking_levels` | Effective extension policy |
| --- | --- |
| `["HIGH", "MEDIUM", "CHECKLIST_FAIL"]` (default) | `HIGH`, `MEDIUM` |
| `["HIGH", "MEDIUM", "LOW", "CHECKLIST_FAIL"]` (stricter) | `HIGH`, `MEDIUM` |
| `["HIGH", "CHECKLIST_FAIL"]` (looser) | `HIGH` |

The stricter global example makes `LOW` blocking for built-in H/M/L reviewers, but not
for this extension because it did not declare `LOW`. A checklist extension declaring
`blocking: [fail]` blocks when global policy contains `CHECKLIST_FAIL` and becomes
advisory when that token is absent. An explicit extension `blocking: []` is also
advisory; a missing or null declaration is invalid.

Unknown values, duplicates, values from the wrong schema, global/native token mixing,
and contradictory built-in declarations make review policy loading `incomplete` before
dispatch. The effective per-agent policy is included in cache identity and is used to
classify both fresh and cached results.

## Deny credential-bearing paths

`deny_components` is a safety boundary applied case-insensitively to each path component. Its defaults reject `.env*`, `*credential*`, `*.key`, `*.pem`, `*.p12`, `*.pfx`, `*secret*`, and `*password*`. You may replace the list in trusted committed configuration when a repository needs different path policy.

Deep Review first enumerates the complete raw changed-endpoint manifest without patch bodies, including untracked paths and any exact-identity relationship source it reports. It validates the whole manifest before retrieving diff hunks, reading working-tree files, creating a snapshot, or hashing dependencies. Repository paths must decode as strict UTF-8; an undecodable byte sequence fails scope resolution instead of being normalized lossily. One denied path fails the entire scope; an allowed/denied mixed change is never reduced to only its allowed files. The same checks run before reading unchanged surrounding context, extension references, or dependency content, so an unchanged credential-bearing file cannot enter a prompt or hash indirectly.

Mutable tracked and untracked files and snapshot context are opened through a platform secure-open adapter anchored to the relevant repository or snapshot root. The adapter must reject symlink and Windows reparse-point traversal, preserve the preflight file identity, and prove containment. POSIX descriptor-relative and Windows handle-relative implementations are both valid when they establish those guarantees; a client that cannot establish them fails or marks required context incomplete instead of silently weakening the boundary. In local mode, staged bodies come from retained index object identities, unstaged bodies come only from secure capture, and Deep Review constructs tracked hunks internally from raw snapshot bytes rather than asking Git to diff the caller's mutable working tree.

Git's initial diff pass emits only raw full-object-ID/mode/path records with rename detection, submodule suppression, external diff, and text conversion disabled; rename similarity can read blobs even in a name-only command. Deep Review therefore uses body-free object identities and compatible Git mode classes to add any unchanged exact-copy source before preflight. It reports only exact-identity renames or copies; modified renames remain delete/add pairs, non-exact copies remain additions, and gitlinks are represented from object metadata without reading or traversing submodules. It builds bounded hunks from accepted raw blobs or securely captured bytes with its own binary detection, and builds snapshot roots without checkout or clean/smudge filters, so contributor-controlled attributes cannot execute or replace review evidence. Local mode never asks Git to compare mutable worktree content: it rejects unmerged index entries, derives conservative candidates from index and no-follow filesystem metadata, securely captures accepted candidates, reconstructs tracked state, and appends each untracked file as an independent synthetic addition.

The non-configurable safety ceilings are 10,000 candidate paths, 200,000 logical-tree entries, 64 MiB of retained metadata and diff working state, 16 MiB per changed body, 128 MiB across changed bodies, 20,000,000 diff operations, 64 MiB of normalized diff output, 16 MiB per projected context file, and 512 MiB of projected context. Remote metadata transport additionally allows 64 MiB compressed input, 256 MiB expanded commit/tree data, and 320 MiB of isolated-store disk use. Remote mode uses an isolated blobless metadata fetch and disables lazy object fetching; only preflight-approved blobs are streamed by exact object ID under the body limits. Exceeding a required changed-evidence or remote-transport ceiling fails the atomic scope before prompt construction or caching; exceeding a surrounding-context projection ceiling makes the required review evidence incomplete rather than silently claiming full coverage.

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

Every reference must exist at the trusted revision. Names use lowercase letters, digits, and hyphens. `prompt_scope` is `full` or `matched`; `output_schema` is `hml` or `checklist`. Extension `blocking` values follow the selected schema and intersect with the normalized global policy described above.

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
