# Live Helm gVisor stop and health validation, 13 November 2026

This follows the [6 November trial](../gvisor-helm-20261106/README.md), which used
node-agent `v0.3.310` and so could not check health reports
([node-agent #1072](https://github.com/kubescape/node-agent/pull/1072)) or stop
observations ([node-agent #1094](https://github.com/kubescape/node-agent/pull/1094),
wired in by [chart #1026](https://github.com/kubescape/helm-charts/pull/1026)).
The chart at `1973c35` (1.42.1) was installed through a real Helm upgrade on the
same Linux ARM64 K3s VM, with the published `quay.io/kubescape/node-agent:v0.3.325`
image, which contains both. The generated ConfigMap and socket mount drove that
image directly; no rebuilt binary or post-install patch enabled the source.

## Result

Phase A ran with `stopObservations: true`.

| Workload | CRI exit | Start exported | Stop exported |
|---|---:|---:|---|
| Normal exit with a child | 7 | 1 | 1, `exited`, code 7 |
| Immediate exit | 5 | 1 | 1, `exited`, code 5 |
| `crictl stop` (SIGTERM, no handler) | 143 | 1 | 1, `signaled`, code 143, signal 15 |
| SIGKILL | 137 | 1 | 1, `signaled`, code 137, signal 9 |
| `kubectl exec` session exits 4, then SIGKILL | 137 | 1 | 1, code 137; none for the exec exit |
| Two overlapping workloads | 21, 22 | 2 | 2, codes 21 and 22 |
| Excluded namespace (gVisor) | 5 | 0 | 0 |
| Ordinary runtime | 6 | 0 | 0 |

Every start and stop matched the independently read container ID, sandbox ID,
Pod UID, name, namespace and node. Each traced container produced exactly one
start and one stop, and each stop's `exit_code`, `signal` and `termination`
matched CRI. The container was still RUNNING after the exec session exited,
and that exit produced no stop.

Phase B upgraded the same release with
`nodeAgent.gVisorStart.stopObservations=false`. The regenerated config kept
`gVisorStart` but no longer contained `stopObservations`. A new gVisor workload
(exit 9) was exported as a start and produced no stop.

## Health reports

The collector received five `RuntimeSourceHealth` reports, each with all 30
counters plus `active_connections` and no other attributes: three periodic reports while phase A ran,
the final `stopped` report the phase A node-agent submitted when the phase B
upgrade restarted it, and one periodic report from the phase B instance.

The final phase A snapshot:

| Counter | Value | Counter | Value |
|---|---:|---|---:|
| `verified_starts` | 7 | `verified_stops` | 7 |
| `callbacks_completed` | 7 | `stop_callbacks_completed` | 7 |
| `export_submitted` | 7 | `stop_export_submitted` | 7 |
| `queue_drops`, `canceled_starts`, `recheck_rejected` | 0 | `stop_queue_drops`, `canceled_stops`, `stop_recheck_rejected` | 0 |
| `duplicate_terminals` | 7 | `unobserved_terminations` | 0 |
| `nonterminal_exits` | 14 | `stop_key_missing`, `stop_tracking_overflow` | 0 |
| `accepted_connections`, `closed_connections`, `handshakes` | 9 | `unresolved_starts`, `ignored_frames` | 9 |
| `received_frames` | 44 | errors, rejections, listener failures, sender drops | 0 |

All four documented equations hold (`verified_starts` = drops + canceled +
callbacks, callbacks = rejected + submitted, and the same two for stops).
The nine connections are the readiness handshake plus eight gVisor sandboxes
(seven traced and the excluded one). The nine unresolved starts are the eight
pause containers plus the excluded workload. `duplicate_terminals` is 7
because each stop's second exit point was counted, not exported again. The
phase B report had its stop counters at zero. These numbers describe this run,
not an end-to-end delivery guarantee.

See [verification](evidence/verification.json), the
[runtime ledger](evidence/runtime-ledger.json), the
[collected records](evidence/observations.jsonl),
[deployment metadata](evidence/environment.json), the
[phase B toggle](evidence/stops-disabled.json) and
[restoration](evidence/restoration.json). Hashes are in
[evidence-sha256.json](evidence-sha256.json).

## Environment

- Ubuntu ARM64, kernel 6.8.0-147-generic, K3s v1.37.1+k3s1.
- runsc release-20261019.0 with systrap, K3s handler `runsc` and RuntimeClass
  `gvisor`. The runsc `Default` session selected `container/start`,
  `sentry/task_exit` and `sentry/exit_notify_parent`, each with `time`,
  `thread_id`, `group_id`, `thread_group_start_time` and `container_id`.
- `quay.io/kubescape/node-agent:v0.3.325`, resolved to
  `sha256:f86ebdbbd92ff7e75fe92e08701a9eceed3ca6ea8e595752c320f4fa9f0cece7`, and
  storage `v0.0.382` from the same chart.
- BusyBox pinned by digest. The mounted directory was root-owned 0700 and the
  socket 0600.
- This chart version enables NetworkPolicies by default. On this node only
  storage was selected, and node-agent's OTLP export to the VM-local collector
  worked without extra policy.

## Privacy and the collector

Every workload has `GVS_HELM_STOP_CANARY_2026` in argv and cwd, and the exec
session has it in argv. The collector in
[`scripts/gvisor-live/otlp-capture`](../../../scripts/gvisor-live/otlp-capture)
extends node-agent's earlier experiment collector: it checks the whole incoming
OTLP request for the canary before filtering, then keeps only fixed allowlists.
These cover the start and stop observation fields, and the source, state and
31 numeric fields of health reports. Every retained record has
`wire_canary_found=false` and `unexpected_attribute_count=0`. Node-agent logs
from both phases were scanned in memory and contained no literal marker. They
were not retained. This does not detect every encoding of sensitive data.

## Reproduce on a disposable prepared node

Save the current Helm revision, runtime file and kubescape resource specs
privately first.

1. Prepare the host as in the [feature doc](../../features/gvisor-start-source.md),
   including the stop trace points and context fields, with the sink at
   `/run/kubescape/gvisor/events.sock`.
2. Build the collector inside a node-agent checkout, which provides its OTLP and
   gRPC modules: copy `scripts/gvisor-live/otlp-capture` under the module root
   and `go build` it for the node. Run it on a trusted VM-local address with a
   new output file.
3. Apply `scripts/gvisor-live/ig-configmap.yaml`, label the node
   `kubescape.io/gvisor-start-ready=true`, and install with
   `scripts/gvisor-live/stop-values.yaml` after replacing the collector address.
4. As root on the node, run
   `python3 scripts/gvisor-live/stop_trial.py --output NEW_DIRECTORY
   --observations COLLECTOR_JSONL --chart charts/kubescape-operator
   --values scripts/gvisor-live/stop-values.yaml`. It runs phase A, upgrades for
   phase B, and writes `verification.json` only when every check passes.
5. Roll Helm back to the saved revision, delete the trial namespaces, the IG
   ConfigMap and the node label, stop the collector, and restore the runtime
   file.

Unit tests for the verifier: `python3 -m unittest discover -s scripts/gvisor-live`.
Collector tests run with `go test` in the same node-agent checkout.

After this run the release was rolled back to its earlier revision, and the
deployments matched their saved specs. The node-agent DaemonSet and ConfigMap
did not match the saved specs, because those carried manual leftovers from an
earlier trial: a volume that referenced a ConfigMap that no longer existed, and
two hand-edited config values. Restoring the volume would have left node-agent
unable to start, so the clean revision was kept and the saved specs were kept
on the VM.

## Scope

This is one live self-managed ARM64 installation with most capabilities
disabled for isolation. It is not an upgrade matrix, a GKE Autopilot
validation, an overhead benchmark or proof of complete delivery. Loss cases
(Sentry failure, node-agent restart while sandboxes are running) are covered by
[node-agent #1091](https://github.com/kubescape/node-agent/pull/1091), not
repeated here.
