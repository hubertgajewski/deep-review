---
rule_id: python.bare-exception-handler
---

Flag a newly added bare `except:` only when it swallows control-flow exceptions or converts an otherwise observable failure into incorrect continuation. Inspect the handler, re-raise behavior, and surrounding cleanup. Do not report a minimal cleanup boundary that immediately re-raises or intentionally handles `BaseException` with documented semantics.

Use HIGH when the handler can hide termination or a critical failure and continue incorrectly, MEDIUM for another reachable swallowed failure, and LOW for a confined overly broad boundary with a concrete narrowing opportunity. Recommend catching the specific expected exception and preserving or re-raising unexpected failures.

Public reference: PEP 8, "Programming Recommendations" (https://peps.python.org/pep-0008/#programming-recommendations).
