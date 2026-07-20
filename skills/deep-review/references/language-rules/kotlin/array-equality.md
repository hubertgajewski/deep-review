---
rule_id: kotlin.array-equality
---

Flag `==` or `!=` on `Array` or primitive-array values only when surrounding behavior requires comparing their elements rather than their references. Confirm the operand types and equality contract before reporting. Do not flag deliberate identity comparison, null comparison, arrays guaranteed to be the same reference, or a custom wrapper whose `equals` already supplies the required content semantics.

Use HIGH when referential comparison corrupts a critical validation, key, or state decision, MEDIUM for another meaningful reachable equality error, and LOW for a confined fragile assumption. Recommend `contentEquals()` for one-dimensional element equality, `contentDeepEquals()` for nested arrays, or a collection/value type whose equality matches the domain.

Public reference: Kotlin documentation, "Compare arrays" (https://kotlinlang.org/docs/arrays.html#compare-arrays).
