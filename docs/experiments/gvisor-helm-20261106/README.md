# Live Helm gVisor start validation, 6 November 2026

This follows [chart #994](https://github.com/kubescape/helm-charts/pull/994).
The chart at `5709eea4` was installed through a real Helm upgrade in the dedicated
Linux ARM64 K3s VM. The generated ConfigMap and socket mount drove the published
node-agent image directly; no rebuilt binary or post-install DaemonSet/config
patch enabled the source.

| Case | Expected | Observed |
|---|---:|---:|
| Repeated application starts | 20 | 20 |
| Two overlapping gVisor workloads | 2 | 2 |
| Excluded namespace | 0 exports | 0 |
| Ordinary runtime | 0 exports | 0 |
| Synthetic unknown container ID | 0 exports | 0 |
| Disable with another Helm upgrade | Config and socket volume/mount omitted | Verified |

All 24 actual workloads completed successfully. Each of the 22 exports matched
the independently read full container ID, sandbox ID, Pod UID/name/namespace,
node and container name. The two parallel execution intervals overlap. No
observation reported sender loss. These counts describe this run, not an
end-to-end delivery guarantee or an explanation of the historical missing start.

The [verification](evidence/verification.json), [ledger](evidence/runtime-ledger.json),
[observations](evidence/observations.jsonl), [deployment metadata](evidence/environment.json)
and [disabled state](evidence/disabled.json) are retained. Hashes are in
[evidence-sha256.json](evidence-sha256.json). The actual mounted directory was
root-owned 0700 and the socket was 0600. Its generated path matched the runsc
sink pathname.

## Environment and prerequisites

- Ubuntu ARM64, kernel 6.8.0-147-generic, K3s v1.37.1+k3s1.
- runsc release-20261019.0, systrap, using the existing K3s handler `runsc` and
  RuntimeClass `gvisor`. Runtime binary SHA-256 is retained.
- `quay.io/kubescape/node-agent:v0.3.310`, resolved by the runtime to
  `sha256:99152dbefd07e524418f682882ad300cb74821aaa4e42e6477c42a9fa4686e60`.
  Its source tag contains the start integration from node-agent #1069. It
  predates the health follow-up #1072; this run does not validate those reports.
- Storage v0.0.382, deployed by the same chart. Both storage and node-agent
  became Ready. The older storage root/command workaround was not used here.
- BusyBox pinned by digest in the fixture, with per-workload image IDs retained.
- Existing IG K3s socket configuration was supplied through an explicit
  ConfigMap volume in the trial values. No new application socket mount or
  runsc control-root permission was added.

An initial attempt with storage disabled left node-agent waiting for the
storage API, without binding the receiver socket. Enabling the chart's storage
backend resolved readiness. The final values keep storage enabled and disable
profile learning/host sensing so this trial measures source/export behavior.
A metrics push to the log-only capture endpoint was also rejected; the final
values use the existing Prometheus metrics mode. Neither initial attempt is
counted as a successful source trial.

## Privacy and observation contract

The fixture deliberately includes `GVS_INTEGRATION_CANARY_2026` in argv and cwd.
The existing [OTLP capture utility](https://github.com/kubescape/node-agent/tree/44eb1e4e01678be35196c124419161df221f4ab5/docs/experiments/gvisor-start-integration-20261102/otlp-capture)
checks its complete protobuf request for that literal marker before retaining
only the observation allowlist. Its executable hash is recorded. Each retained
export has `wire_canary_found=false` and `unexpected_attribute_count=0`.
The pre-disable node-agent logs were read into memory and scanned without
retaining raw output. No literal marker was found. This does not detect every
possible encoding or arbitrary credential.

Records remain `RuntimeObservation`, `source=gvisor_trace`,
`kind=container_started`, with inventory-verified metadata. They do not attest
to the sender, application execution, actor/session identity or enforcement.

## Reproduce on a disposable prepared node

Preserve the current Helm revision, runtime file and actual Kubernetes resource
specs privately before changing them. The fixture uses fixed namespaces and
refuses to overwrite evidence; archive/delete only owned trial resources before
a repeat. Do not copy kubeconfig, service-account tokens or raw OCI specs into
the report.

1. Follow the [host and trace setup](../../features/gvisor-start-source.md),
   using `/run/kubescape/gvisor/events.sock`. The receiver directory must exist
   with the tested ownership/mode. Configure `container/start` before fresh
   sandbox startup and do not replace another monitor's Default session.
2. Build the linked capture utility for the node's architecture and run it on a
   trusted VM-local address with a new output file. It is a log-only disposable
   receiver, not a public collector deployment.
3. Apply `scripts/gvisor-live/ig-configmap.yaml`. Start from
   `scripts/gvisor-live/values.yaml`, replacing the VM-local collector address
   and adapting the runtime/image/namespace settings for the prepared test node.
   Label the node `kubescape.io/gvisor-start-ready=true`.
4. Build chart dependencies and run `helm upgrade --install kubescape
   charts/kubescape-operator -n kubescape -f scripts/gvisor-live/values.yaml`.
   Wait for storage and node-agent readiness, then require the fixture's actual
   bounded version-1 socket handshake before workloads.
5. On the VM as root, run `python3 trial.py --output NEW_DIRECTORY
   --observations COLLECTOR_JSONL`, using `scripts/gvisor-live/trial.py`.
   It creates 20 repeated starts, two parallel starts and all three controls,
   checks exact counts/identities and scans the current agent log in memory.
   It writes a verification file only after all checks pass.
6. Upgrade with `--set nodeAgent.gVisorStart.enabled=false`. Inspect the actual
   ConfigMap and DaemonSet for absence of the generated config, socket volume
   and mount. Kubernetes readiness alone is insufficient to establish this.
7. Restore the saved runtime configuration, Helm revision and any previously
   patched resource specs. Remove only the trial namespaces, ConfigMap and
   prepared-node label. Stop the capture process and disposable VM.

The checked-in verifier adds control-ledger completeness checks to the executed
fixture; it was rerun successfully against the retained ledger and exports.
Four unit tests exercise missing/extra/duplicate exports, identity mismatch,
wire privacy/loss failures, missing controls and non-overlapping workloads.

## Scope

This is one live self-managed ARM64 installation, with ordinary capabilities
reduced for isolation. It is not an upgrade matrix, full runtime-security test,
GKE Autopilot validation, overhead benchmark or proof of complete delivery.
The VM's original Helm/resources/runtime configuration was restored afterward.
