---
rule_id: javascript.unhandled-promise
---

Flag a changed expression known from an `async` declaration, standard Promise API, or inspected local contract to produce a Promise only when it is neither awaited, returned, chained with rejection handling, nor deliberately detached behind explicit error and lifetime ownership, and rejection or ordering matters on a reachable path. Do not infer Promise production from an arbitrary function name. Findings owned by `javascript.async-promise-executor` or `javascript.async-foreach` take precedence and must not be duplicated under this rule.

Use HIGH for demonstrated loss of a critical failure or required ordering, MEDIUM for another reachable unhandled rejection or sequencing defect, and LOW for confined ambiguous ownership. Recommend awaiting or returning the Promise, attaching rejection handling, joining concurrent work, or moving intentional detachment behind a named helper with an explicit error and lifetime contract.

Public references: ECMAScript, `HostPromiseRejectionTracker` (https://tc39.es/ecma262/multipage/control-abstraction-objects.html#sec-host-promise-rejection-tracker) and Node.js, `unhandledRejection` (https://nodejs.org/api/process.html#event-unhandledrejection).
