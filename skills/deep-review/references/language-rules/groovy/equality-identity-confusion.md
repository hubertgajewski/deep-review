---
rule_id: groovy.equality-identity-confusion
---

Flag `==` or `!=` only when the surrounding algorithm demonstrably requires reference identity, or flag `is`, `===`, or their negations only when distinct but equal values must compare alike. Inspect collection semantics, mutation, ownership, and callers before deciding which relation is required. Do not flag a comparison merely because it differs from Java syntax or when value and identity equality are equivalent for all reachable operands.

Use HIGH when the wrong relation corrupts a critical ownership, deduplication, or state transition, MEDIUM for another meaningful reachable branch error, and LOW for a confined fragile assumption. Recommend `==` or `!=` for value equality and `is()` for broadly compatible identity checks; recommend `===` or `!==` only when the repository's Groovy baseline supports Groovy 3 or later.

Public reference: Apache Groovy, "Identity operator" (https://docs.groovy-lang.org/docs/groovy-latest/html/documentation/core-operators.html#_identity_operator).
