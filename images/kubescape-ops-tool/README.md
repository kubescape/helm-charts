# kubescape-ops-tool

A single static Go binary that replaces the shell/`kubectl`/`jq`/`openssl`/`helm`
tooling the `kubescape-operator` chart used to run from init containers and cronjobs.
It ships in a distroless image with no shell, so every operation is a typed API call.

```
kubescape-ops-tool <subcommand> [flags]
```

## Subcommands

### `certgen-create`

Reuses an existing TLS secret or generates a P-256 ECDSA CA plus a leaf certificate,
writes the leaf cert/key into `--out-dir`, and persists all three to a new secret.
Replaces `charts/kubescape-operator/scripts/certgen-create.sh` with the same flags.

| Flag | Default | Meaning |
|---|---|---|
| `-n`, `--namespace` | — | Namespace for the secret (required) |
| `-s`, `--secret-name` | — | Secret to read/create (required) |
| `-H`, `--host` | — | Comma-separated DNS SANs for the leaf (required) |
| `-o`, `--out-dir` | — | Directory to write the leaf cert/key into (required) |
| `--ca-name` | `ca` | Secret key for the CA cert |
| `--cert-name` | `cert` | Secret key for the leaf cert |
| `--key-name` | `key` | Secret key for the leaf key |
| `--days` | `36500` | Validity in days |

### `certgen-patch`

Reads the CA from the secret and patches its base64 `caBundle` into an `APIService`
(merge patch on `spec`) or a `ValidatingWebhookConfiguration` (JSON patch on
`/webhooks/0/clientConfig/caBundle`), retrying while the target is not yet ready.
Replaces `charts/kubescape-operator/scripts/certgen-patch.sh` with the same flags.

| Flag | Default | Meaning |
|---|---|---|
| `-n`, `--namespace` | — | Namespace of the secret (required) |
| `-s`, `--secret-name` | — | Secret holding the CA (required) |
| `-c`, `--ca-name` | `ca` | Secret key holding the CA cert |
| `-t`, `--resource-type` | — | `apiservice` or `vwc` (required) |
| `-r`, `--resource-name` | — | Name of the resource to patch (required) |
| `--retries` | `60` | Max patch attempts |
| `--retry-interval` | `5` | Seconds between attempts |

Both certgen subcommands log the certificate's subject, DNS SANs, and `NotAfter` at
info level, since the image has no shell for `openssl x509 -text`.

### `rollout-restart`

Equivalent to `kubectl rollout restart deployment/<name>`: patches the pod template
with a `kubectl.kubernetes.io/restartedAt` annotation.

| Flag | Meaning |
|---|---|
| `-n`, `--namespace` | Namespace of the deployment (required) |
| `-d`, `--deployment` | Deployment to restart (required) |

### `helm-upgrade`

Upgrades a Helm release through the Helm Go SDK — no `helm` binary. Nothing is
hardcoded: every value comes from a flag or its environment variable, and the
upgrade reuses the release's existing values so an unattended run cannot reset a
user's configuration to chart defaults.

| Flag | Environment variable | Meaning |
|---|---|---|
| `--release` | `KUBESCAPE_OPS_RELEASE` | Release name (required) |
| `-n`, `--namespace` | `KUBESCAPE_OPS_NAMESPACE` | Release namespace (required) |
| `--chart-repo` | `KUBESCAPE_OPS_CHART_REPO` | Local repo name (required) |
| `--chart-repo-url` | `KUBESCAPE_OPS_CHART_REPO_URL` | Repo index URL (required) |
| `--chart-name` | `KUBESCAPE_OPS_CHART_NAME` | Chart name in the repo (required) |
| `--version` | `KUBESCAPE_OPS_CHART_VERSION` | Chart version, empty means latest |
| `--timeout` | — | Upgrade timeout (default `10m`) |

`--chart-repo` is only the local alias; the SDK resolves the index from
`--chart-repo-url`. `HELM_CACHE_HOME` / `HELM_CONFIG_HOME` / `HELM_DATA_HOME` are
honoured and must be writable.

## Development

```bash
go build ./...
go vet ./...
go test ./... -race
```

`internal/helmupgrade` deliberately imports nothing from `internal/certgen` or
`internal/rollout`, and the Helm SDK's dependency tree stays out of those packages,
so splitting it into its own binary/image later stays mechanical.
