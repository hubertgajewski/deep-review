---
rule_id: swift.unstructured-task-lifetime
---

Flag creation of an unstructured task only when its lifetime, cancellation, actor inheritance, or error ownership can outlive or diverge from the operation that requires it. Trace task handles, captures, cancellation, and result consumption. Do not report deliberate independent work with explicit ownership and error handling.

Use HIGH when detached lifetime can mutate released or superseded critical state, MEDIUM for another reachable cancellation, ordering, or error-ownership defect, and LOW for confined ambiguous ownership. Recommend structured concurrency, retaining and cancelling the task handle, awaiting its result, or moving independent work behind an explicit owner.

Public reference: Swift language reference, "Concurrency — Unstructured Concurrency" (https://docs.swift.org/swift-book/documentation/the-swift-programming-language/concurrency/#Unstructured-Concurrency).
