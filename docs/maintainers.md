# Maintainer operations

This guide contains repository-administration details that are not needed by ordinary Deep Review users.

## Continuous integration

GitLab CI runs the complete Python unit-test suite on Python 3.10 and 3.14. Python container images are pinned to reviewed multi-platform manifest digests; update those digests explicitly and review the change like other code.

Pipeline selection works as follows:

- A push to a branch without an open merge request creates a branch pipeline.
- After a merge request is open, its pipeline runs and the duplicate branch pipeline is suppressed.
- A pipeline started with **Build > Pipelines > New pipeline** remains available when automatic pipelines are disabled.

### Disable automatic pipelines

Create a project or group CI/CD variable with these settings:

```text
Key: CI_ENABLED
Value: false
Type: Variable
Environment scope: All (*)
Protect variable: cleared
```

The value must be the exact lowercase string `false`. For a project variable, open **Settings > CI/CD**, expand **Variables**, and select **Add variable**. Leave **Protect variable** cleared if the gate should also apply to unprotected branches and merge requests.

Delete the variable or change it to `true` to re-enable automatic pipelines. Manually started web pipelines intentionally remain enabled because the `web` pipeline-source rule is evaluated before the automatic-pipeline gate.

## Runtime documentation

The files under `skills/deep-review/references/` are normative. Update them and their contract tests together when behavior changes; keep this guide focused on repository operations.
