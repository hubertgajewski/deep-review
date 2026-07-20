---
rule_id: groovy.elvis-falsy-default
---

Flag `value ?: fallback` or `value ?= fallback` only when `false`, zero, an empty string, or an empty collection is a valid reachable value that Groovy truth will replace incorrectly. Trace the value's domain and the fallback's downstream effect. Do not flag a deliberately truth-based default, a value that can only be null or truthy, or a replacement whose behavior is equivalent for every reachable consumer.

Use HIGH when the substitution corrupts a critical decision or externally visible value, MEDIUM for another meaningful reachable wrong default, and LOW for a confined fragile domain assumption. Recommend an explicit null test or the exact domain-specific condition that distinguishes absence from a valid false-ish value.

Public reference: Apache Groovy, "Elvis operator" (https://docs.groovy-lang.org/docs/groovy-latest/html/documentation/core-operators.html#_elvis_operator).
