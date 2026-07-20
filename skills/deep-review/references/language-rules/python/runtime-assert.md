---
rule_id: python.runtime-assert
---

Flag an `assert` introduced as required production input validation, state transition enforcement, or error handling when optimized execution may remove it. Read the surrounding code and distinguish test assertions and internal debug invariants from checks required for correct runtime behavior. Defer independently demonstrated access-control impact to the security reviewer.

Use HIGH when removal bypasses a critical boundary, MEDIUM when removal permits another concrete invalid state, and LOW for a confined runtime precondition whose failure remains bounded. Recommend an explicit conditional raising the appropriate exception; retain `assert` only for nonessential internal invariants.

Public reference: Python language reference, "The assert statement" (https://docs.python.org/3/reference/simple_stmts.html#the-assert-statement).
