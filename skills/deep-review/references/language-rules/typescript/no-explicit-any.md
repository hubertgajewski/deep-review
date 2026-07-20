---
rule_id: typescript.no-explicit-any
---

Flag an explicit `any` introduced by the change only when it removes meaningful checking from a value that crosses a function, module, callback, or data boundary. Trace where the value originates and flows; do not flag generated declarations, deliberate compatibility boundaries with documented constraints, or a local value whose type is immediately validated.

Use MEDIUM when `any` escapes through an exported or shared contract or reaches a typed operation unchecked. Use LOW when the loss is confined and actionable. Recommend a concrete type, generic constraint, or `unknown` followed by narrowing. Do not report unused declarations.

Public references: TypeScript Handbook, "Everyday Types — any" (https://www.typescriptlang.org/docs/handbook/2/everyday-types.html#any) and typescript-eslint `no-explicit-any` (https://typescript-eslint.io/rules/no-explicit-any/).
