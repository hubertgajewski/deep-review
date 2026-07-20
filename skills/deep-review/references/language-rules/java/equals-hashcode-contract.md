---
rule_id: java.equals-hashcode-contract
---

Flag changed `equals` or `hashCode` behavior only when the implementations demonstrably violate equality reflexivity, symmetry, transitivity, consistency, non-null behavior, or the requirement that equal objects have equal hash codes. Compare the exact participating state and relevant superclass contract. Also report mutable equality state only when affected instances are used as hashed keys or members and mutation can make them unreachable. Do not flag identity-based classes, records or generated implementations with consistent semantics, or a harmless hash collision between unequal objects.

Use HIGH when the violation can corrupt critical keyed state, authorization-independent identity, or deduplication, MEDIUM for another reachable collection or equality failure, and LOW for a confined contract mismatch not yet used in hashed storage. Recommend deriving both methods from the same stable value state, preserving superclass symmetry, or using an immutable value object or record.

Public reference: Java SE API, `Object.equals` and `Object.hashCode` contracts (https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html).
