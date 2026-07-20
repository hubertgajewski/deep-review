---
rule_id: kotlin.unsafe-not-null-assertion
---

Flag `!!` only when the asserted value can realistically be null on a reachable path and no dominating validation or construction invariant excludes that state. Trace nullable assignments, safe casts, collection lookups, external values, and platform boundaries before reporting. When the same defect originates from a Java platform value, own it under this rule and do not duplicate it as `kotlin.platform-type-nullability`. Do not flag an assertion whose non-null invariant is established by inspected control flow or a contract unavailable to the type system.

Use HIGH for a demonstrated critical-path null failure, MEDIUM for another meaningful reachable exception, and LOW for a confined fragile invariant. Recommend preserving nullable flow with safe calls or Elvis handling, or enforcing the invariant once with a meaningful `requireNotNull`, `checkNotNull`, or domain-specific boundary failure.

Public reference: Kotlin documentation, "Null safety" and the not-null assertion operator (https://kotlinlang.org/docs/null-safety.html#not-null-assertion-operator).
