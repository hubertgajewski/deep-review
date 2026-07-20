---
rule_id: kotlin.run-blocking-in-suspend
---

Flag `runBlocking` only when it executes inside a suspending function or an existing coroutine and can block the coroutine thread, ignore the current coroutine context, or contribute to reachable thread starvation. Inspect the caller and execution context rather than assuming every call is wrong. Do not flag a normal blocking entry point, test bridge, or non-suspending callback that deliberately adapts suspending work to a blocking contract.

Use HIGH when the call can starve or deadlock a critical constrained dispatcher, MEDIUM for another meaningful reachable blocking or context-loss defect, and LOW for a confined nested-event-loop risk. Recommend calling the suspending operation directly, using `coroutineScope` for structured children, or moving genuinely blocking work to an appropriate dispatcher without nesting `runBlocking`.

Public reference: kotlinx.coroutines API, "runBlocking: Calling from a suspend function" (https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines/run-blocking.html#calling-from-a-suspend-function).
