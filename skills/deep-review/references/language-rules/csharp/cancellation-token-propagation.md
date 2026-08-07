---
rule_id: csharp.cancellation-token-propagation
---

Flag an omitted or replaced `CancellationToken` only when the containing operation receives a live token, a reachable downstream operation can accept it, both belong to the same cancellable lifetime, and omission demonstrably prevents timely cancellation. Inspect overloads, optional parameters, linked tokens, caller intent, and operation ownership. Do not flag an explicit cancellation boundary, independent background work, a non-cancellable downstream contract, or intentional `CancellationToken.None` or `default` use whose behavior is established.

Use HIGH when failed propagation can keep a critical operation running after cancellation and cause resource exhaustion, unsafe completion, or shutdown failure, MEDIUM for another reachable cancellation-contract violation with meaningful impact, and LOW for confined delayed cancellation. Recommend forwarding the correct token, passing an appropriately linked token, or documenting and enforcing an intentional lifetime boundary. Report this separately from a task-consumption finding only when cancellation has a distinct demonstrated impact.

Public reference: Microsoft .NET code-analysis rule CA2016, "Forward the CancellationToken parameter to methods that take one" (https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca2016).
