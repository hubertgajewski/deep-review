---
rule_id: java.autocloseable-lifetime
---

Flag acquisition or construction of an owned `AutoCloseable` only when the concrete object holds a releasable resource and a normal or exceptional exit can leave it unclosed. Trace factories, wrappers, ownership transfer, returned values, fields, and enclosing resource scopes. Do not flag a resource whose ownership is transferred, whose lifetime is managed by a surrounding container, or a non-I/O stream or other `AutoCloseable` instance known not to require release.

Use HIGH when a reachable leak can exhaust a critical process-wide resource or corrupt transactional completion, MEDIUM for another repeatable file, socket, database, executor, or native-resource leak, and LOW for a confined leak with bounded impact. Recommend `try`-with-resources at the owning scope, or an explicit lifecycle owner when the resource intentionally outlives the method.

Public references: Java SE API, `AutoCloseable` (https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html) and Java Language Specification, "`try`-with-resources" (https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20.3).
