---
rule_id: typescript.unsafe-non-null-assertion
---

Flag a postfix non-null assertion only when the value can realistically be `null` or `undefined` on a reachable path and no dominating check or construction invariant excludes that state. Typical sources include optional configuration, collection lookup, and nullable external data, but source shape alone is not proof.

Use HIGH for a demonstrated critical-path absence, MEDIUM for another realistic reachable absence, and LOW only for a confined fragile assumption. Recommend explicit narrowing, a typed required-value loader, a fallback, or a construction invariant represented in the type.

Public references: TypeScript Handbook, "Non-null Assertion Operator" (https://www.typescriptlang.org/docs/handbook/2/everyday-types.html#non-null-assertion-operator-postfix-) and typescript-eslint `no-non-null-assertion` (https://typescript-eslint.io/rules/no-non-null-assertion/).
