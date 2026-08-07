---
rule_id: csharp.unobserved-task
---

Flag a known `Task`-producing expression only when completion, ordering, or failure matters on a reachable path and the task is neither awaited, returned, composed, nor deliberately detached with explicit lifetime and exception ownership. Inspect declarations or standard APIs rather than inferring task production from a method name. Also inspect nested tasks from APIs such as `Task.Factory.StartNew(async ...)` and report when only the outer task is observed while the required inner operation is not. Do not flag intentionally independent work whose lifetime and failure handling are explicit.

Use HIGH when a lost task failure, premature success, or omitted inner completion can corrupt a critical operation, MEDIUM for another reachable lost exception or required-ordering defect, and LOW for confined work with a credible but nonblocking observation gap. Recommend awaiting, returning, or composing the task; for a nested task, recommend `Task.Run`, `Unwrap`, or observing both layers as the surrounding contract requires. Do not duplicate a defect owned by `csharp.async-void`, `csharp.valuetask-consumption`, or `csharp.sync-over-async`.

Public references: Microsoft C# compiler guidance for CS4014 (https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/compiler-messages/async-await-errors) and Microsoft .NET documentation, "Common async/await bugs" (https://learn.microsoft.com/en-us/dotnet/standard/asynchronous-programming-patterns/common-async-bugs).
