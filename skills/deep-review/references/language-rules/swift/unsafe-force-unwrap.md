---
rule_id: swift.unsafe-force-unwrap
---

Flag a force unwrap only when the optional can be `nil` on a reachable path and no construction, pattern-match, or dominating check establishes a non-nil invariant. Trace the optional's origin and lifecycle. Do not report test fixtures or values whose non-nil guarantee is structurally proven in the reviewed state.

Use HIGH for a demonstrated crash in a public or critical path, MEDIUM for another realistic reachable nil, and LOW for a confined fragile invariant. Recommend optional binding, `guard`, a throwing requirement, a fallback, or a type that represents guaranteed presence.

Public reference: The Swift Programming Language, "The Basics — Optionals" (https://docs.swift.org/swift-book/documentation/the-swift-programming-language/thebasics/#Optionals).
