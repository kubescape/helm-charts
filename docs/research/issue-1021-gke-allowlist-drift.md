# Issue #1021: GKE Autopilot allowlist drift

Research date: 2026-11-12. Repository baseline inspected:
`235e2d89aa46ec01dfdba19f734023f39c2fef8c`.

## Findings

The three differences in [issue #1021](https://github.com/kubescape/helm-charts/issues/1021)
have two causes. The SBOM scanner proxy variables are genuinely outside the vendored allowlist.
The API-token mount finding comes from checking a render with Autopilot allowlist mode disabled;
the chart already has a compatibility fallback for the selected allowlist.

| Reported field | Baseline evidence | Interpretation |
| --- | --- | --- |
| `sbom-scanner` env `HTTPS_PROXY`, `no_proxy` | The sidecar template adds both whenever `global.httpsProxy` is nonempty; the sidecar entry in the vendored allowlist contains neither name. | The proxy + SBOM sidecar combination requires a matching approved allowlist or explicit chart validation preventing this combination. |
| `node-agent` mount `/var/run/secrets/kubescape.io/api-token` | `apiauth.enabled` becomes false when `nodeAgent.gke.allowlist.enabled=true` and `supportsApiToken=false`; caller volume/mount rendering is conditional on that effective switch. The drift wrapper never enables the allowlist. | The current drift profile does not exercise the chart's Autopilot compatibility mode. Enable that mode in the checker before treating this as a required workload expansion. |

Sources: baseline [sidecar template](https://github.com/kubescape/helm-charts/blob/235e2d89aa46ec01dfdba19f734023f39c2fef8c/charts/kubescape-operator/templates/node-agent/_node-agent.tpl#L274-L306),
[API-auth helpers](https://github.com/kubescape/helm-charts/blob/235e2d89aa46ec01dfdba19f734023f39c2fef8c/charts/kubescape-operator/templates/_apiauth.tpl),
[allowlist defaults](https://github.com/kubescape/helm-charts/blob/235e2d89aa46ec01dfdba19f734023f39c2fef8c/charts/kubescape-operator/values.yaml#L862-L878),
[drift wrapper](https://github.com/kubescape/helm-charts/blob/235e2d89aa46ec01dfdba19f734023f39c2fef8c/scripts/gke-allowlist/check-drift.sh),
and [vendored allowlist](https://github.com/kubescape/helm-charts/blob/235e2d89aa46ec01dfdba19f734023f39c2fef8c/gke-allowlist/armo-kubescape-node-agent-1.40-v2.yaml#L35-L59).

## Google admission rules

Google's CRD reference specifies environment matching by name; other env fields are ignored.
Every workload volume must have a corresponding allowlist entry, and volume mount fields must
match. The same reference explains subset matching for capabilities. These rules support treating
the additional proxy variable names and token mount as admission-relevant differences, rather than
as harmless YAML differences. [Google WorkloadAllowlist CRD reference](https://docs.cloud.google.com/kubernetes-engine/docs/reference/crds/workloadallowlist)

Google's troubleshooting guide shows Warden rejecting unmatched environment names, volumes and
mounts. Adding `cloud.google.com/matching-allowlist` with the installed allowlist's exact resource
name produces detailed mismatch diagnostics. A third-party workload owner is responsible for
resolving its workload/allowlist incompatibilities. [Google privileged workload troubleshooting](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/autopilot-privileged-workloads)

An AllowlistSynchronizer installs allowlists from approved paths. Google recommends waiting for
its `Ready` condition and verifying the WorkloadAllowlist exists before deploying the workload;
creating the synchronizer alone does not prove that a new allowlist is available. [Google allowlist installation guide](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/run-autopilot-partner-workloads)

## Approval and version evidence

The checked-in default is `armo-kubescape-node-agent-1.40-v2`, and the repository describes its
vendored YAML as the approved copy used by CI. The YAML's SBOM scanner env list lacks the proxy
names, and the node-agent mount/volume lists lack the projected API token. This establishes the
local comparison input, not the current state of Google's publication pipeline. [Baseline tooling guide](https://github.com/kubescape/helm-charts/blob/235e2d89aa46ec01dfdba19f734023f39c2fef8c/docs/features/gke-autopilot-allowlist-tooling.md)

The current Kubescape installation guide illustrates `1.40-v2`, describes allowlist naming per
chart minor, and says that the matching minor must already be approved and published by Google.
It tells operators to use the exact name installed in their cluster. Its `1.41` naming example
and the chart comments anticipating `1.43` are not evidence that either revision admits these
additional fields. [Kubescape GKE Autopilot guide](https://kubescape.io/docs/integrations/kubescape-integration-with-cloud-providers/running-armokubescape-node-agents-on-gke-autopilot-clusters/)

Attempts to inspect the owning [ARMO allowlist repository](https://gke-ap-allowlist.googlesource.com/ARMO)
and its [Gerrit project](https://gke-ap-allowlist-review.googlesource.com/q/project:ARMO) were
unsuccessful: the web retrieval tool could not access either endpoint, and local `curl` failed
DNS resolution for `gke-ap-allowlist.googlesource.com`. Searches for a public `v3` or `1.43`
allowlist did not produce approval evidence. **No newer approved version or rollout status was
verified.** This is an access/evidence limitation, not a claim that no newer allowlist exists.

## Recommended repository-only fix

1. Render the drift profiles with `nodeAgent.gke.allowlist.enabled=true`, retaining the existing
   `supportsApiToken=false` fallback for the vendored allowlist.
2. Explicitly reject Autopilot allowlist mode + SBOM scanner + nonempty HTTPS proxy while the
   selected allowlist lacks the scanner proxy fields. Do not silently drop proxy variables: that
   changes the user's requested egress behavior. Keep ordinary, non-Autopilot proxy rendering.
3. If adding an opt-in such as `supportsSbomScannerProxy`, default it to false and describe it as
   an assertion about the exact approved allowlist selected by `name`. Do not assign it a guessed
   version threshold. Selecting the flag alone does not approve a workload.
4. Check both maximal supported profiles: proxy enabled with the scanner disabled, and scanner
   enabled without proxy. Future opt-ins for proxy/scanner or API-token support must still expose
   their new fields to comparison with the supplied allowlist, so an old file fails the check.
5. Leave the vendored allowlist and default name unchanged until a maintainer supplies the actual
   approved artifact and publication evidence. Follow the existing Gerrit process to expand
   support, then vendor that artifact and update the capability flags/name together.

These recommendations are inferences from the baseline templates and Google's admission rules.
The existing [allowlist runbook](https://github.com/kubescape/helm-charts/blob/235e2d89aa46ec01dfdba19f734023f39c2fef8c/scripts/gke-allowlist/README.md)
requires a new allowlist revision for spec drift. Editing the vendored file locally would only
change CI's comparison input; it would not publish the corresponding allowlist to GKE.

## Validation boundaries

Focused regression coverage should verify the API-auth fallback, allowed proxy-only and
scanner-only profiles, explicit rejection of the unsupported combination, and drift with old
allowlists when future support flags enable the extra fields. The drift detector projects a
limited set of fields and forces the fixed DaemonSet render; its passing result cannot establish
complete admission equivalence for autoscaler-created Pods or cluster-time mutations.
[Baseline drift detector](https://github.com/kubescape/helm-charts/blob/235e2d89aa46ec01dfdba19f734023f39c2fef8c/scripts/gke-allowlist/allowlist-drift.py)

No live GKE Autopilot admission test was performed during this research. Final cluster validation
should record the installed allowlist name/content, synchronizer readiness and any Warden
mismatch diagnostics for both supported profiles.

## Implementation verification (2026-11-12)

The repository fix preserves the vendored allowlist and its default name. It enables allowlist
mode in the drift wrapper, checks the proxy/in-process and no-proxy/sidecar profiles, and rejects
the unsupported combination unless the operator explicitly declares a matching approved allowlist.

| Boundary | Evidence |
| --- | --- |
| Baseline gate → generic render | Exit 2 with the three differences reported in #1021. |
| Fixed gate → Autopilot render → vendored allowlist | Both supported profiles return `CLASS: no-op`; aggregate exit 0. |
| Invalid configuration → chart validation | Rendering sidecar plus proxy with the legacy capability flag fails in fixed, multiple-DaemonSet and autoscaler paths. |
| Capability overrides → comparison | Setting token/proxy support flags while comparing with the legacy file still returns spec drift for the added fields. |
| Regression/error handling | 10 Python integration tests pass, including wrapper charts, missing proxy approval and malformed allowlists. |
| Existing chart behavior | Helm lint passes; the pinned CI renderer passes 46 suites, 400 tests and 1,202 snapshots without regeneration. |
| Workflow and shell | Actionlint v1.7.12 and `bash -n` pass. |

Tests ran with Helm v3.19.0 and PyYAML 6.0.3. The Context7 Helm documentation lookup failed
with a DNS-resolution error; the primary Google and repository sources above were used.
Only local Kubernetes contexts were available; no live Autopilot admission or Google allowlist
publication was performed. Hosted PR checks are separate evidence once the change is pushed.
