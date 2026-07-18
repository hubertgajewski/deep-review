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

## Checklist

Emit one line per applicable item:

```text
- [pass|fail|N/A] <item>: <one-line evidence or gap>
```

Then emit:

```text
summary: <N> pass / <N> fail / <N> N/A
```

When failures exist, append a prioritized numbered list of actionable `file:line` failures. Otherwise append exactly:

```text
Failures: none.
```

Only `fail` blocks by default. Recount the body; drift is malformed output.

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

Use consumer-configured blocking levels, constrained to known schema values. Defaults:

- H/M/L: HIGH and MEDIUM block; LOW does not.
- checklist: fail blocks.

Return `blocked` when a blocker exists even if another result is unavailable; add `warning: review evidence incomplete`. Return `incomplete` only when no known blocker exists. Never convert unavailable evidence into zero findings.
