# Experimental gVisor start collection

This chart path deploys the experimental node-agent SecCheck `container/start`
receiver on explicitly selected, prepared self-managed Linux nodes. It requires
an image containing [node-agent #1069](https://github.com/kubescape/node-agent/pull/1069).
The chart's current default image, `v0.3.308`, predates that integration. Override
`nodeAgent.image.repository` and `nodeAgent.image.tag` with a compatible image
you have built or verified. Enabling this with an older image does not establish
collection.

[Node-agent #1072](https://github.com/kubescape/node-agent/pull/1072) adds health
reporting and local loss accounting. Those reports require an image containing
that change as well; the chart wiring itself uses the configuration from #1069.

This feature is disabled by default. It does not deploy runsc, configure
containerd, claim a trace session, or provide managed GKE support. The supported
chart path is a single node-agent DaemonSet, without the autoscaler, multiple
DaemonSets or test multiplication. Existing node-agent capabilities determine
whether node-agent is deployed; this switch alone does not enable it.

[Node-agent #1094](https://github.com/kubescape/node-agent/pull/1094) adds
optional stop observations. They are off by default; see
[Stop observations](#stop-observations) before enabling them.

## Prepare the selected nodes

Use an isolated test node with a working Linux/containerd/runsc installation
and a known Kubernetes RuntimeClass. Keep the runsc/containerd versions pinned
in your trial record. The existing Linux ARM64 integration trial is documented
in [node-agent's report](https://github.com/kubescape/node-agent/tree/main/docs/experiments/gvisor-start-integration-20261102).
It is evidence for the source, not validation of this chart deployment.

Before installing, run on every selected host:

```sh
sudo install -d -o root -g root -m 0700 /run/kubescape/gvisor
sudo stat -c '%U %G %a %n' /run/kubescape/gvisor
```

The node-agent container already runs as UID 0. The socket directory must belong
to that UID and have no group/other permissions. The chart mounts it with
`hostPath.type: Directory`, so kubelet will not create a permissive directory
when preparation is missing. The receiver also checks ownership and permissions.
It creates `events.sock` with mode 0600 and never replaces an existing path.

The example directory is under `/run` and must be prepared again after a host
reboot, for example through administrator-managed tmpfiles configuration.
Do not mount it into application Pods. Changing `socketDirectory` requires
changing the host preparation and runsc endpoint to the same absolute pathname.
The dedicated volume adds no runtime control-root mount or new RBAC rules.
The chart's existing broader node-agent host mounts remain in place.

Configure the host's runsc `Default` trace session **before** starting test
workloads. Follow the [node-agent trace setup](https://github.com/kubescape/node-agent/blob/main/docs/gvisor-start-probe.md)
for the pinned runsc build. Its remote sink endpoint for the default example is:

```json
{
  "trace_session": {
    "name": "Default",
    "points": [{"name": "container/start"}],
    "sinks": [{
      "name": "remote",
      "config": {"endpoint": "/run/kubescape/gvisor/events.sock"}
    }]
  }
}
```

Enable no optional fields. The start point still sends argv/cwd to the receiver;
node-agent discards them before queueing or export. Never retain raw sink output.
Do not overwrite another monitor's existing `Default` session. Attaching the sink
to an already running sandbox, or automatic sender reconnection, is not provided
by Helm. Follow the pinned runsc setup instructions for the actual trace command.

Label only hosts where preparation has been checked:

```sh
kubectl label node YOUR_TEST_NODE kubescape.io/gvisor-start-ready=true
```

## Install

Start from [the example values](../../examples/gvisor-start-values.yaml). Replace
its image placeholders, cluster name, OTLP collector endpoint and CRI path.
The K3s example uses `/run/k3s/containerd/containerd.sock`; standard containerd
usually uses `/run/containerd/containerd.sock`. Empty `runtimeEndpoint` reuses
node-agent's detected socket. A custom endpoint must already be reachable through
node-agent's mounts; the feature does not mount arbitrary CRI paths for you.

`configurations.otelUrl` is required by this chart path. It uses the existing
OTLP environment configuration, including OTLP gRPC log export (normally port 4317). A metrics-only collector
or stdout alert exporter is insufficient. The collector must accept OTLP gRPC logs;
existing network policies and any external policies must permit the endpoint.
A configured URL does not prove that the collector is reachable.

```sh
helm dependency build charts/kubescape-operator
helm upgrade --install kubescape charts/kubescape-operator \
  --namespace kubescape --create-namespace \
  -f examples/gvisor-start-values.yaml
```

Enabling requires `nodeAgent.nodeSelector` to include `kubernetes.io/os: linux`
and at least one additional label selecting prepared hosts. This selector also
limits the ordinary node-agent to those hosts. Use this configuration in a
dedicated test installation; it is not a second agent to install alongside an
existing node-agent on the same nodes. Do not duplicate the generated
`gvisor-start` volume/mount or override `gVisorStart` through `config.extra`.

## Validate before marking the deployment ready

1. Check the rendered ConfigMap contains the intended `gVisorStart` object and
   that the DaemonSet has the matching host directory, writable mount and selector.
   Confirm the deployed image contains the integration, not just the expected tag.
2. Check the host directory's owner/mode and the mounted CRI endpoint. Wait for
   node-agent to initialize its OTLP log provider and bind the socket. A ready
   Kubernetes Pod alone does not prove this optional source is ready.
3. Use the bounded version-1 seqpacket readiness handshake from the
   [trial procedure](https://github.com/kubescape/node-agent/blob/main/docs/gvisor-start-probe.md).
   The sink, readiness client and receiver must all use the identical socket path.
4. Start fresh runsc application containers. Match exported `RuntimeObservation`
   records to exact CRI IDs and live Pod UIDs. Repeat starts, include two
   concurrent workloads and ordinary-runtime/excluded-namespace controls, and
   check a synthetic argv/cwd marker is absent from retained OTLP evidence.
5. If using an image containing #1072, inspect `RuntimeSourceHealth` reports for
   rejection/drop/retry counts. Neither submission nor a connected state proves
   delivery completeness. A disconnected socket is not a container stop.

The [6 November ARM64 trial](../experiments/gvisor-helm-20261106/README.md)
records these checks for one self-managed K3s setup. Broader environment
validation remains pending. Helm render,
unit and lint checks do not establish successful runsc/CRI/OTLP collection.
There is no actor/session attribution, behavioral enforcement or egress
collection added here. The earlier missing-start investigation remains unresolved.

## Stop observations

Set `nodeAgent.gVisorStart.stopObservations: true` to also export container
stops. It requires `enabled: true` and an image containing node-agent #1094; an
older image ignores the setting. The chart only adds `"stopObservations": true`
to the generated `gVisorStart` config. It adds no volume, mount, RBAC or trace
configuration.

The node's runsc trace session must then select the two exit points as well,
and every point must carry the context fields node-agent matches on:

```json
{
  "trace_session": {
    "name": "Default",
    "points": [
      {"name": "container/start",
       "context_fields": ["time", "thread_id", "group_id", "thread_group_start_time", "container_id"]},
      {"name": "sentry/task_exit",
       "context_fields": ["time", "thread_id", "group_id", "thread_group_start_time", "container_id"]},
      {"name": "sentry/exit_notify_parent",
       "context_fields": ["time", "thread_id", "group_id", "thread_group_start_time", "container_id"]}
    ],
    "sinks": [{
      "name": "remote",
      "config": {"endpoint": "/run/kubescape/gvisor/events.sock"}
    }]
  }
}
```

If `container/start` lacks these fields, starts are still exported, but the
health report counts them in `stop_key_missing` and no stop can be matched for
them. If only the exit points lack them, starts look normal and
`stop_key_missing` stays zero, but no exit matches its start: those exits are
counted in `nonterminal_exits` and no stop is reported. Configure all three
points the same way. Exported stops are
`RuntimeObservation` records with `kind=container_stopped`, `exit_code`,
`signal` and `termination`. The matching rule and loss behavior are in
[node-agent's feature doc](https://github.com/kubescape/node-agent/blob/main/docs/features/gvisor-start-source.md#stop-observations-opt-in).

This source does not cover every termination. When the Sentry process dies, or
node-agent restarts, existing sandboxes do not reconnect and their stops are not
reported. When a trace connection closes while node-agent keeps running, the
containers it was tracking are counted in `unobserved_terminations`. That count
lives in memory: after an abrupt node-agent restart it may never reach a health
report, and the new process starts again from zero, so the counter does not
account for every missed stop. Use CRI for an authoritative container state. When validating, compare exported stops with CRI
exit codes, and check that `kubectl exec` and child-process exits produce no
stop. The stop path has unit and socket tests in node-agent and the live mapping
evidence in [node-agent #1091](https://github.com/kubescape/node-agent/pull/1091);
it has not yet been validated through a live Helm installation.

## Disable and clean up

Set `nodeAgent.gVisorStart.enabled: false` and apply the values again. This omits
the generated config, directory volume and mount. Remove the prepared-node label
only when it is no longer needed by the installation's node selector. Remove any
experiment-owned trace session/configuration separately, following runsc's
instructions, and verify that no sender or receiver uses the socket before
removing an abandoned socket or directory. The chart does not delete host paths
or trace sessions, including during uninstall.

## GKE allowlist status

This path is for self-managed test nodes. An enabled render requires both the
`gvisor-start` hostPath volume and its `/run/kubescape/gvisor` writable mount;
neither is present in the vendored `armo-kubescape-node-agent-1.40-v2` allowlist.
Enabling on GKE Autopilot needs a separately reviewed allowlist update and live
validation. The ordinary drift workflow renders this feature disabled, so a
passing default check would not establish approval of the optional mount.

The existing proxy environment and API-token mount gaps also reproduce on
upstream main. Maintainers must coordinate any approved allowlist change and
acknowledgement through the repository's documented process.
