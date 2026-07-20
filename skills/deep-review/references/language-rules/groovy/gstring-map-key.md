---
rule_id: groovy.gstring-map-key
---

Flag an interpolated `GString` used as a map key only when an inspected lookup, removal, membership check, serialization boundary, or caller uses the equivalent plain `String` and can miss the entry because `GString` and `String` hash codes differ. Do not flag interpolation used only as a value, a key converted to `String` before insertion, or a map whose relevant operations demonstrably use the same key representation.

Use HIGH when the missed entry bypasses a critical lookup or corrupts durable state, MEDIUM for another meaningful reachable lookup failure, and LOW for a confined representation hazard with a concrete consumer. Recommend converting the interpolated key to `String` at the map boundary and using one stable key representation for insertion and access.

Public reference: Apache Groovy, "GString and String hashCodes" (https://docs.groovy-lang.org/docs/latest/html/documentation/#_gstring_and_string_hashcodes).
