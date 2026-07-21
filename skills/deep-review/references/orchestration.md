# Orchestration

## Contents

- Derived scope
- Dispatch defaults
- Large diffs
- Prompt chunks and coverage
- Cache keys and iterations
- Final guard

## Derived scope

Begin only with the complete accepted manifest produced by scope-resolution path preflight. Parse the normalized content diff once into an ordered map of accepted path to complete unified-diff block and cross-check it without expanding the manifest. Derive:

- `CHANGED_PATHS`: diff metadata plus untracked paths
- `NEW_PATHS`: new-file markers plus untracked paths
- `ADDED_LINES_BY_PATH`: hunk additions excluding `+++`
- `CHANGED_LINE_COUNT`: hunk additions and deletions excluding file headers
- `CHANGED_FILES`: status and destination path, with rename/copy source

Every dispatched agent receives `CHANGED_FILES`, even when its inline matched diff is empty. No trigger, snapshot, prompt, bucket, or dependency hash may be built from a path that did not pass preflight.

## Dispatch defaults

- code, architecture, simplification: always
- security: dispatch for executable/source/config/dependency/CI paths, sensitive path components, credential-shaped added assignments, or untracked content not clearly docs/generated/test-only
- docs: dispatch for new paths, documentation, assistant/skill policy, configuration examples, CI files, or newly introduced environment/configuration names
- CI: dispatch for `.github/workflows/**`, `.gitlab-ci.yml`, `.gitlab/ci/**`, action metadata, shell files, automation scripts, exact root `Jenkinsfile`, or `**/*.groovy`
- project-checklist: dispatch only when a trusted checklist exists and its trusted patterns match; when patterns are absent, match every non-generated changed path
- typescript: dispatch once for `**/*.ts`, `**/*.tsx`, `**/*.mts`, or `**/*.cts` when the agent and at least one rule are enabled
- python: dispatch once for `**/*.py` or `**/*.pyi` when the agent and at least one rule are enabled
- swift: dispatch once for `**/*.swift` or exact `Package.swift` when the agent and at least one rule are enabled
- java: dispatch once for `**/*.java` when the agent and at least one rule are enabled
- javascript: dispatch once for `**/*.js`, `**/*.jsx`, `**/*.mjs`, or `**/*.cjs` when the agent and at least one rule are enabled
- groovy: dispatch once for `**/*.groovy`, `**/*.gradle`, or exact root `Jenkinsfile` when the agent and at least one rule are enabled
- kotlin: dispatch once for `**/*.kt` or `**/*.kts` when the agent and at least one rule are enabled

Treat `build.gradle` as Groovy and `build.gradle.kts` as Kotlin; the latter matches `**/*.kts`, not `**/*.gradle`. Gradle DSL and build-logic correctness remain code-review ownership, while Groovy and Kotlin own only their enabled language-semantic rules.

Any changed `**/*.groovy` path dispatches both the Groovy language agent and the CI agent. This conservative overlap covers Jenkins Shared Library sources without treating a Groovy suffix as finding evidence: CI must demonstrate Jenkins Pipeline or Shared Library execution context and ignore ordinary Groovy application code. A changed root `Jenkinsfile` therefore dispatches both agents as well. Groovy owns only its enabled language-semantic rules there; Jenkins pipeline trust, credentials, execution policy, and other CI concerns remain CI ownership. Repository-specific Pipeline Script Paths and non-Groovy Shared Library resources cannot be inferred from a standard suffix and must be listed in trusted `triggers.ci`.

Consumer agent `applies_to` patterns are deterministic path triggers. New matching agents run even if they were skipped in the previous iteration.

A built-in language row with no matching path emits `SKIPPED: language trigger did not match` and contributes zero findings to readiness.

Validate `language_agents.disabled` and `language_rules.disabled` against the package-owned catalogs before evaluating language dispatch. Assemble a matching language prompt from the shared contract, H/M/L schema, base language prompt, and only the enabled rule fragments in declared order. Include the ordered enabled rule IDs as trusted prompt metadata. Never include a disabled fragment or dispatch one subagent per rule.

For fresh language output, apply the normal H/M/L validator plus the effective rule set. When `cache.py validate-result` is available, pass each enabled ID as a repeated `--allowed-category` argument; otherwise perform the equivalent exact-membership check before aggregation or caching.

## Large diffs

Apply trusted high-risk patterns first, then generated, then low-risk, then normal. Denied components are rejected during metadata-only path preflight, before content diff retrieval and therefore before bucketing. Each path belongs to one bucket.

Metadata-only placeholders include path, status, bucket, and omitted changed-line count. Effective `full_review = true`, whether set by trusted policy or explicit `--full-review`, disables metadata-only treatment for every required non-generated path. Generated paths may remain metadata-only unless trusted configuration marks them required.

A metadata-only required path makes coverage partial and cannot produce `ready`. Require a distinct later invocation whose effective `full_review` value is true; do not promote the partial pass automatically.

Large-diff bucketing decides which content is required; it never permits an oversized required hunk to be omitted. Normal and high-risk content remains required in both partial and full modes. Effective full-review mode makes every required non-generated hunk part of the bounded prompt plan.

## Prompt chunks and coverage

Follow [Prompt budgets and coverage](prompt-budgets.md) after bucketing and per-agent scope matching. The hard 120,000-byte UTF-8 limit applies to the complete final prompt, not only the inline diff. Build an ordered per-agent chunk manifest with exact payload spans and hashes, then measure every prompt again after the final ordinal and total are known.

One huge file is split at hunk, line, and finally Unicode-code-point boundaries without gaps. Several huge files retain accepted manifest and per-file block order. Full-review mode uses the same chunker rather than requiring all content in one invocation. Every chunk repeats trusted framing, complete `CHANGED_FILES`, and immutable reviewed-state identity.

Treat chunks as required evidence belonging to one logical roster agent. Validate each output, merge valid results by the schema-specific rules, and report global valid/required chunk counts. Missing or unavailable chunk evidence produces `incomplete` unless another valid chunk has a configured blocker, in which case the aggregate remains `blocked` with an incomplete-evidence warning. Only complete logical-agent results are eligible for caching or readiness.

## Cache keys and iterations

Construct one canonical JSON key manifest per agent with:

```text
schema_version
agent
provider
host
repository
change_number
base_identity
head_identity
mode
scope_hash
description_hash
orchestrator_hash
agent_prompt_hash
config_hash
checklist_hash
references_hash
scoped_prompt_hash
dependencies_complete
dependencies: sorted path and content-hash pairs
```

Use empty strings for non-applicable remote fields. Never omit required names. Compute SHA-256 over canonical UTF-8 JSON.

For a language agent, `agent_prompt_hash` covers the exact effective base prompt plus enabled rule fragments in canonical declared order. The existing `config_hash` covers the complete trusted configuration. A configuration change or enabled-fragment change therefore invalidates reuse without another key-manifest field.

`description_hash` is the hash of the exact effective, frame-tag-encoded description bytes propagated to every chunk, including the exact empty value when omitted. `scoped_prompt_hash` is the SHA-256 of canonical JSON containing the ordered hashes of every exact complete chunk prompt and the ordered chunk identities. It therefore commits the cache record to description propagation, one huge file or several huge files, deterministic chunk order, complete-manifest framing, effective full-review coverage, and every package prompt-budget constant.

Build the convergence `scope_key` only from stable request identity:

- every mode: repository identity, mode, and reviewer-focus hash;
- remote: provider, host, and change number;
- path: canonical repository-relative path selector;
- base/range: normalized validated selectors and range operator;
- local: no additional selector.

Exclude base/head revisions, diff and description hashes, untracked identities, bucket coverage, and effective full-review state from `scope_key`; include all changing reviewed content in `reviewed_state_hash`. The reviewed-state hash includes the exact effective description hash, accepted diff and untracked identities, and bucket/full-review coverage. The derived chunk plan is excluded to avoid a cycle because every `chunk_id` already commits to `reviewed_state_hash`; ordered chunk identities instead belong to `scoped_prompt_hash`. This keeps one fix/review sequence stable while its reviewed state changes.

Persist one latest complete logical-agent record per agent. A record stores the key, classification (`nonblocking`, `blocking`, or `incomplete`), iteration, merged result body, summary counts, and timestamp. It never stores raw scope input, individual chunk prompts, or partial chunk results separately.

The record also stores the validated canonical key manifest, including its sorted dependency identities. On a later invocation, use `cache.py probe` to obtain only a structurally and schema-validated prior manifest, re-hash its dependency paths from the immutable reviewed-head context rather than the caller's checkout, construct the complete candidate key, and use `cache.py lookup` for an exact match. Treat exit code 3 as a miss. Treat corrupt, unreadable, or unwritable cache as unavailable and run required agents fresh; keep the current invocation's iteration state in memory.

Persist at most 64 records keyed by scope identity, with reviewed-state hash, iteration, generation, last aggregate status, and whether reuse or targeted reruns occurred. `cache.py` serializes each read-modify-write transition under a cross-platform lock. When capacity is reached, evict the least-recently-updated completed record: either `ready` or terminal iteration-3 `blocked`/`incomplete`. Never evict an active iteration-1 or iteration-2 `blocked`/`incomplete` state. If no completed record is evictable, disable persistence for the new scope and keep its state in memory. Pass `--scope-key` to `state-read` when more than one record exists. Rules:

- new scope: iteration 1
- identical reviewed-state hash: keep iteration
- changed reviewed-state hash: increment once
- changed reviewed-state hash after `ready`: start a new sequence at iteration 1
- an iteration-3 `blocked` or `incomplete` result ends the current sequence; stop and return control to the caller
- a later explicit invocation with a changed reviewed-state hash after an iteration-3 result passes `state --start-new-sequence --expected-generation <observed>` and starts at iteration 1
- reject a changed iteration-3 state without `--start-new-sequence`; reject the flag unless the prior state is terminal iteration 3 and the reviewed-state hash changed
- an identical reviewed-state hash at iteration 3 keeps iteration 3 and may re-emit validated cached blockers without another model call
- reuse and targeted-rerun flags accumulate monotonically for the sequence
- every state write advances a per-scope generation
- every update to an existing scope requires `--expected-generation <observed>`
- only `state --final-guard-run --expected-generation <observed>` with the same reviewed-state hash clears guard flags
- a generation mismatch invalidates the completed review result and requires a rebuilt scope; a guard hash mismatch requires a rebuilt fresh guard

Blocking output is not reusable after a state change. It may be re-emitted for an identical state to avoid a no-value model call.
Starting a new sequence resets only its iteration and guard-history flags. It does not clear agent-result records; independently eligible nonblocking results remain available under the normal complete-key checks.

## Final guard

Require the guard when any current convergence sequence used a reused result or ran only targeted agents. Rebuild triggers, chunk plans, and prompt frames, disable reuse, and run every required chunk for all currently matching agents. Ensure required large-diff and prompt-chunk coverage are both complete. Fresh guard output supersedes prior cached output.

The guard does not advance iteration. If it blocks, persist `blocked` and wait for a changed reviewed state. Never loop a guard automatically.
