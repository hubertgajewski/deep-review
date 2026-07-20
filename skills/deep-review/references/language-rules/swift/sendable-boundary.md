---
rule_id: swift.sendable-boundary
---

Flag a value crossing a concurrency boundary only when it contains shared mutable or otherwise non-transfer-safe state and the change incorrectly declares, assumes, or bypasses `Sendable`. Inspect stored properties, ownership, synchronization, and all relevant conformances. Do not report immutable value semantics or compiler-proven transfers.

Use HIGH for demonstrated unsynchronized shared mutation across tasks or actors, MEDIUM for another concrete unsafe transfer, and LOW for a confined unchecked conformance whose invariant is fragile. Recommend immutable value transfer, actor ownership, synchronization, or a justified checked conformance rather than `@unchecked Sendable` without proof.

Public reference: Swift language reference, "Concurrency — Sendable Types" (https://docs.swift.org/swift-book/documentation/the-swift-programming-language/concurrency/#Sendable-Types).
