---
rule_id: csharp.disposable-lifetime
---

Flag acquisition or construction of an owned `IDisposable` or `IAsyncDisposable` only when the concrete value holds a releasable resource and a normal or exceptional exit can leave it undisposed. Trace factories, wrappers, returned values, fields, dependency-injection or host ownership, explicit transfer, and enclosing synchronous or asynchronous resource scopes. Do not flag a resource managed by a container, transferred to another lifecycle owner, returned to the caller, or known not to require deterministic release.

Use HIGH when a reachable leak can exhaust a critical process-wide resource, prevent transactional completion, or block shutdown, MEDIUM for another repeatable file, socket, database, executor, or native-resource leak, and LOW for a confined leak with bounded impact. Recommend `using`, `await using`, `try`/`finally`, or an explicit lifecycle owner appropriate to whether cleanup is synchronous or asynchronous.

Public references: Microsoft .NET documentation, "Using objects that implement IDisposable" (https://learn.microsoft.com/en-us/dotnet/standard/garbage-collection/using-objects), "Implement a DisposeAsync method" (https://learn.microsoft.com/en-us/dotnet/standard/garbage-collection/implementing-disposeasync), and code-analysis rule CA2000 (https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca2000).
