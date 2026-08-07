---
rule_id: csharp.sync-over-async
---

Flag synchronous observation through `Task.Result`, `Wait`, `WaitAll`, `WaitAny`, or `GetAwaiter().GetResult()` only when surrounding execution demonstrates a reachable deadlock, thread starvation, responsiveness failure, or incorrect exception behavior. Inspect synchronization contexts, request or UI threads, static constructors and their initialization locks, task completion state, continuations, and caller contracts. Do not flag an already completed task or an unavoidable synchronous boundary whose blocking lifetime and exception behavior are explicit and proven safe.

Use HIGH when blocking can deadlock or exhaust threads in a critical service or interactive path, MEDIUM for another reachable scalability, responsiveness, or exception-contract defect, and LOW for a confined blocking bridge with credible operational risk. Recommend propagating asynchronous control flow and using `await`; when a synchronous boundary is truly required, recommend isolating it behind a documented bridge whose execution context cannot deadlock. Do not duplicate the same defect as `csharp.unobserved-task`.

Public reference: Microsoft .NET documentation, "Common async/await bugs — Deadlocks from blocking on async code" (https://learn.microsoft.com/en-us/dotnet/standard/asynchronous-programming-patterns/common-async-bugs#deadlocks-from-blocking-on-async-code).
