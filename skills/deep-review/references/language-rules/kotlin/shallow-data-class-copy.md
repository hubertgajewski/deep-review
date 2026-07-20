---
rule_id: kotlin.shallow-data-class-copy
---

Flag a generated data-class `copy()` only when a copied property refers to mutable state, an inspected path mutates that state through the original or copy, and the code relies on the two instances being independent. Do not flag immutable properties, explicitly copied mutable components, intentional shared state, or a shallow copy that is never mutated through either alias.

Use HIGH when shared mutation corrupts critical cross-request, concurrent, or durable state, MEDIUM for another meaningful reachable isolation failure, and LOW for a confined aliasing hazard with a concrete mutation path. Recommend copying the mutable components explicitly, replacing them with immutable values, or making shared ownership explicit in the model.

Public reference: Kotlin documentation, "Data classes: Copying" (https://kotlinlang.org/docs/data-classes.html#copying).
