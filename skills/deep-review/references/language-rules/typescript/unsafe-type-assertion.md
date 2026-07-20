---
rule_id: typescript.unsafe-type-assertion
---

Flag `as T` or angle-bracket assertions only when the asserted runtime value is not established by construction, validation, or prior narrowing and the assertion makes an incompatible operation type-check. Trace the source and consumer. Do not reject assertions that only preserve a proven invariant or bridge an API whose runtime contract is inspected.

Use HIGH only when an unchecked external or critical-boundary value is demonstrated to reach an incompatible operation. Use MEDIUM for another reachable unchecked boundary and LOW for confined type debt. Recommend validation, a type predicate, discriminant narrowing, or a contract that returns the proven type.

Public reference: TypeScript Handbook, "Narrowing" (https://www.typescriptlang.org/docs/handbook/2/narrowing.html).
