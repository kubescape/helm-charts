# Workflow permission contract tests

Install PyYAML if needed (`python3 -m pip install pyyaml`), then run from the repository root:

```sh
python3 -B -m unittest discover -s scripts/workflow-permissions -v
```

The tests check read-only workflow defaults, every local reusable-workflow call,
callee defaults, execution-job permissions, and nested caller ceilings. Negative
cases reproduce the original three incompatible callers and a denied permission
in the nested `03-helm-release.yaml` → `02-e2e-test.yaml` path. Caller write grants
are checked separately to prevent unintended escalation.

Explicit permission maps deny omitted scopes. A caller of a workflow declaring
`read-all` therefore lists every readable scope, plus only the writes needed by
that workflow's jobs. Execution jobs keep their narrower grants. The scope list
matches the [GitHub workflow schema](https://github.com/actions/languageservices/blob/4043eda158e16579cc5fb1b0b07a4bce2a76f0b5/workflow-parser/src/workflow-v1.0.json).
If GitHub adds readable scopes, update the test list and caller maps together.

Actionlint v1.7.12 does not recognize `code-quality`, `drives`, or
`vulnerability-alerts`, although the GitHub schema includes them. When using that
version, exclude only those scope warnings and the repository's existing
required-input/default and old-action-runtime diagnostics:

```sh
actionlint -shellcheck= -pyflakes= \
  -ignore 'unknown permission scope "(code-quality|drives|vulnerability-alerts)"' \
  -ignore 'input .* of workflow_call event has the default value .* but it is also required' \
  -ignore 'the runner of .* action is too old'
```

These are local static checks. They do not execute private system tests, publish
charts, or verify upstream token policy and credentials.
