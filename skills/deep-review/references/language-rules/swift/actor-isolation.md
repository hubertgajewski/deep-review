---
rule_id: swift.actor-isolation
---

Flag changed code that accesses actor-isolated mutable state from an incompatible isolation domain, drops a required actor annotation, or uses an unsafe isolation escape without a proven executor guarantee. Trace annotations, call sites, suspension points, and state ownership. Do not infer a race merely from asynchronous syntax.

Use HIGH for a demonstrated cross-isolation mutation or critical ordering violation, MEDIUM for another reachable unsafe isolation boundary, and LOW for a confined annotation gap with a concrete risk. Recommend preserving isolation through actor methods, annotations, `await`, immutable transfer, or an explicitly safe ownership redesign.

Public reference: Swift language reference, "Concurrency" (https://docs.swift.org/swift-book/documentation/the-swift-programming-language/concurrency/).
