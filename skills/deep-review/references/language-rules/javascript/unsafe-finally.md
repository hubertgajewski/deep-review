---
rule_id: javascript.unsafe-finally
---

Flag a reachable `return`, `throw`, `break`, or `continue` originating in a `finally` block only when it replaces or discards an earlier return value, exception, or control transfer from the associated `try` or `catch`. Inspect branch reachability and distinguish control flow inside a nested function, generator, class, or method. Do not report a `finally` block that completes normally or cleanup that preserves the pending completion.

Use HIGH when the replacement hides a critical rejection or exception or returns a false success, MEDIUM for another reachable discarded result or failure, and LOW for confined conditional control flow with a credible masking path. Recommend allowing `finally` to complete normally, moving the decision outside the block, or explicitly preserving and propagating the original completion.

Public references: ESLint, `no-unsafe-finally` (https://eslint.org/docs/latest/rules/no-unsafe-finally) and ECMAScript, "The `try` Statement" (https://tc39.es/ecma262/multipage/ecmascript-language-statements-and-declarations.html#sec-try-statement).
