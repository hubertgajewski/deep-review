---
rule_id: swift.unsafe-force-cast
---

Flag `as!` only when the runtime value can have another type on a reachable path and no closed construction invariant proves the cast. Trace producers and collection or decoding boundaries. Do not report a cast whose type guarantee is established by an immediately preceding check or a sealed internal construction path.

Use HIGH for a demonstrated critical-path cast trap, MEDIUM for another realistic reachable mismatch, and LOW for a confined fragile invariant. Recommend conditional casting, pattern matching, a generic constraint, or changing the producer contract to return the required type.

Public reference: The Swift Programming Language, "Type Casting" (https://docs.swift.org/swift-book/documentation/the-swift-programming-language/typecasting/).
