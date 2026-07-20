---
rule_id: javascript.async-promise-executor
---

Flag an `async` function passed to the `Promise` constructor only when a reachable `await`, throw, or rejected operation can leave the constructed Promise pending or route failure through the executor's ignored returned Promise. Inspect explicit `resolve` and `reject` paths; the `async` token alone is insufficient evidence of a harmful outcome. Do not duplicate the same defect as `javascript.unhandled-promise`.

Use HIGH when a critical operation can hang or lose a required failure, MEDIUM for another reachable lost rejection or permanently unsettled Promise, and LOW for confined error-handling ambiguity with a credible rejection path. Recommend returning the existing Promise or using a normal `async` function, or restricting `new Promise` to a synchronous callback adapter that calls `resolve` and `reject` explicitly.

Public reference: ESLint, `no-async-promise-executor` (https://eslint.org/docs/latest/rules/no-async-promise-executor).
