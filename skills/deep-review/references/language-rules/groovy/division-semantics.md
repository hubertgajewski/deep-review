---
rule_id: groovy.division-semantics
---

Flag `/` only when inspected consumers require integral division or a specific decimal precision and Groovy's division result creates a reachable incorrect value, conversion, type, or boundary. Establish the operand types and required rounding or truncation contract before reporting. Do not flag intentional decimal division, an explicit rounding step, `intdiv()`, or a result whose representation cannot affect reachable behavior.

Use HIGH when the result corrupts critical financial, allocation, or boundary behavior, MEDIUM for another meaningful reachable numeric error, and LOW for a confined precision assumption. Recommend `intdiv()` for intended integer division or an explicit decimal type, precision, and rounding policy for non-integral results.

Public reference: Apache Groovy, "Arithmetic operators" and integer division (https://docs.groovy-lang.org/docs/groovy-latest/html/documentation/core-operators.html#_arithmetic_operators).
