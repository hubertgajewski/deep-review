---
rule_id: java.unchecked-cast
---

Flag an unchecked narrowing or raw-to-parameterized conversion only when the runtime cannot validate the complete asserted type and an incompatible value can enter or escape the boundary, causing heap pollution or delayed failure. Trace producers and consumers rather than treating the compiler warning or `@SuppressWarnings` token as proof. Do not flag a checked narrowing cast, a validated element-by-element conversion, or an isolated legacy boundary whose invariant is established and contained.

Use HIGH when incompatible data can cross a critical public boundary or corrupt shared typed state, MEDIUM for another reachable heap-pollution or delayed-cast failure, and LOW for confined type debt with a credible incompatible producer. Recommend a generic or wildcard contract, a runtime type token plus validation, a defensive typed copy, or a narrowly isolated adapter that proves and documents the invariant.

Public reference: Java Language Specification, "Checked and Unchecked Narrowing Reference Conversions" (https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.6.2).
