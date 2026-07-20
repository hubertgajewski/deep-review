---
rule_id: typescript.unhandled-promise
---

Flag a changed promise-producing expression only when it is neither awaited, returned, deliberately detached with explicit rejection handling, nor otherwise consumed, and rejection or ordering matters on a reachable path. Trace the declared return type and caller control flow. Do not flag intentionally fire-and-forget work that owns its error handling and lifetime.

Use HIGH for demonstrated loss of a critical failure or required ordering, MEDIUM for another reachable unhandled rejection or sequencing defect, and LOW for confined ambiguous ownership. Recommend awaiting, returning, attaching rejection handling, or moving deliberate detachment behind a named helper with an explicit contract.

Public reference: typescript-eslint `no-floating-promises` (https://typescript-eslint.io/rules/no-floating-promises/).
