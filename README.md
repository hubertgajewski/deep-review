# Deep Review

Deep Review is a configurable multi-agent code-review skill for local changes,
Git references, GitHub pull requests, and GitLab merge requests.

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
