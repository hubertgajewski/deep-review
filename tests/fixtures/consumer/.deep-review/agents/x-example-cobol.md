---
name: x-example-cobol
description: Review COBOL data-layout and arithmetic correctness.
domain: x-example-cobol-data-layout
applies_to:
  - "**/*.cbl"
  - "**/*.cob"
  - "**/*.ccp"
  - "**/*.cpy"
prompt_scope: matched
output_schema: hml
blocking:
  - HIGH
  - MEDIUM
references:
  - "docs/cobol-guidelines.md"
---

Review COBOL changes for concrete data-layout, numeric representation, copybook compatibility, and arithmetic-semantic defects. Follow the shared deep-review agent contract.
