---
rule_id: java.unsafe-finally
---

Flag a reachable `return`, `throw`, `break`, or `continue` originating in a `finally` block only when it replaces or discards an earlier return value, exception, or control transfer from the associated `try` or `catch`. Inspect branch reachability and distinguish control flow inside a nested lambda, local class, or method declaration. Do not report a `finally` block that completes normally or cleanup that preserves the pending completion.

Use HIGH when the replacement hides a critical failure or returns a false success, MEDIUM for another reachable discarded result or exception, and LOW for confined conditional control flow with a credible masking path. Recommend allowing `finally` to complete normally, moving the decision outside the block, or explicitly preserving and propagating the original completion.

Public reference: Java Language Specification, "Execution of `try`-`finally` and `try`-`catch`-`finally`" (https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20.2).
