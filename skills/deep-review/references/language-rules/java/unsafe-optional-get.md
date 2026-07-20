---
rule_id: java.unsafe-optional-get
---

Flag `Optional.get()` only when the `Optional` can be empty on a reachable path and the resulting `NoSuchElementException` is not the intended method contract. Inspect how the value is created, filtered, returned, and guarded; a `get()` call alone is insufficient evidence. Do not flag a dominating presence check, a construction invariant that proves presence, or a deliberately documented fail-fast boundary.

Use HIGH when empty access can terminate a critical public operation, MEDIUM for another reachable unintended exception, and LOW for a confined fragile presence assumption. Recommend `map`, `flatMap`, `ifPresent`, `orElse`, or `orElseGet` when absence is normal, or `orElseThrow` with an appropriate domain exception when failure is the explicit contract; do not recommend a mechanical no-argument `orElseThrow()` replacement.

Public reference: Java SE API, `Optional.get()` and presence-aware alternatives (https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html).
