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

Only `fail` blocks by default. In global `blocking_levels`, checklist `fail` is
represented by the canonical token `CHECKLIST_FAIL`; all agent frontmatter continues
to use its schema-native value `fail`. Normalize and combine policies before dispatch
according to the configuration contract, then classify the validated counts with that
same effective policy. Recount the body and action list; drift is malformed output.

## Non-result states

The orchestrator, not agents, emits:

```text
SKIPPED: <trigger did not match>
REUSED: unchanged result from iteration <N> (cache key <short-hash>)
UNAVAILABLE: <concise reason>
MALFORMED: <schema violation>
```

`UNAVAILABLE` and `MALFORMED` prevent readiness.

## Aggregate decision

Use the normalized effective per-agent policy from the configuration contract. Defaults:

- H/M/L: HIGH and MEDIUM block; LOW does not.
- checklist: fail blocks.

Return `blocked` when a blocker exists even if another result is unavailable; add `warning: review evidence incomplete`. Return `incomplete` only when no known blocker exists. Never convert unavailable evidence into zero findings.

For a valid complete H/M/L result, classification is `blocking` exactly when at least
one count selected by that agent's effective H/M/L policy is nonzero. For a valid
complete checklist result, it is `blocking` exactly when effective policy contains
`fail` and the fail count is nonzero. Otherwise it is `nonblocking`. Missing evidence,
malformed output, or incomplete dependency identity is `incomplete`, never
`nonblocking`, unless the validated result already contains a configured blocker; as
with aggregate status, a known blocker takes precedence and the evidence gap remains a
warning.
