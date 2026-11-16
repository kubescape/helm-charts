# Research: component image freshness (#987)

Investigation baseline: 12 November 2026, chart repository commit
[`235e2d89`](https://github.com/kubescape/helm-charts/tree/235e2d89aa46ec01dfdba19f734023f39c2fef8c).
This note records evidence and design constraints; it does not establish that
any proposed image combination has been tested or is compatible.

## Existing release process

[Issue #987](https://github.com/kubescape/helm-charts/issues/987) reports that
component releases can outpace stable chart releases. The chart pins component
images in [`values.yaml`](https://github.com/kubescape/helm-charts/blob/235e2d89aa46ec01dfdba19f734023f39c2fef8c/charts/kubescape-operator/values.yaml).
The [workflow guide](https://github.com/kubescape/helm-charts/blob/235e2d89aa46ec01dfdba19f734023f39c2fef8c/.github/workflows/README.md)
describes manual image, snapshot, and documentation updates, with coupled
components grouped together. [PR #992](https://github.com/kubescape/helm-charts/pull/992)
removed the stopped per-component workflow, which had automatically merged and
published charts; it did not establish that independently updating components
is safe.

[PR #991](https://github.com/kubescape/helm-charts/pull/991) grouped storage,
node-agent, and kubevuln for an SBOM change. [PR #999](https://github.com/kubescape/helm-charts/pull/999)
coordinated components for API authentication. Therefore a same-minor patch
selection is a candidate policy, not evidence of schema, protocol, or
authentication compatibility. [PR #929](https://github.com/kubescape/helm-charts/pull/929),
[#996](https://github.com/kubescape/helm-charts/pull/996), and
[#1000](https://github.com/kubescape/helm-charts/pull/1000) addressed the old
helper image paths separately.

## Component mapping at the baseline

Each image is `quay.io/kubescape/<repository>` and each release repository is
`github.com/kubescape/<repository>`. The table captures defaults at the baseline;
it is not a live version inventory.

| Values key | Repository | Baseline tag |
| --- | --- | --- |
| `nodeAgent.image.tag` | [node-agent](https://github.com/kubescape/node-agent/releases) | `v0.3.310` |
| `kubevuln.image.tag` | [kubevuln](https://github.com/kubescape/kubevuln/releases) | `v0.3.578` |
| `storage.image.tag` | [storage](https://github.com/kubescape/storage/releases) | `v0.0.382` |
| `operator.image.tag` | [operator](https://github.com/kubescape/operator/releases) | `v0.2.209` |
| `kubescape.image.tag` | [kubescape](https://github.com/kubescape/kubescape/releases) | `v4.0.20` |
| `synchronizer.image.tag` | [synchronizer](https://github.com/kubescape/synchronizer/releases) | `v0.0.175` |
| `prometheusExporter.image.tag` | [prometheus-exporter](https://github.com/kubescape/prometheus-exporter/releases) | `v0.2.27` |

The [shared component release workflow](https://github.com/kubescape/workflows/blob/e44559c59f0d665afa7f277513e01eb546037b98/.github/workflows/incluster-comp-pr-merged.yaml)
and [node-agent's release workflow](https://github.com/kubescape/node-agent/blob/main/.github/workflows/incluster-comp-pr-merged.yaml)
retag images before publishing releases. A release record alone does not prove
that its image remains available or contains the desired platforms; inspect the
registry manifest for each selected candidate. The ops tool, grype database,
busybox, and inherited sidecar tags have different conventions and are outside
this component mapping.

## Validation and release boundaries

The chart's [PR workflow](https://github.com/kubescape/helm-charts/blob/235e2d89aa46ec01dfdba19f734023f39c2fef8c/.github/workflows/pr-created.yaml)
uses an immutable Helm unittest image. Local rendering and unit tests do not
prove runtime compatibility. The [E2E release workflow](https://github.com/kubescape/helm-charts/blob/235e2d89aa46ec01dfdba19f734023f39c2fef8c/.github/workflows/03-helm-release.yaml)
allows E2E to be disabled; the separate [no-tests release workflow](https://github.com/kubescape/helm-charts/blob/235e2d89aa46ec01dfdba19f734023f39c2fef8c/.github/workflows/04-helm-release-no-tests.yaml)
does not provide an E2E or allowlist gate. Maintainers must evaluate release
readiness and run appropriate checks against the chosen commit.

GitHub documents that pull requests created or updated using `GITHUB_TOKEN`
can produce approval-required workflow runs for `opened`, `synchronize`, and
`reopened` events. Candidate validation before proposing and maintainer approval
of subsequent PR checks serve distinct purposes. See [GitHub's workflow trigger documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).
