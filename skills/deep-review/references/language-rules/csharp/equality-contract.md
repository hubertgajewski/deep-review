---
rule_id: csharp.equality-contract
---

Flag changed equality behavior only when `object.Equals`, `IEquatable<T>.Equals`, `GetHashCode`, `==`, or `!=` demonstrably disagree about equal instances, use incompatible participating state, violate reflexivity, symmetry, transitivity, or consistency, or allow equal objects to return different hash codes. Also report mutable equality state only when affected instances are used as hashed keys or members and mutation can make them unreachable. Do not flag consistent records or generated implementations, deliberate reference identity, or harmless hash collisions between unequal values.

Use HIGH when inconsistency can corrupt critical keyed state, identity, or deduplication, MEDIUM for another reachable collection or equality failure, and LOW for a confined contract mismatch not yet used in hashed storage. Recommend deriving every equality member and operator from the same stable value state, implementing paired operators consistently, or using an immutable record or value object where appropriate.

Public references: Microsoft C# reference, "Equality operators" (https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/operators/equality-operators), .NET Framework Design Guidelines, "Equality Operators" (https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/equality-operators), and code-analysis rule CA2218 (https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca2218).
