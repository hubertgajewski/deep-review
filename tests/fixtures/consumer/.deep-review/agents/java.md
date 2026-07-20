---
name: java
description: Review Java language and JVM API correctness.
domain: java-jvm-correctness
applies_to:
  - "**/*.java"
prompt_scope: matched
output_schema: hml
blocking:
  - HIGH
  - MEDIUM
references:
  - "docs/java-guidelines.md"
---

Review Java changes for concrete correctness, resource-lifecycle, concurrency, and JVM API misuse. Follow the shared deep-review agent contract.
