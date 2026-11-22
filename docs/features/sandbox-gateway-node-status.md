# Sandbox gateway node status CRD and RBAC

The chart installs a fifth sandbox CRD, `SandboxGatewayNodeStatus`
(`sandboxgatewaynodestatuses.kubescape.io`), next to the four from
`templates/sandbox-policy-crds/`. It is cluster-scoped, has no `spec`, and holds
one object per node, named after the node: whether Envoy and the processor are
up, host counts against the node cap, rejected patterns, counters and the
certificate validity of the node. Its schema is generated in kubescape/storage
(`docs/features/sandbox-policy-api.md`, "Gateway node status").

The same release also carries the `http` section of `SandboxPolicy` and
`ClusterSandboxPolicy`, and the `http` block of `SandboxPolicyNodeStatus`. Chart
1.42.2 is the first version with them. A cluster on an older chart prunes the new
fields on apply, so anything that delivers an `http` section must require
chart 1.42.2 or later.

Like the other four, the CRD carries `helm.sh/resource-policy: keep` and is
rendered whether or not any capability is enabled. Installing it enables nothing.

## Who may write it

`capabilities.sandboxGateway: enable` renders a service account, a cluster role
and a cluster role binding, all named `sandboxGateway.name` (default
`sandbox-gateway`). The role holds exactly two rules:

| Resource | Verbs |
|---|---|
| `sandboxgatewaynodestatuses` | `get`, `create` |
| `sandboxgatewaynodestatuses/status` | `update` |

The writer creates its node's object, then updates the status subresource. It
cannot list, watch, patch or delete, and it holds no other permission through
this role. The capability deploys no workload: the gateway's DaemonSet is added
later and runs under this account.

No other role in the chart names the resource, and none grants a wildcard on the
`kubescape.io` group, with two things to know:

- The opt-in autoupdater (`capabilities.autoUpgrading: enable`) runs under the
  `helm-release-upgrader` cluster role, which grants every verb on every resource
  and so can also write the kind. That is existing behaviour of that component.
- RBAC cannot tell nodes apart. The account can write any node's object, so one
  node controller could overwrite another's status. Narrowing that needs an
  admission policy and is not part of this chart.

## Checking the exclusivity claim

helm-unittest cannot match free text inside a rendered role, so the unit tests
cover the gateway objects exactly (two rules, one subject, names follow
`sandboxGateway.name`) and the claim above is checked on a full render. Render
with everything that adds roles turned on, then list every `Role` and
`ClusterRole` rule that names `sandboxgatewaynodestatuses` or grants `*` on
`kubescape.io`; only `sandbox-gateway` should appear (plus
`helm-release-upgrader` when the autoupdater is on).

## Updating the CRD

Do not edit the files under `templates/sandbox-policy-crds/` by hand; see the
README in that directory.
