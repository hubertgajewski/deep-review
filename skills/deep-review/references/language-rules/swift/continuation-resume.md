---
rule_id: swift.continuation-resume
---

Flag checked or unsafe continuation code only when a reachable path can fail to resume exactly once, can resume more than once, or can retain the continuation without a bounded completion contract. Enumerate success, failure, cancellation, synchronous-callback, and repeated-callback paths before reporting.

Use HIGH for a demonstrated double resume or critical path that never resumes, MEDIUM for another realistic exactly-once contract violation, and LOW for a confined ownership gap with a concrete missing path. Recommend a single completion gate, explicit cancellation completion, or an async API that avoids manual continuation ownership.

Public reference: Swift standard library documentation, `withCheckedContinuation(function:_:)` (https://developer.apple.com/documentation/swift/withcheckedcontinuation(function:_:)).
