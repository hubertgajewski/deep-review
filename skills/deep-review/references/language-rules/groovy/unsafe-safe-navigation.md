---
rule_id: groovy.unsafe-safe-navigation
---

Flag a value produced by `?.` or `?[]` only when a null receiver is reachable and the resulting `null` subsequently enters an operation, assignment, argument, or dereference that requires a non-null value. Inspect the complete chain and dominating validation before reporting. Do not flag safely propagated nullability, an explicit null check or fallback, an intentionally nullable result, or a skipped safe-navigation assignment with no required side effect.

Use HIGH when the propagated null causes a critical-path failure or false success, MEDIUM for another reachable failure or missing required value, and LOW for a confined fragile assumption. Recommend continuing safe navigation where absence is acceptable, handling it with an explicit fallback or branch, or enforcing the non-null invariant before the value reaches the requiring context.

Public reference: Apache Groovy, "Safe navigation operator" (https://docs.groovy-lang.org/docs/groovy-latest/html/documentation/core-operators.html#_safe_navigation_operator).
