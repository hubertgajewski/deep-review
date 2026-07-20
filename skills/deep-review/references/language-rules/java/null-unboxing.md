---
rule_id: java.null-unboxing
---

Flag an implicit or explicit unboxing conversion only when the boxed value can realistically be `null` on a reachable path. Inspect assignments, collection lookups, method contracts, branches, and dominating checks before reporting. Do not flag a primitive value, a boxed value proven non-null by construction or validation, or a merely nullable declaration whose actual path cannot reach the conversion.

Use HIGH when null unboxing can crash a critical public operation, MEDIUM for another reachable `NullPointerException` with meaningful impact, and LOW for a confined fragile assumption. Recommend preserving a primitive type where absence is impossible, or explicitly handling, rejecting, or defaulting the nullable value before arithmetic, comparison, switching, argument conversion, or assignment triggers unboxing.

Public reference: Java Language Specification, "Unboxing Conversion" (https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.8).
