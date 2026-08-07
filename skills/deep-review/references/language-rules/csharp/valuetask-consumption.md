---
rule_id: csharp.valuetask-consumption
---

Flag a `ValueTask` returned by a member only when it is awaited more than once, converted with `AsTask()` more than once, consumed through multiple forms, discarded when completion matters, or accessed through `Result` before it is known complete. Trace copies, fields, branches, and consumers. For an arbitrary member result, assume single consumption unless inspected implementation proves reusable `Task` backing or synchronous completion; do not flag repeated observation of the single `Task` produced by one `AsTask()` call.

Use HIGH when invalid consumption can corrupt pooled operation state, lose a critical failure, or break required completion, MEDIUM for another reachable exception, corruption, or completion defect, and LOW for confined misuse with credible provider-dependent risk. Recommend directly awaiting the `ValueTask` exactly once, or converting it once to `Task` and reusing that task when repeated observation is required. Do not duplicate the same defect as `csharp.unobserved-task`.

Public references: Microsoft .NET code-analysis rule CA2012, "Use ValueTasks correctly" (https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca2012) and the `ValueTask` API contract (https://learn.microsoft.com/en-us/dotnet/api/system.threading.tasks.valuetask).
