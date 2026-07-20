---
rule_id: typescript.non-exhaustive-union
---

Flag changed branching over a discriminated union only when one or more declared variants can reach the branch without correct handling, or when an exported evolving union is handled without a compiler-checked `never` exhaustiveness guard and a silent fallback would accept future variants incorrectly. Read the union declaration and every relevant branch.

Use HIGH for a currently unhandled variant on a critical path, MEDIUM for another currently reachable variant or a public silent fallback that defeats exhaustiveness, and LOW for a confined growth hazard. Recommend handling the missing variant or adding a `never`-based exhaustive guard.

Public reference: TypeScript Handbook, "Union Exhaustiveness checking" (https://www.typescriptlang.org/docs/handbook/unions-and-intersections.html#union-exhaustiveness-checking).
