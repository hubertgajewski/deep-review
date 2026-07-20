---
rule_id: python.mutable-default
---

Flag a mutable default argument only when the function can mutate that object directly or through a callee, allowing state to leak between calls. Inspect the complete body and called helpers; do not report an immutable default, a sentinel, or a mutable object that is never mutated or exposed.

Use HIGH when cross-call state can corrupt a public or critical operation, MEDIUM for another demonstrated reachable mutation, and LOW for a confined exposed default whose mutation risk is credible but not yet exercised. Recommend a `None` or immutable sentinel and allocate the mutable value inside the function.

Public reference: Python tutorial, "Default Argument Values" (https://docs.python.org/3/tutorial/controlflow.html#default-argument-values).
