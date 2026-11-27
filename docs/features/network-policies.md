# Network policies

> **Warning:** starting with chart **1.43.0**, `global.networkPolicy.enabled` defaults to `true`.
> A plain `helm upgrade` creates NetworkPolicies in the Kubescape namespace. They restrict
> **ingress** to the Kubescape pods to the traffic listed below; egress is unchanged unless you
> also set `global.networkPolicy.createEgressRules=true`. If something outside the chart talks to
> a Kubescape pod directly, allow it with your own NetworkPolicy (policies are additive) or opt
> out with `--set global.networkPolicy.enabled=false`.

The policies only take effect when the cluster's CNI enforces NetworkPolicies (Calico, Cilium,
kube-router as shipped by k3s, Antrea, OVN-Kubernetes, GKE Dataplane V2, AKS/EKS network policy,
and so on). On a CNI that does not enforce them, such as plain flannel, they are no-ops.

## What is allowed in

Every policy selects one component by its `app.kubernetes.io/{name,instance,component}` labels.
Components without an ingress policy (node-agent, the scheduler and auto-updater CronJobs) accept
traffic as before.

| Component | Rendered when | Ingress allowed |
|---|---|---|
| `kubescape` | `capabilities.configurationScan=enable` | from `operator` on `http` (8080); on `http` when `kubescape.serviceMonitor.enabled` or `configurations.prometheusAnnotations=enable` (Prometheus scrape, from anywhere unless narrowed with `kubescape.networkPolicy.prometheusIngressFrom`, see below) |
| `kubevuln` | `capabilities.vulnerabilityScan=enable` | from `operator` on `kubevuln.service.targetPort` (8080) |
| `operator` | `capabilities.operator=enable` | from anywhere on `admission-port` (8443) when `capabilities.admissionController=enable` (narrow with `operator.admissionWebhooks.networkPolicy.ingressFrom`, see below), nothing otherwise |
| `storage` | `storage.enabled` | from anywhere on `storage.serverPort` (8443), the aggregated API called by kube-apiserver |
| `synchronizer` | a backend is configured (`server`) | from `node-agent` and `operator` on `synchronizer.service.targetPort` (8089), their alert exporters |
| `prometheus-exporter` | `capabilities.prometheusExporter=enable` | from anywhere on `prometheusExporter.service.port` (8080) |
| `grype-offline-db` | `grypeOfflineDB.enabled` | from `kubevuln` on 8080 |

Webhook and aggregated-API calls from kube-apiserver are allowed from any source because the
control plane is usually outside the pod network (host network or a managed control plane), where
pod and namespace selectors cannot match it, and its source address varies (a node tunnel address,
a konnectivity agent pod, one of several control-plane ENIs). Kubelet probes are always allowed: Kubernetes
NetworkPolicies do not apply to traffic from the pod's own node.

Kubescape components talk to each other through the Kubernetes API for everything else (scan
results go to `storage` through kube-apiserver, scheduled scans are `OperatorCommand` objects), so
no other pod-to-pod path is needed.

### Restricting admission webhook ingress

The `admission-port` ingress is unrestricted by default for the reason above: the kube-apiserver's
source address is not reliably matchable by a Pod or namespace selector. If you **know** your
control plane's source addresses, you can narrow this one rule with
`operator.admissionWebhooks.networkPolicy.ingressFrom`, a list of standard
[NetworkPolicyPeer](https://kubernetes.io/docs/reference/kubernetes-api/policy-resources/network-policy-v1/#NetworkPolicyPeer)
entries. Leaving it empty (the default) keeps the current from-anywhere behaviour.

```yaml
operator:
  admissionWebhooks:
    networkPolicy:
      ingressFrom:
        - ipBlock:
            cidr: 10.0.0.0/24          # control-plane subnet
        - ipBlock:
            cidr: 192.168.49.2/32      # a single API-server node
        # - namespaceSelector:          # e.g. a konnectivity-agent namespace,
        #     matchLabels:              #   only where the API server reaches
        #       kubernetes.io/metadata.name: kube-system   # pods from in-cluster
```

The chart validates each `ipBlock.cidr` at render time and fails on an invalid value. **IPv4** is
validated in full — every octet must be 0–255 and the prefix 0–32, so `999.0.0.0/24`,
`256.1.1.1/24`, `10.0.0.0/33` and a missing prefix (`10.0.0.0`) are all rejected. **IPv6** (any
value containing `:`) is validated for character set (hex and `:`), prefix (0–128), and — for
IPv4-mapped/embedded forms such as `::ffff:192.0.2.1/128` or `2001:db8::192.0.2.1/128` — the
trailing dotted-decimal tail is octet-validated (0–255) exactly like IPv4, so `::/999`,
`::ffff:999.0.2.1/128` and the truncated `::ffff:192.0.2/128` are rejected while `2001:db8::/64`
and `::ffff:192.0.2.0/120` are accepted. A regex cannot reliably parse the full IPv6 address
structure (zero-compression, group count), so the kube-apiserver remains the final authority on the
IPv6 address itself; this check rejects obvious typos rather than guaranteeing RFC-complete
validity. Selector peers (`namespaceSelector`/`podSelector`) are not CIDR-checked.

**Identify your API server's source address** before restricting. From the operator pod's node,
the apparent source of an incoming webhook call depends on the cluster:

- **kubeadm / k3s / RKE2 (API server on cluster nodes):** usually the node IP or the pod-network
  address of the node running the API server. `kubectl get endpointslice kubernetes -n default -o wide`
  lists the control-plane endpoint IPs.
- **konnectivity / egress-selector clusters:** traffic arrives from the konnectivity-agent pod;
  match its namespace/pod, not an IP.
- **Managed control planes (EKS/GKE/AKS):** the source is one of several control-plane ENIs or a
  tunnel address that can change; these environments generally **require the unrestricted default**.

**Test connectivity after restricting.** Apply the change, then create a Pod and confirm the
webhook still sees it — the operator logs a rule evaluation / admission counter for each request.
Because the `ValidatingWebhookConfiguration` uses `failurePolicy: Ignore`, an over-tight rule does
**not** block your workloads; it silently drops the API server's webhook calls, so verify that
admission telemetry still flows (operator logs, `telemetry` admission counters) rather than relying
on admission being rejected. If telemetry stopped, widen or remove `ingressFrom`.

### Restricting the Prometheus scrape ingress

When `kubescape.serviceMonitor.enabled=true` or `configurations.prometheusAnnotations=enable`,
the kubescape metrics port accepts scrapes from any namespace. If Prometheus runs in a known
namespace, narrow that rule with `kubescape.networkPolicy.prometheusIngressFrom`, a list of
standard
[NetworkPolicyPeer](https://kubernetes.io/docs/reference/kubernetes-api/policy-resources/network-policy-v1/#NetworkPolicyPeer)
entries:

```yaml
kubescape:
  serviceMonitor:
    enabled: true
  networkPolicy:
    prometheusIngressFrom:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: monitoring
```

Leaving it empty (the default) keeps the from-anywhere behaviour. The chart validates each
`ipBlock.cidr` at render time (same rules as admission webhook ingress above). The `operator`
rule that lets Kubescape's own scans reach the metrics port is unaffected.

## Egress rules (opt-in)

`global.networkPolicy.createEgressRules=true` adds `Egress` to every component policy except
grype-offline-db (an nginx that only serves the Grype database baked into its image and makes no
outbound connections), and creates egress-only policies for node-agent, the two scheduler
CronJobs and the auto-updater. Each
component may then reach:

- DNS, UDP and TCP ports 53 and 5353, to any destination (NodeLocal DNSCache and OpenShift DNS do
  not run as `kube-dns` pods in `kube-system`, so a selector would break name resolution there, and
  OpenShift's DNS pods listen on 5353 behind the Service);
- kube-apiserver: port `apiServerPort` plus the ports of the `default/kubernetes` EndpointSlice
  (looked up at install time, for example 6443 on kubeadm and k3s), to `apiServerIP` when it is set
  and to any destination otherwise. Most CNIs check egress after the Service DNAT, so the endpoint
  port is what must be allowed;
- the HTTPS proxy (`httpsProxyIP`/`httpsProxyPort`) when `global.httpsProxy` is set;
- what the component needs on top: port 443 for the backend, registries, the Grype database and
  the chart repository (kubescape, kubevuln, operator, synchronizer, auto-updater), the cloud metadata service (kubescape, operator),
  kubescape, kubevuln and the synchronizer (operator), the synchronizer and the OTLP ports 4317/4318 (node-agent),
  grype-offline-db (kubevuln).

When `helm template` or a GitOps tool renders the chart without cluster access, the lookup returns
nothing; set `apiServerPort` to your API server's endpoint port
(`kubectl get endpointslice kubernetes -n default`) in that case. The identity running Helm needs
`get` on EndpointSlices in the `default` namespace, otherwise the lookup fails the install.

Leave `apiServerIP` empty on Cilium (including GKE Dataplane V2) when kube-apiserver runs on the
cluster's own nodes: Cilium does not match node addresses with `ipBlock`, so pinning the IP would
block egress to the API server.

## Values

| Key | Default | Description |
|---|---|---|
| `global.networkPolicy.enabled` | `true` | Create the ingress NetworkPolicies above |
| `global.networkPolicy.createEgressRules` | `false` | Also restrict egress |
| `global.networkPolicy.apiServerIP` | `""` | Pin the kube-apiserver egress rule to this IP (it no longer restricts storage ingress) |
| `operator.admissionWebhooks.networkPolicy.ingressFrom` | `[]` | NetworkPolicyPeer list that narrows the admission webhook ingress; empty keeps it unrestricted (from anywhere) |
| `kubescape.networkPolicy.prometheusIngressFrom` | `[]` | NetworkPolicyPeer list that narrows the metrics scrape ingress; empty keeps it unrestricted (from anywhere) |
| `global.networkPolicy.apiServerPort` | `443` | kube-apiserver port for the egress rules, merged with the looked-up endpoint ports |
| `global.networkPolicy.httpsProxyIP` | `""` | Pin the proxy egress rule to this IP (optional; destination left open if empty) |
| `global.networkPolicy.httpsProxyPort` | `""` | Proxy port for egress rules; derived from `global.httpsProxy` when unset |

## Troubleshooting

A component that worked before the upgrade and now times out talking to a Kubescape pod is the
symptom of a missing rule. List the policies and check which one selects the target pod:

```sh
kubectl -n kubescape get networkpolicies
kubectl -n kubescape describe networkpolicy <component>
```

Add an extra policy for your client instead of editing the chart's (they are reverted on the next
upgrade), or disable the chart's policies with `global.networkPolicy.enabled=false`.

Scheduled-scan CronJobs created by charts older than 1.42.0 call the operator on port 4002, which
the policy keeps closed. Operator v0.2.197 and later rewrite those schedules into `OperatorCommand`
CronJobs at startup, so this only matters if `operator.image.tag` is pinned to an older operator.
