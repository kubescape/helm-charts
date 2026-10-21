# Live namespace-filter validation

The chart's render tests establish wiring and Pod-template stability. The live
harness exercises production Operator, Synchronizer and Kubescape images in a
dedicated Kind cluster. It records behavior at HTTP and WebSocket boundaries;
readiness and reload logs alone are not success criteria.

## Running the checks

Prerequisites: Python 3 with PyYAML, Helm, kubectl, Kind, Podman and OpenSSL. Use
Helm unittest v1.2.1, verified with its official release checksum, before this
integration check (`helm-unittest-linux-amd64-1.2.1.tgz` and
`helm-unittest-checksum.sha`).

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/namespace-filters-live/run.py
```

The script creates a uniquely named `ks664-live-*` cluster, explicitly selects a
separate kubeconfig for every command, retains evidence under `/tmp`, and removes
only its own cluster on completion. It never targets the current kubeconfig.
Use `--keep-cluster` when running the independent file-consumer startup check:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/namespace-filters-live/run.py \
  --cluster ks664-live-review --output /tmp/ks664-live-review --keep-cluster

PYTHONDONTWRITEBYTECODE=1 python3 scripts/namespace-filters-live/startup.py \
  --kubeconfig /tmp/ks664-live-review/kubeconfig \
  --output /tmp/ks664-startup-review

KIND_EXPERIMENTAL_PROVIDER=podman kind delete cluster --name ks664-live-review
```

`run.py` exits nonzero if any criterion fails **or remains unverified**. Inspect
`results.json` to distinguish a source assertion failure from an environmental
limit. `--convergence` defaults to 180 seconds and `--observation` to 30 seconds;
initial image pulls have a separate 600-second readiness allowance. A complete
matrix takes several minutes because every phase has behavioral observation
windows. `--existing-kubeconfig` accepts only an explicitly matching dedicated
`kind-ks664-live-*` context; an externally supplied cluster is never deleted by
the script.

## What the harness observes

- A local TLS discovery/WebSocket fixture receives Synchronizer's actual outgoing
  protocol envelopes for uniquely named Services in two namespaces. Allowed
  events must arrive; excluded events are checked throughout the phase, including
  delayed events for earlier phase markers.
- Production Operator dispatch is intercepted at a local HTTP recorder by a
  test-only Helm post-renderer. It changes only the Kubevuln destination in the
  shared startup configuration. New workloads must produce scan dispatches for
  allowed namespaces and none for excluded namespaces. This proves selection and
  outbound dispatch, not a completed Kubevuln vulnerability scan.
- Production Kubescape receives HTTP scan requests without request-level namespace
  overrides. Actual JSON resources and Prometheus namespace labels are checked
  repeatedly during the observation window. Offline, image-bundled policies are
  used; results are kept local.
- Inclusion A to B, exclusion A, clearing both lists, malformed JSON, missing
  required keys, malformed regex, valid recovery, and external-map deletion and
  recreation receive behavioral checks.
- Helm upgrades verify preservation of manual edits with unchanged values,
  intentional value changes without pod restarts, and migration to a separately
  named external ConfigMap. API/HTTP consumer pod UIDs and restart counts must
  remain unchanged during live edits. Changing the source reference is an
  intentional rollout and establishes a new baseline.
- API watchers are started against a missing ConfigMap and then invalid initial
  content. The fixture must observe no namespace callbacks or scan dispatches
  while workload probes are created. Publishing a valid document must restore
  allowed behavior. The independent `startup.py` uses the chart's actual
  required projections and production file-consumer images to verify missing
  mounts prevent startup and invalid JSON causes filter-initialization failure.

The fixture uses synthetic credentials only, does not retain request headers,
and discards arbitrary object/patch bodies from recorded Synchronizer envelopes.
Do not substitute real backend credentials. The evidence directory includes a
test-only CA key and isolated kubeconfig; neither belongs in a commit.

## Runtime monitoring boundary

Rootless Podman/Kind on the validation host cannot start the production Node-agent:
kernel validation reports `mounting /sys/fs/bpf: operation not permitted`.
This blocks real eBPF runtime monitoring, exclusion and readmission of running
workloads. Node-agent readiness, live filtering and restart stability are therefore
**unverified**, even when the other consumers pass. A failing runtime process is
excluded from their no-restart assertions.

Before closing issue #664, use an eBPF-capable cluster to demonstrate the default
runtime binding admits a running workload when its namespace becomes included,
removes monitoring on exclusion, and resumes monitoring on readmission without
restarting Node-agent. Record actual runtime events or stored profile transitions
for those workload/container identities. A mounted-file change, successful Helm
render, or `filters updated` log does not satisfy that criterion.

Valid regex fields are outside the shared contract: Operator and Synchronizer
support them, while the file consumers reject them. The malformed-regex case
tests rejection; it does not establish uniform behavior for otherwise valid
regex documents. Use exact namespace arrays in shared ConfigMaps.
