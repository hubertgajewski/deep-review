---
rule_id: kotlin.platform-type-nullability
---

Flag a Java platform value only when inspected Java declarations, annotations, implementations, generic mutation, or reachable callers show that null can arrive and Kotlin directly dereferences, assigns, passes, or propagates it as non-null without validation. Do not infer risk solely from the platform-type marker. Do not flag a defect whose failure site is `!!`; `kotlin.unsafe-not-null-assertion` takes precedence for that same defect. Exclude values covered by reliable nullability annotations, explicit nullable Kotlin types and checks, or proven non-null construction.

Use HIGH for a demonstrated critical-path null failure or corrupted non-null collection, MEDIUM for another meaningful reachable boundary failure, and LOW for a confined fragile interoperation contract. Recommend adding accurate Java nullability annotations where the declaration is owned, or introducing an explicit nullable Kotlin boundary and validating it before non-null use.

Public reference: Kotlin documentation, "Null-safety and platform types" (https://kotlinlang.org/docs/java-interop.html#null-safety-and-platform-types).
