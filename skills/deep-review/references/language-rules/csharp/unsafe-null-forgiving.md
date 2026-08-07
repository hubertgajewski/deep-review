---
rule_id: csharp.unsafe-null-forgiving
---

Flag the postfix null-forgiving operator `!` only when the suppressed expression can realistically be `null` on a reachable path and the value reaches a dereference, non-null contract, or other operation with concrete failure impact. Inspect the effective nullable annotation and warning contexts, assignments, attributes, guards, constructors, and callers. Do not flag a value whose non-null invariant is established by inspected control flow or an external contract, or test code that deliberately supplies `null` to exercise validation.

Use HIGH when the suppression can crash a critical public operation or corrupt a required non-null boundary, MEDIUM for another reachable `NullReferenceException` or contract violation with meaningful impact, and LOW for a confined fragile assumption with credible nullable provenance. Recommend preserving nullable flow, adding an explicit guard or boundary validation, or correcting annotations so the compiler can prove the invariant without suppression.

Public references: Microsoft C# reference, "! (null-forgiving) operator" (https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/operators/null-forgiving) and "Nullable reference types" (https://learn.microsoft.com/en-us/dotnet/csharp/fundamentals/null-safety/nullable-reference-types).
