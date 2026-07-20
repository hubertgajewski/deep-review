# Deep Review

Deep Review is a configurable multi-agent code-review skill for local changes,
Git references, GitHub pull requests, and GitLab merge requests.

## Language reviewers

Matching TypeScript, Python, and Swift changes receive one repository-neutral language review in addition to the general review roster. Language agents own only their documented language-semantic rules; general concerns such as dead imports, unused symbols, runtime correctness, security, architecture, and simplification remain with their existing agents.

All language agents and rules are enabled by default. Consumers can disable a complete agent or individual rule in the trusted `.deep-review/config.toml`:

```toml
[language_agents]
disabled = ["swift"]

[language_rules]
disabled = ["typescript.no-explicit-any", "python.runtime-assert"]
```

Supported rule IDs:

- TypeScript: `typescript.no-explicit-any`, `typescript.unsafe-type-assertion`, `typescript.unsafe-non-null-assertion`, `typescript.non-exhaustive-union`, `typescript.unhandled-promise`
- Python: `python.mutable-default`, `python.bare-exception-handler`, `python.runtime-assert`
- Swift: `swift.unsafe-force-unwrap`, `swift.unsafe-force-cast`, `swift.actor-isolation`, `swift.sendable-boundary`, `swift.unstructured-task-lifetime`, `swift.continuation-resume`

Unknown or duplicate disable entries make the review incomplete instead of being ignored. Disabled rule fragments are excluded from the effective agent prompt.

## Continuous integration

GitLab CI runs the complete Python unit-test suite on Python 3.10 and 3.14.
The Python container images are pinned to reviewed multi-platform manifest
digests; digest updates must be made explicitly and reviewed like other code
changes.

Pipeline selection works as follows:

- A push to a branch without an open merge request creates a branch pipeline.
- After a merge request is open, its pipeline runs and the duplicate branch
  pipeline is suppressed.
- A pipeline started with **Build > Pipelines > New pipeline** in the GitLab UI
  remains available even when automatic pipelines are disabled.

### Disabling automatic pipelines

Automatic branch and merge-request pipelines are enabled by default. To disable
them, create a project or group CI/CD variable with these settings:

```text
Key: CI_ENABLED
Value: false
Type: Variable
Environment scope: All (*)
Protect variable: cleared
```

The value must be the exact lowercase string `false`. For a project variable,
open **Settings > CI/CD**, expand **Variables**, and select **Add variable**.
Leave **Protect variable** cleared if the gate should apply to unprotected
branches and merge requests as well.

Delete the variable or change it to `true` to re-enable automatic pipelines.
Manually started GitLab UI pipelines intentionally remain enabled because the
`web` pipeline-source rule is evaluated before the automatic-pipeline gate.
