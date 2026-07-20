---
rule_id: javascript.unsafe-optional-chaining
---

Flag optional chaining only when its `undefined` result can reach a context that requires another callable, constructible, object, or iterable value and therefore throws or produces a demonstrated invalid result. Inspect nullish provenance, the complete continuous chain, parentheses, fallbacks, and dominating checks. Do not flag a chain that safely propagates absence, supplies a valid fallback, or is proven non-nullish on the path.

Use HIGH when the unsafe continuation can fail a critical public operation, MEDIUM for another reachable `TypeError` or meaningful invalid result, and LOW for a confined fragile chain. Recommend extending the optional chain through the unsafe operation, supplying an appropriate `??` fallback, or narrowing the value before calling, constructing, spreading, destructuring, iterating, or applying a requiring operator.

Public references: ESLint, `no-unsafe-optional-chaining` (https://eslint.org/docs/latest/rules/no-unsafe-optional-chaining) and ECMAScript, "Optional Chains" (https://tc39.es/ecma262/multipage/ecmascript-language-expressions.html#sec-optional-chains).
