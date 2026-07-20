---
rule_id: javascript.loss-of-precision
---

Flag a changed numeric literal only when conversion to JavaScript `Number` loses digits written by the author and the exact value matters to a reachable identifier, counter, timestamp, monetary amount, protocol field, comparison, or calculation. Compare the actual representable value; magnitude alone is not proof. Do not flag exactly representable literals or deliberately approximate scientific constants whose precision is sufficient for their use.

Use HIGH when rounding can corrupt a critical identifier, monetary value, or protocol boundary, MEDIUM for another reachable exactness defect, and LOW for confined precision loss with limited impact. Recommend a corrected exactly representable literal, `BigInt` for integral arithmetic where compatible, a string for opaque identifiers, or a suitable decimal representation.

Public reference: ESLint, `no-loss-of-precision` (https://eslint.org/docs/latest/rules/no-loss-of-precision).
