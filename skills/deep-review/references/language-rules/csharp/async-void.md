---
rule_id: csharp.async-void
---

Flag an `async void` method or an async lambda converted to a void-returning delegate only when it is not a genuine event handler or required callback and a reachable caller needs to observe completion, ordering, or failure. Inspect delegate types, registrations, framework contracts, callers, and exception handling. Do not flag a top-level event handler or a callback whose required signature is void and whose body explicitly owns all asynchronous failures and lifetime.

Use HIGH when an unobservable exception or completion race can terminate or corrupt a critical operation, MEDIUM for another reachable lost failure or required-ordering defect, and LOW for a confined callback lifetime risk. Recommend returning `Task` or `Task<T>` and awaiting or propagating it; when a void callback contract is unavoidable, recommend delegating immediately to a task-returning method and explicitly owning its failures.

Public reference: Microsoft .NET documentation, "Common async/await bugs — Can't await an async void method" (https://learn.microsoft.com/en-us/dotnet/standard/asynchronous-programming-patterns/common-async-bugs#cant-await-an-async-void-method).
