# Prompt budgets and coverage

## Package-owned limits

These safety limits are package-owned invariants:

```text
DEFAULT_DESCRIPTION_MAX_CHARS = 12000
ABSOLUTE_DESCRIPTION_MAX_CHARS = 20000
PROMPT_MAX_UTF8_BYTES = 120000
```

Consumer configuration may reduce the effective description limit but cannot increase or disable the absolute maximum. `description_max_chars = 0` is accepted only as a compatibility request for the package maximum; it never means unlimited. Negative and non-integer values are invalid. A positive configured value above `ABSOLUTE_DESCRIPTION_MAX_CHARS` is clamped to the absolute maximum and reported. `include_description = false` propagates an empty description.

Count description characters as Unicode code points after provider JSON decoding, without line-ending or whitespace normalization. Truncate to the first effective-limit code points before prompt sanitization or construction. Report exactly one of:

```text
description: full (<original> chars)
description: omitted (<original> chars, effective 0 chars)
description: truncated (<original> chars, effective <effective> chars, limit <limit>)
description: limit clamped (configured <configured>, absolute <absolute>); truncated (<original> chars, effective <effective> chars)
```

Entity-encode frame tags in the truncated value, then compute `description_hash` over the exact UTF-8 bytes placed inside `<untrusted-change-description>`. An omitted or absent description hashes the exact empty byte string. Never hash the original oversized description as the cache identity.

## Exact prompt budget

`PROMPT_MAX_UTF8_BYTES` applies to every complete prompt submitted to an agent, including the trusted contract, schema, agent instructions and references, enabled language rules, reviewed-state and chunk metadata, frame tags, complete `CHANGED_FILES`, paths, effective description, focus, and diff payload. Measure the final prompt's exact UTF-8 encoding before dispatch. No consumer configuration may change this limit.

Prompt planning is per logical agent because trusted bundles and matched diff scopes differ. First construct the exact no-diff envelope. If that envelope is larger than the hard limit, do not dispatch a reduced or malformed prompt: emit `UNAVAILABLE: fixed prompt framing exceeds the package prompt budget` for that logical agent and make the aggregate `incomplete` unless another validated result already blocks.

## Deterministic chunks

For each logical agent, form one canonical scoped-diff stream in accepted manifest order. Preserve every required normal and high-risk hunk. In effective full-review mode, also preserve every required non-generated hunk that a partial large-diff pass represented as metadata only. Generated content may remain metadata-only under the large-diff contract.

Create the smallest ordered chunk sequence whose complete prompts fit `PROMPT_MAX_UTF8_BYTES`:

1. Keep complete file blocks together when they fit.
2. Split an oversized file at existing hunk boundaries.
3. Split an oversized hunk at diff-line boundaries.
4. Split a single oversized diff line only at a Unicode-code-point boundary.

Use greedy first-fit in canonical stream order; never reorder content to fill an earlier chunk. Diff payload spans are contiguous, non-overlapping, and gap-free. Transport copies of file or hunk headers used to identify a continuation do not count as covered payload and must be marked `repeated transport context`. Determine chunk count and ordinal width to a fixed point, then measure every final prompt again. A planning inconsistency or over-budget prompt is unavailable evidence, never permission to drop content.

Every chunk prompt repeats:

- the complete trusted agent bundle;
- repository identity, immutable base and head identities, and `reviewed_state_hash`;
- the complete `CHANGED_FILES` manifest;
- effective description and reviewer focus;
- bucket and full-review state; and
- `chunk_id`, one-based ordinal, total count, scoped payload byte span, and payload SHA-256.

`chunk_id` is the lowercase SHA-256 of canonical JSON containing the logical agent name, `reviewed_state_hash`, scoped prompt kind, one-based ordinal, total count, payload start/end byte offsets, and exact payload hash. UTF-8 byte offsets refer to the canonical scoped-diff stream. A one-prompt review is still chunk `1/1` and follows the same identity rules.

Chunking is transport, not a new reviewer or ownership boundary. A language agent remains one logical roster dispatch even when several prompt jobs cover its diff. Each chunk follows the same output schema and may inspect safe surrounding context only through the same immutable snapshot.

## Complete coverage and aggregation

Before dispatch, record the ordered required chunk manifest for every matching logical agent. Validate every result independently. Retry only the failed chunk once; after a second failure, report that chunk as unavailable. Never replace a failed chunk with a wider prompt, a sibling chunk, metadata-only coverage, or an agent's inference about unseen content.

Merge valid chunk results in logical-agent and chunk order:

- H/M/L: retain the first occurrence of byte-identical finding lines and recount the merged body.
- checklist: for each item in trusted checklist order, `fail` wins; otherwise `pass` wins over `N/A`; merge the evidence in first-chunk order and rebuild the failure actions and counts.

Store or reuse a logical agent result only after every one of its required chunks is schema-valid and dependency-complete. `scoped_prompt_hash` hashes canonical JSON containing the ordered exact full-prompt hashes and ordered chunk identities; the dependency list is the sorted union from all chunks. Partial chunk results are not cached. A cache hit is valid only when the complete recomputed chunk plan, exact effective-description hash, prompt hashes, and dependencies match.

Report coverage after the roster:

```text
prompt-coverage: complete (<valid>/<required> chunks)
```

or:

```text
prompt-coverage: incomplete (<valid>/<required> chunks; unavailable <agent>:<ordinal>, ...)
```

`ready` requires complete prompt coverage as well as the existing schema, dependency, large-diff, convergence, and final-guard requirements. A known blocking finding still produces `blocked`, with `warning: review evidence incomplete` when any required chunk is missing. Without a known blocker, any missing, malformed, over-budget, or unavailable required chunk produces `incomplete`, never `ready`.
