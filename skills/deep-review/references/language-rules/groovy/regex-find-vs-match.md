---
rule_id: groovy.regex-find-vs-match
---

Flag boolean use of `=~` only when the contract requires the entire input to match, or use of `==~` only when the contract requires finding a substring, and demonstrate a reachable input whose classification changes. Remember that `=~` produces a `Matcher` whose truth uses `find`, while `==~` returns a strict-match boolean. Do not flag intentional matcher iteration, capture extraction, explicit anchoring with a correct consumer, or a pattern whose accepted language is equivalent in context.

Use HIGH when the distinction creates a critical validation bypass, MEDIUM for another meaningful reachable acceptance or rejection error, and LOW for a confined boundary weakness. Recommend `==~` for whole-input validation, `=~` or explicit `find()` for discovery, and tests containing both valid surrounding text and invalid partial matches.

Public reference: Apache Groovy, "Comparing Find vs Match operators" (https://docs.groovy-lang.org/docs/groovy-latest/html/documentation/core-operators.html#_comparing_find_vs_match_operators).
