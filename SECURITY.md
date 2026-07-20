# Security policy

## Supported versions

Until versioned releases are published, only the current default branch is supported with security fixes. Older commits and unmaintained forks are not supported.

## Report a vulnerability privately

Do not disclose a suspected vulnerability in a public issue, merge request, discussion, or chat.

Create a [new GitLab issue](https://gitlab.com/hubertgajewski-ai/deep-review/-/issues/new), select **Turn on confidentiality**, and verify that GitLab marks the issue confidential before submitting technical details. If the confidentiality option is unavailable, contact the maintainer through their [GitLab profile](https://gitlab.com/hubertgajewski) and request a private reporting channel without including vulnerability details in the first message.

Include, where possible:

- the affected commit or version;
- the vulnerable component and expected security boundary;
- reproducible steps or a minimal proof of concept;
- the impact and required preconditions;
- any suggested mitigation;
- whether the issue has been disclosed elsewhere.

## Scope

Security reports may cover prompt-injection boundaries, unsafe handling of untrusted repository content, path traversal or symlink escapes, unintended secret access or persistence, command injection, remote-review identity confusion, cache poisoning, and vulnerabilities in bundled scripts.

Ordinary review-quality disagreements, unsupported clients, feature requests, and findings in code merely reviewed by Deep Review should use normal project issues unless they reveal a security boundary failure in Deep Review itself.

## Response and disclosure

The maintainer will aim to acknowledge a complete report within five business days and provide an initial assessment or request for more information within ten business days. Remediation and disclosure timing depend on severity and complexity. Please allow a coordinated fix and release before public disclosure.
