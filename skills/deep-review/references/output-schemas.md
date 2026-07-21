# Output schemas

## H/M/L

Finding lines contain five pipe-separated fields:

```text
<HIGH|MEDIUM|LOW> | <category> | <file>:<line> | <problem and evidence> | <recommended fix>
```

Escape a literal pipe inside a field as `\|`. Require repository-relative file paths and positive line numbers when a line is knowable.

No findings:

```text
findings: none
summary: 0 high / 0 medium / 0 low
```

With findings, emit the lines followed by:

```text
summary: <N> high / <N> medium / <N> low
```

Recount the body. A mismatch is malformed output.

For a built-in language agent, `<category>` must equal one of the exact namespaced rule IDs enabled for that invocation, such as `typescript.no-explicit-any`. Validate against the effective enabled set before aggregation and caching. An unknown, disabled, or cross-language category is malformed even when the five-field syntax and summary counts are otherwise valid.

## Checklist

Emit one line per applicable item:

```text
- [pass|fail|N/A] <item>: <one-line evidence or gap>
```

Then emit:

```text
summary: <N> pass / <N> fail / <N> N/A
```

When failures exist, append exactly one prioritized, consecutively numbered, repository-relative `file:line` action per failed checklist item, in failed-item order. Otherwise append exactly:

```text
Failures: none.
```

Only `fail` blocks by default. In global `blocking_levels`, checklist `fail` is represented by the canonical token `CHECKLIST_FAIL`; extension frontmatter continues to use its schema-native value `fail`. Recount the body and action list; drift is malformed output.

## Non-result states

The orchestrator, not agents, emits:

```text
SKIPPED: <trigger did not match>
REUSED: unchanged result from iteration <N> (cache key <short-hash>)
UNAVAILABLE: <concise reason>
MALFORMED: <schema violation>
```

`UNAVAILABLE` and `MALFORMED` prevent readiness.

When a logical agent needs multiple bounded prompts, validate each chunk result independently before merging findings under [Prompt budgets and coverage](prompt-budgets.md). A malformed, unavailable, over-budget, or unsynthesized multi-chunk result prevents a complete logical-agent result; never recount only the chunks that happened to return or treat merged findings as cross-chunk semantic synthesis.

## Aggregate decision

Use consumer-configured blocking levels, constrained to known schema values. Defaults:

- H/M/L: HIGH and MEDIUM block; LOW does not.
- checklist: fail blocks.

After the roster, report `prompt-coverage: complete (<valid>/<required> chunks)` or the incomplete form defined in the prompt-budget contract. Return `blocked` when a blocker exists even if another result or required chunk is unavailable; add `warning: review evidence incomplete`. Return `incomplete` only when no known blocker exists. Never convert unavailable evidence into zero findings or complete coverage.
