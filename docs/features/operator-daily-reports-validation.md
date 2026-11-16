# Operator daily-report image validation

The default Operator v0.2.188 contains the offline report fix from
[operator#421](https://github.com/kubescape/operator/pull/421). v0.2.181 is the
first compatible release identified in the review of helm-charts#935.
Rebasing onto main `1607513` already brings the newer v0.2.188 default, so this
PR preserves that version instead of downgrading it to v0.2.181.

## Reproduce

Requires Helm 3, Podman, OpenSSL, Python 3 with PyYAML, and free local ports 4002
and 8000. From the repository root:

```sh
podman pull quay.io/kubescape/operator:v0.2.181
podman pull quay.io/kubescape/operator:v0.2.188
python3 scripts/verify-operator-daily-reports.py --image quay.io/kubescape/operator:v0.2.181
python3 scripts/verify-operator-daily-reports.py --image quay.io/kubescape/operator:v0.2.188
helm unittest charts/kubescape-operator -f tests/operator_daily_reports_test.yaml
helm lint --strict charts/kubescape-operator --kube-version 1.28.0 --set clusterName=offline-test --set capabilities.kubescapeOffline=enable
helm lint --strict charts/kubescape-operator --kube-version 1.28.0 --set clusterName=online-test
```

The script runs the published image's unmodified entrypoint. It renders the
chart with Kubernetes 1.28, mounts the Operator's ConfigMap data using the
Deployment's volume key mappings, and passes the rendered literal environment
variables. A local Kubernetes API fixture supplies report metadata. A TLS proxy
with a temporary trusted certificate receives the actual HTTPS POST for
`version-check.ks-services.co`; no test reports are forwarded to that service.

The rendered test configuration uses `clusterName=report-fixture`, disables
continuous scanning, vulnerability scanning, relevancy, admission control, rule
updates and the node-agent autoscaler to reach the reporting path without other
running components. Configuration scanning stays enabled to keep the Operator
enabled. These settings are identical across the three cases except for
`capabilities.kubescapeOffline` and the conflicting override:

| Case | Offline capability | User `operator.env` | Rendered skip value |
| --- | --- | --- | --- |
| online | disable | none | absent |
| offline | enable | none | `true` |
| offline-conflict | enable | `KS_SKIP_UPDATE_CHECK=false` | `true` |

Each case runs for 20 seconds. Successful validation requires readiness, no
fatal startup error, one received daily-report POST and its response logged by
the online Operator, and zero report POSTs in both offline cases. The receiver
also checks the POST method and `daily-report` context in the request body.

This verifies the packaged binary's immediate reporting path using chart
configuration. It does not test a full Kubernetes installation or wait for the
24-hour timer. The API fixture does not validate Kubernetes RBAC or other
Operator features.

## Results recorded on 2026-10-17

Helm v3.19.0 and Podman 5.8.9 on Linux/amd64:

| Published tag | Ready in all three cases | Online POSTs | Offline POSTs | Offline-conflict POSTs |
| --- | --- | --- | --- | --- |
| v0.2.181 | yes | 1 | 0 | 0 |
| v0.2.188 (default) | yes | 1 | 0 | 0 |

The online bodies contained `context=daily-report`,
`clusterID=report-fixture` and `helmChartVersion=kubescape-operator-1.41.0`.
Both online Operators logged `local daily-report fixture accepted`, confirming
that the HTTPS receiver returned a response consumed by the packaged binary.

Image digests observed during validation:

| Tag | Registry index digest | Executed linux/amd64 manifest digest |
| --- | --- | --- |
| v0.2.181 | `sha256:6aee02b07198d9e35c9e7ed5a5f30ec6d29572954029a0fff37bd189f9fd39e7` | `sha256:234f459ff00f57a73116e9731ecbd24293c6087b6af861a3ed150e3649aa852a` |
| v0.2.188 | `sha256:d475fd37a5e6da6b5b5e1b03fb30c24c332f9bd0f16c950fc5a6caca81a37a80` | `sha256:ca17ab0f60ce35875e71a7b2d713a8172dd364b0c390eeced79fd544610dae10` |

The six targeted Helm tests and strict online/offline lint passed. Full chart
tests had 168 passing tests and 20 failing snapshot cases (38 mismatches).
The same full suite on clean main `1607513` had 162 passing tests and the same
20 failing snapshot cases / 38 mismatches; all six added regression tests pass.
