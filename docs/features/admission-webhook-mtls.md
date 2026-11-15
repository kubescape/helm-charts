# Admission webhook client authentication (opt-in mutual TLS)

The operator's validating admission webhook (`/validate`, port `8443`) serves HTTPS with a
server certificate so the Kubernetes API server can verify the webhook. By default it does
**not** authenticate the *caller*: any client that can reach the port can send an
`AdmissionReview`, and the webhook builds its evaluation attributes from caller-supplied
`UserInfo`, `Object` and `OldObject`.

Because the webhook is **audit-only** — it always responds `Allowed: true` and its
`ValidatingWebhookConfiguration` uses `failurePolicy: Ignore` — this cannot change a Kubernetes
admission decision. The residual concern is the integrity of admission *telemetry* when a real
alert exporter is configured: a reachable, unauthenticated caller could submit fabricated reviews.

This opt-in feature lets you require **mutual TLS** so the webhook accepts a request only from a
peer presenting a client certificate that chains to a CA you configure.

> **This feature is not usable with a released operator image yet.** It requires an operator build
> that reads `ADMISSION_CLIENT_CA_FILE` (kubescape/operator#522), which is not merged or released
> at the time of writing. The chart refuses to render `clientAuth.enabled: true` until you point
> `operator.image.tag` at a compatible build and set `operatorSupportsClientCA: true` (see
> [Compatible operator image requirement](#compatible-operator-image-requirement)).

## Purpose and trust model

- **What is authenticated:** the TLS transport peer. A caller must present a client certificate
  signed by the configured client CA. This is a cryptographic check on the connection, independent
  of the request body.
- **What is *not* trusted as identity:** `UserInfo`, `Object`, `OldObject` and the other
  `AdmissionReview` fields remain untrusted input used only for rule attribution — never as proof
  of who the caller is. Client authentication is the only caller-identity check; the body cannot
  grant it.
- **Scope:** this authenticates the API server to the webhook. It does not change admission
  semantics, rule evaluation, or the `Allowed: true` response.

## Creating the client CA Secret

Provision a CA, issue the API server a client certificate from it (see
[API-server client certificate configuration](#kubernetes-api-server-client-certificate-configuration)),
and create a Secret in the Kubescape namespace holding the **CA certificate** the webhook should
trust:

```bash
kubectl -n kubescape create secret generic apiserver-webhook-client-ca \
  --from-file=ca.crt=/path/to/client-ca.crt
```

The Secret may be `Opaque` or `kubernetes.io/tls`; only the key named by `caKey` (default `ca.crt`)
is read, and it must contain the trusted client-CA bundle.

## Helm values

```yaml
capabilities:
  admissionController: enable
operator:
  image:
    # A build that supports mTLS — NOT a default/released tag (see below).
    tag: <operator-image-that-reads-ADMISSION_CLIENT_CA_FILE>
  admissionWebhooks:
    clientAuth:
      enabled: true
      secretName: apiserver-webhook-client-ca   # the Secret created above
      caKey: ca.crt                             # key within that Secret
      operatorSupportsClientCA: true            # attest the image enforces mTLS
```

| Value | Default | Meaning |
|---|---|---|
| `operator.admissionWebhooks.clientAuth.enabled` | `false` | Turn on mutual TLS for the webhook listener. |
| `operator.admissionWebhooks.clientAuth.secretName` | `""` | Secret holding the trusted client-CA bundle. Required when `enabled`. |
| `operator.admissionWebhooks.clientAuth.caKey` | `ca.crt` | Key within that Secret. |
| `operator.admissionWebhooks.clientAuth.operatorSupportsClientCA` | `false` | Attestation that `operator.image.tag` is a build which enforces client-cert verification. Required when `enabled`. |

When enabled, the chart mounts the CA at `/etc/admission-client-ca/<caKey>` and sets
`ADMISSION_CLIENT_CA_FILE` on the operator. The env var is the only contract, so the mechanism also
works outside Helm.

## Compatible operator image requirement

mTLS has no effect unless the running operator image reads `ADMISSION_CLIENT_CA_FILE` and enforces
client-certificate verification on the webhook listener. An image that ignores the variable would
serve the webhook **unauthenticated** while the chart mounts a CA and sets the env var — a silent,
insecure outcome where you believe authentication is on but it is not.

**Compatibility is asserted by you (the operator), not verified by Helm.** Helm cannot run the image
or inspect an unreleased feature, so it cannot confirm that a given image actually enforces client
authentication. The gate therefore does two things only: it requires your explicit attestation, and
it blocks released versions already *known* to lack the feature. An image you attest as compatible is
trusted on your word.

The chart **refuses to render** `clientAuth.enabled: true` unless **both** hold:

1. `operatorSupportsClientCA: true` — your explicit attestation that the configured image is a
   compatible build.
2. `operator.image.tag` is **not** a released operator version known not to read
   `ADMISSION_CLIENT_CA_FILE`. Every released version **up to and including v0.2.224** is verified to
   lack it, so any **SemVer** tag whose `major.minor.patch` core is at or below that boundary is
   rejected **even when `operatorSupportsClientCA` is `true`**.

   This comparison is on the SemVer **core**, so it includes **prereleases** of incompatible
   versions: `v0.2.224-rc1`, `v0.2.224-beta.1` and `v0.2.223-custom` are all rejected (checked at
   their `0.2.224` / `0.2.223` base), because a prerelease of a version that lacks the feature also
   lacks it. (A dotted-decimal detail: Masterminds `semverCompare` excludes prereleases from a
   non-prerelease constraint such as `<= 0.2.224`, which is why the chart compares the core rather
   than the raw tag.) A prerelease **above** the boundary, such as `v0.2.225-rc1`, is allowed under
   attestation — `0.2.225 > 0.2.224`, so it is not *known* incompatible.

   **Genuine non-SemVer tags** — custom/dev builds from kubescape/operator#522, git SHAs, branch
   names — are not version-checked and are governed by the attestation alone. The chart does not
   claim they are compatible; it only stops asserting they are not.

This boundary (`<= v0.2.224`) must be raised as further incompatible releases ship, and replaced by a
minimum-supported-version check once a release actually reads the variable.

No released operator image supports this at the time of writing (kubescape/operator#522 is not
merged), and the chart's default `operator.image.tag` does not read the variable. Until a release
includes the feature:

1. Build the operator from kubescape/operator#522 (or a later release that includes it) and push it
   to a registry you control.
2. Set `operator.image.repository`/`operator.image.tag` to that image. Custom registries and image
   references are fully supported.
3. Set `operatorSupportsClientCA: true`.

Once a released image ships the feature, this attestation can be replaced by a minimum-version check
in the chart.

## Kubernetes API-server client certificate configuration

The API server presents a client certificate to a webhook **only** when the cluster administrator
configures the control plane's `--admission-control-config-file` with an `AdmissionConfiguration`
that supplies a `kubeConfigFile` for the webhook host:

```yaml
# admission-control-config.yaml (referenced by kube-apiserver --admission-control-config-file)
apiVersion: apiserver.config.k8s.io/v1
kind: AdmissionConfiguration
plugins:
  - name: ValidatingAdmissionWebhook
    configuration:
      apiVersion: apiserver.config.k8s.io/v1
      kind: WebhookAdmissionConfiguration
      kubeConfigFile: /etc/kubernetes/admission/webhook-kubeconfig.yaml
```

```yaml
# webhook-kubeconfig.yaml — client cert the API server presents to webhooks
apiVersion: v1
kind: Config
users:
  - name: '*'            # or the exact webhook service DNS name
    user:
      client-certificate: /etc/kubernetes/admission/apiserver-client.crt
      client-key: /etc/kubernetes/admission/apiserver-client.key
```

The `apiserver-client.crt` must be issued by the CA stored in `clientAuth.secretName`.

## Control-plane compatibility limitations

- A Helm chart cannot set a control-plane flag, and several managed control planes (EKS/GKE/AKS) do
  not expose `--admission-control-config-file`. On those, this feature cannot be used and the webhook
  stays server-TLS-only.
- Authentication covers only the transport peer (the API server). It does not distinguish *which*
  API-server identity beyond "signed by the configured CA"; scope the client CA accordingly.
- It does not alter `failurePolicy: Ignore` or the `Allowed: true` response, so it changes neither
  admission outcomes nor rule evaluation — only who may submit reviews.

## `/health` also requires a client certificate

When mTLS is enabled it applies to the **entire webhook TLS listener** (port `8443`), not just
`/validate`. Both `/validate` **and** `/health` on that listener then require a client certificate
that chains to the configured CA; an unauthenticated caller is rejected at the TLS handshake for
either path.

- The operator's own **readiness/liveness probes are unaffected** — they target the separate port
  `8000` endpoints (`/v1/readiness`, `/v1/liveness`), which have no TLS and no client-cert
  requirement. Enabling mTLS does not change pod health checking.
- **External monitoring that scrapes the webhook `/health` on `8443` must present a trusted client
  certificate** once mTLS is enabled, or switch to probing the port `8000` readiness endpoint.

## Certificate rotation

The trusted CA bundle is re-read per TLS handshake. Replacing the Secret (Kubernetes swaps the
`..data` symlink) is picked up on the next connection — no operator restart is needed. A
half-written/invalid CA file keeps the last-good trust pool rather than dropping verification. The
existing server-certificate rotation is unchanged; client verification is layered on top.

## Verifying that authentication is active

1. With a trusted client certificate, admission telemetry continues for legitimate workloads —
   confirming the API server's certificate is trusted.
2. From inside the cluster, a request to the webhook **without** a client certificate should be
   rejected at the TLS handshake:

   ```bash
   # expect a TLS handshake / certificate-required error, not an AdmissionReview response
   kubectl -n kubescape exec deploy/operator -- \
     curl -sv --cacert /etc/certs/tls.crt https://localhost:8443/health
   ```

3. If admission telemetry stops after enabling, the API-server client certificate is not trusted by
   the configured CA — fix the CA/kubeconfig and re-check. The webhook fails closed, so it will not
   revert to unauthenticated.

## Disabling the feature safely

Set `operator.admissionWebhooks.clientAuth.enabled: false` (the default) and upgrade. The rendered
manifests and the webhook's TLS behaviour return to server-TLS-only; the CA mount and env var are
removed. With `enabled: false` the rendered Deployment is identical to a chart without this feature,
so disabling is a safe rollback.
