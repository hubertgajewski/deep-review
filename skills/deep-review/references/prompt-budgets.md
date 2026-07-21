# Prompt budgets and coverage

## Package-owned limits

These safety limits are package-owned invariants:

```text
DEFAULT_DESCRIPTION_MAX_CHARS = 12000
ABSOLUTE_DESCRIPTION_MAX_CHARS = 20000
PROMPT_MAX_UTF8_BYTES = 120000
INLINE_PROMPT_MAX_UTF8_BYTES = 96000
CONTEXT_READ_MAX_UTF8_BYTES = 12000
CONTEXT_READ_TOTAL_MAX_UTF8_BYTES = 24000
MAX_CONTEXT_READS_PER_CHUNK = 2
MAX_MODEL_TURNS_PER_CHUNK_ATTEMPT = 3
MAX_CHUNKS_PER_AGENT = 32
MAX_CHUNKS_PER_REVIEW = 128
MAX_MODEL_CALLS_PER_REVIEW = 256
MAX_TOTAL_PROMPT_UTF8_BYTES = 12000000
MAX_CONCURRENT_CHUNKS = 8
RESULT_MAX_UTF8_BYTES = 12000
AGGREGATE_RESULT_MAX_UTF8_BYTES = 96000
CACHE_RECORD_MAX_UTF8_BYTES = 524288
```

Consumer configuration may reduce the effective description limit but cannot increase or disable the absolute maximum. `description_max_chars = 0` is accepted only as a compatibility request for the package maximum; it never means unlimited. Negative and non-integer values are invalid. A positive configured value above `ABSOLUTE_DESCRIPTION_MAX_CHARS` is clamped to the absolute maximum and reported. `include_description = false` propagates an empty description.

Count description characters as Unicode code points after provider JSON decoding, without line-ending or whitespace normalization. Truncate to the first effective-limit code points before prompt sanitization or construction. Always report exactly one description-state line:

```text
description: full (<original> chars)
description: omitted (<original> chars, effective 0 chars)
description: truncated (<original> chars, effective <effective> chars, limit <limit>)
```

When a positive configured limit exceeds the absolute maximum, also report this independent line before the description-state line:

```text
description-limit: clamped (configured <configured>, absolute <absolute>, effective limit <absolute>)
```

The description-state line then truthfully reports `full`, `omitted`, or `truncated`. Thus a short description with a clamped limit reports `clamped` plus `full`, and `include_description = false` with a clamped limit reports `clamped` plus `omitted`. `description_max_chars = 0` selects the compatibility maximum without a clamping line.

Entity-encode frame tags in the truncated value, then compute `description_hash` over the exact UTF-8 bytes placed inside `<untrusted-change-description>`. An omitted or absent description hashes the exact empty byte string. Never hash the original oversized description as the cache identity.

## Exact prompt budget

`PROMPT_MAX_UTF8_BYTES` applies to the exact model-visible input on every turn, including prior messages and tool results. Reserve `CONTEXT_READ_TOTAL_MAX_UTF8_BYTES` for bounded context reads, so the initially dispatched inline prompt may use at most `INLINE_PROMPT_MAX_UTF8_BYTES`. The inline measurement includes the trusted contract, schema, agent instructions and references, enabled language rules, reviewed-state and chunk metadata, frame tags, complete `CHANGED_FILES`, paths, effective description, focus, and diff payload. Measure the final inline prompt before dispatch and the complete model-visible input again before every later turn. No consumer configuration may change these limits.

Prompt planning is per logical agent because trusted bundles and matched diff scopes differ. First construct the exact no-diff envelope. If that envelope is larger than `INLINE_PROMPT_MAX_UTF8_BYTES`, do not dispatch a reduced or malformed prompt: emit `UNAVAILABLE: fixed prompt framing exceeds the package prompt budget` for that logical agent and make the aggregate `incomplete` unless another validated result already blocks.

Route every model-visible surrounding-context read through an orchestrator-owned bounded transport. One returned read may contain at most `CONTEXT_READ_MAX_UTF8_BYTES`; one logical chunk, across its initial attempt and retry, may make at most `MAX_CONTEXT_READS_PER_CHUNK` reads and receive at most `CONTEXT_READ_TOTAL_MAX_UTF8_BYTES`. An individual attempt uses at most `MAX_MODEL_TURNS_PER_CHUNK_ATTEMPT`: its initial turn plus no more than the remaining permitted follow-up reads. Slice larger files at UTF-8 code-point boundaries and include trusted path and byte-range metadata. Before every subsequent model call, require the exact complete input to remain at or below `PROMPT_MAX_UTF8_BYTES` and debit its full byte length from the cumulative review budget. If the host cannot meter tool results and complete turn input, or the reviewer cannot obtain required evidence within the read, turn, or byte budget, mark that chunk unavailable; never expose an ordinary unbounded file-read tool as a fallback.

Every individual or merged result body is limited to `RESULT_MAX_UTF8_BYTES`, and validated result bodies across the roster are limited to `AGGREGATE_RESULT_MAX_UTF8_BYTES`. A larger or unmetered result is malformed evidence. Result capture, schema validation, recounting, deduplication, and aggregate-size enforcement are deterministic non-model operations; raw result bodies must not be interpolated into another model prompt. Persistent cache reads and writes are limited to `CACHE_RECORD_MAX_UTF8_BYTES`; an oversized record is a cache miss or disables persistence without changing review findings.

## Deterministic chunks

For each logical agent, form one canonical scoped-diff stream in accepted manifest order. Preserve every required normal and high-risk hunk. In effective full-review mode, also preserve every required non-generated hunk that a partial large-diff pass represented as metadata only. Generated content may remain metadata-only under the large-diff contract.

Create the smallest ordered chunk sequence whose complete inline prompts fit `INLINE_PROMPT_MAX_UTF8_BYTES`:

1. Keep complete file blocks together when they fit.
2. Split an oversized file at existing hunk boundaries.
3. Split an oversized hunk at diff-line boundaries.
4. Split a single oversized diff line only at a Unicode-code-point boundary.

Use greedy first-fit in canonical stream order; never reorder content to fill an earlier chunk. Diff payload spans are contiguous, non-overlapping, and gap-free. Transport copies of file or hunk headers used to identify a continuation do not count as covered payload and must be marked `repeated transport context`. Determine chunk count and ordinal width to a fixed point, then measure every final prompt again. A planning inconsistency or over-budget prompt is unavailable evidence, never permission to drop content.

Before any chunk dispatch, validate the complete review plan against every package ceiling: at most `MAX_CHUNKS_PER_AGENT` chunks for one logical agent, `MAX_CHUNKS_PER_REVIEW` chunks across the review, `MAX_MODEL_CALLS_PER_REVIEW` calls including tool-follow-up turns, retries, and any required final guard, `MAX_TOTAL_PROMPT_UTF8_BYTES` across every complete model-visible input, and `MAX_CONCURRENT_CHUNKS` active calls. For each planned chunk, reserve the worst case of two initial attempt turns plus `MAX_CONTEXT_READS_PER_CHUNK` follow-up turns, while also respecting the per-attempt turn ceiling. Charge every reserved turn at the full `PROMPT_MAX_UTF8_BYTES`; this deliberately covers repeated conversation, prior model output, transport metadata, and accumulated context without estimating their smaller actual sizes. Reserve the same worst case for a required final guard. Dispatch through a fixed-size queue rather than creating one worker per chunk. If the plan exceeds any ceiling, dispatch none of its chunks and report required evidence incomplete. Before every model call, atomically debit one call and the exact complete input bytes from the reserved and global budgets. Release unused retry or context-turn reservations only after that chunk finishes. Exhaustion never authorizes partial coverage or starves another already admitted chunk.

Every chunk prompt repeats:

- the complete trusted agent bundle;
- repository identity, immutable base and head identities, and `reviewed_state_hash`;
- the complete `CHANGED_FILES` manifest;
- effective description and reviewer focus;
- bucket and full-review state; and
- `chunk_id`, one-based ordinal, total count, scoped payload byte span, and payload SHA-256.

`chunk_id` is the lowercase SHA-256 of canonical JSON containing the logical agent name, `reviewed_state_hash`, prompt scope (`full` or `matched`), one-based ordinal, total count, payload start/end byte offsets, and exact payload hash. UTF-8 byte offsets refer to the canonical scoped-diff stream. A one-prompt review is still chunk `1/1` and follows the same identity rules.

Chunking is transport, not a new reviewer or ownership boundary. A language agent remains one logical roster dispatch even when several prompt jobs cover its diff. Each chunk follows the same output schema and may inspect safe surrounding context only through the same immutable snapshot.

## Complete coverage and aggregation

Before dispatch, record the ordered required chunk manifest for every matching logical agent. Validate every result independently. Retry only the failed chunk once; after a second failure, report that chunk as unavailable. Never replace a failed chunk with a wider prompt, a sibling chunk, metadata-only coverage, or an agent's inference about unseen content.

Merge valid chunk results in logical-agent and chunk order:

- H/M/L: retain the first occurrence of byte-identical finding lines and recount the merged body.
- checklist: for each item in trusted checklist order, `fail` wins; otherwise `pass` wins over `N/A`; merge the evidence in first-chunk order and rebuild the failure actions and counts.

This merge preserves findings but does not establish cross-chunk semantic coverage: independent chunk results cannot prove relationships between separated hunks, and exact-head context cannot recover deleted base-side evidence. This package version defines no bounded synthesis protocol. Therefore a logical agent with more than one chunk is always semantically incomplete and cannot contribute to `ready`, even when every chunk returned a valid schema. It may still report validated blockers. A future synthesis protocol must have package-owned input, output, call, and context budgets and must produce valid logical-agent evidence before multi-chunk coverage can become complete.

Store or reuse a logical agent result only after every one of its required chunks is schema-valid and dependency-complete and semantic coverage is complete. `scoped_prompt_hash` hashes canonical JSON containing the ordered exact full-prompt hashes and ordered chunk identities; the dependency list is the sorted union from all chunks. Partial or semantically incomplete chunk results are not cached. A cache hit is valid only when the complete recomputed chunk plan, exact effective-description hash, prompt hashes, and dependencies match.

Report coverage after the roster:

```text
prompt-coverage: complete (<valid>/<required> chunks)
```

or:

```text
prompt-coverage: incomplete (<valid>/<required> chunks; <unavailable chunks or multi-chunk synthesis unavailable>)
```

`ready` requires one valid bounded chunk per logical agent, complete prompt coverage, and the existing schema, dependency, large-diff, convergence, and final-guard requirements. Until a bounded synthesis protocol exists, any multi-chunk logical agent makes the result semantically incomplete. A known blocking finding still produces `blocked`, with `warning: review evidence incomplete` when evidence is missing or semantically incomplete. Without a known blocker, any missing, malformed, over-budget, unavailable, or unsynthesized multi-chunk result produces `incomplete`, never `ready`.
