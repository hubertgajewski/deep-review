---
rule_id: kotlin.swallowed-cancellation
---

Flag a `catch` surrounding suspending work only when `CancellationException` can reach it, the handler neither rethrows nor restores cancellation, and execution can incorrectly continue or report success after cancellation. Inspect the caught type, called suspend functions, handler exits, and enclosing coroutine scope. Do not flag a narrower exception that excludes cancellation, a handler that rethrows cancellation or calls `ensureActive()`, or a terminal boundary whose explicit contract consumes cancellation safely.

Use HIGH when swallowed cancellation keeps critical work alive, reports a false success, or violates a lifecycle boundary, MEDIUM for another meaningful reachable cancellation failure, and LOW for a confined cooperative-cancellation weakness. Recommend rethrowing `CancellationException` before handling other failures, calling `ensureActive()` where appropriate, or catching only the specific recoverable exception.

Public reference: Kotlin documentation, "Cancellation and timeouts" (https://kotlinlang.org/docs/cancellation-and-timeouts.html).
