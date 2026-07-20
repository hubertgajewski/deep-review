---
rule_id: javascript.async-foreach
---

Flag an asynchronous `Array.prototype.forEach` callback only when the caller depends on callback completion or ordering, or when a callback rejection can escape without explicit handling. Inspect the callback, surrounding function, subsequent statements, and whether each callback owns its errors. Do not flag deliberately independent work whose lifetime and rejection handling are explicit. Do not duplicate the same defect as `javascript.unhandled-promise`.

Use HIGH when a critical operation reports success before required work completes or loses a critical rejection, MEDIUM for another reachable ordering, completion, or rejection defect, and LOW for confined ambiguous asynchronous ownership. Recommend `for...of` with `await` for sequential work, or `await Promise.all(array.map(...))` for concurrent work whose completion and failures must be joined.

Public references: ECMAScript, `Array.prototype.forEach` (https://tc39.es/ecma262/multipage/indexed-collections.html#sec-array.prototype.foreach) and MDN, `Array.prototype.forEach()` (https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/forEach).
