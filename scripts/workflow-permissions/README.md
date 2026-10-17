# Workflow permission contract tests

Install PyYAML if needed (`python3 -m pip install pyyaml`), then run from the repository root:

```sh
python3 -B -m unittest discover -s scripts/workflow-permissions -v
```

The tests check read-only workflow defaults, every local reusable-workflow call,
callee defaults, execution-job permissions, and nested caller ceilings. Negative
cases reproduce the original three incompatible callers and a denied permission
in the nested `03-helm-release.yaml` → `02-e2e-test.yaml` path. Every job's effective
write grants are checked against a static approved set, including jobs that inherit
`read-all` and need no writes. The expected job keys must match the loaded jobs, so
adding or renaming a job requires an explicit review of its write permissions.

Explicit permission maps deny omitted scopes. A caller of a workflow declaring
`read-all` therefore lists every readable scope, plus only the writes needed by
that workflow's jobs. Execution jobs keep their narrower grants. The scope list
matches the [GitHub workflow schema](https://github.com/actions/languageservices/blob/4043eda158e16579cc5fb1b0b07a4bce2a76f0b5/workflow-parser/src/workflow-v1.0.json).
If GitHub adds readable scopes, update the test list and caller maps together.

Actionlint v1.7.12 does not recognize `code-quality`, `drives`, or
`vulnerability-alerts`, although the GitHub schema includes them. When using that
version, exclude only those scope warnings and the repository's two existing
required-input/default diagnostics:

```sh
actionlint -shellcheck= -pyflakes= \
  -ignore 'unknown permission scope "(code-quality|drives|vulnerability-alerts)"' \
  -ignore 'input .* of workflow_call event has the default value .* but it is also required'
```

These are local static checks. They do not execute private system tests, publish
charts, or verify upstream token policy and credentials.
Successful upstream runs of `pr-created` establish Helm unit-test coverage only.
Issue #950's runtime criterion still requires successful runs using the proposed
permissions through `00-cicd.yaml` → `01-update_tag.yaml`, `00-cicd.yaml` →
`03-helm-release.yaml` → `02-e2e-test.yaml`, and
`inspektor-trigger-e2e-tests.yaml` → `relevancy-e2e-test.yaml`, including release,
attestation, and report uploads, or explicit maintainer acceptance of that gap.
These paths require upstream credentials and can update branches or publish
charts; they are not part of the local test command above.
