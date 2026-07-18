# Orchestration

## Contents

- Derived scope
- Dispatch defaults
- Large diffs
- Cache keys and iterations
- Final guard

## Derived scope

Parse the normalized diff once into an ordered map of path to complete unified-diff block. Derive:

- `CHANGED_PATHS`: diff metadata plus untracked paths
- `NEW_PATHS`: new-file markers plus untracked paths
- `ADDED_LINES_BY_PATH`: hunk additions excluding `+++`
- `CHANGED_LINE_COUNT`: hunk additions and deletions excluding file headers
- `CHANGED_FILES`: status and destination path, with rename/copy source

Every dispatched agent receives `CHANGED_FILES`, even when its inline matched diff is empty.

## Dispatch defaults

- code, architecture, simplification: always
- security: dispatch for executable/source/config/dependency/CI paths, sensitive path components, credential-shaped added assignments, or untracked content not clearly docs/generated/test-only
- docs: dispatch for new paths, documentation, assistant/skill policy, configuration examples, CI files, or newly introduced environment/configuration names
- CI: dispatch for `.github/workflows/**`, `.gitlab-ci.yml`, `.gitlab/ci/**`, action metadata, shell files, or automation scripts
- project-checklist: dispatch only when a trusted checklist exists and its trusted patterns match; when patterns are absent, match every non-generated changed path

Consumer agent `applies_to` patterns are deterministic path triggers. New matching agents run even if they were skipped in the previous iteration.

## Large diffs

Apply trusted high-risk patterns first, then generated, then low-risk, then normal. Denied components are rejected before bucketing. Each path belongs to one bucket.

Metadata-only placeholders include path, status, bucket, and omitted changed-line count. `--full-review` disables metadata-only treatment for every required non-generated path. Generated paths may remain metadata-only unless trusted configuration marks them required.

A metadata-only required path makes coverage partial and cannot produce `ready`. Require a separate explicit `--full-review` invocation before readiness; do not promote the partial pass automatically.

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

Persist one latest record per agent. A record stores the key, classification (`nonblocking`, `blocking`, or `incomplete`), iteration, result body, summary counts, and timestamp. It never stores raw scope input separately.

The record also stores the validated canonical key manifest, including its sorted dependency identities. On a later invocation, use `cache.py probe` to obtain only a structurally and schema-validated prior manifest, re-hash its dependency paths at the current reviewed state, construct the complete candidate key, and use `cache.py lookup` for an exact match. Treat exit code 3 as a miss. Treat corrupt, unreadable, or unwritable cache as unavailable and run required agents fresh; keep the current invocation's iteration state in memory.

Persist scope state with scope identity, reviewed-state hash, iteration, last aggregate status, and whether reuse or targeted reruns occurred. Rules:

- new scope: iteration 1
- identical reviewed-state hash: keep iteration
- changed reviewed-state hash: increment once
- refuse to advance above 3

Blocking output is not reusable after a state change. It may be re-emitted for an identical state to avoid a no-value model call.

## Final guard

Require the guard when any current convergence sequence used a reused result or ran only targeted agents. Rebuild triggers and prompt frames, disable reuse, and run all currently matching agents. Ensure required large-diff coverage is full. Fresh guard output supersedes prior cached output.

The guard does not advance iteration. If it blocks, persist `blocked` and wait for a changed reviewed state. Never loop a guard automatically.
