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
   `ADMISSION_CLIENT_CA_FILE`. Every released version **up to and including v0.2.240** (the latest release at the time of
   writing) is verified to
   lack it, so any **SemVer** tag whose `major.minor.patch` core is at or below that boundary is
   rejected **even when `operatorSupportsClientCA` is `true`**.

   This comparison is on the SemVer **core**, so it includes **prereleases** of incompatible
   versions: `v0.2.224-rc1`, `v0.2.224-beta.1` and `v0.2.223-custom` are all rejected (checked at
   their `0.2.224` / `0.2.223` base), because a prerelease of a version that lacks the feature also
   lacks it. (A dotted-decimal detail: Masterminds `semverCompare` excludes prereleases from a
   non-prerelease constraint such as `<= 0.2.240`, which is why the chart compares the core rather
   than the raw tag.) A prerelease **above** the boundary, such as `v0.2.241-rc1`, is allowed under
   attestation — `0.2.241 > 0.2.240`, so it is not *known* incompatible.

   **Genuine non-SemVer tags** — custom/dev builds from kubescape/operator#522, git SHAs, branch
   names — are not version-checked and are governed by the attestation alone. The chart does not
   claim they are compatible; it only stops asserting they are not.

   **Digest-pinned tags.** The chart renders the image as `<repository>:<tag>`, so pin a digest by
   writing it into the tag: `operator.image.tag: v0.2.241@sha256:<digest>`. When mTLS is enabled the
   gate splits off the digest and applies the checks above to the tag before `@`, so
   `v0.2.224@sha256:…` and `v0.2.224-rc1@sha256:…` are rejected exactly like `v0.2.224` and
   `v0.2.224-rc1`. A digest pin never makes an image count as compatible: a digest-pinned release
   above the boundary, or a digest-pinned custom tag, still needs `operatorSupportsClientCA: true`.
   The digest must be `sha256:` followed by exactly 64 **lowercase** hex characters, and the tag
   before `@` must be a non-empty, valid image tag (letters, digits, `_`, `.`, `-`; at most 128
   characters). Anything else is rejected with an explicit error rather than guessed at: a short or
   uppercase digest, another algorithm, a missing tag (`@sha256:…`), more than one `@`, or SemVer
   build metadata (`+build`), since `+` is not a legal image-tag character. The image reference is
   rendered exactly as you set it, never rewritten. With mTLS disabled none of this validation
   runs, and the image renders as before.

This boundary (`<= v0.2.240`) must be raised as further incompatible releases ship, and replaced by a
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
# webhook-kubeconfig.yaml — client credentials the API server presents to webhooks
apiVersion: v1
kind: Config
users:
  # Exact DNS name of the Kubescape admission webhook Service: <service>.<namespace>.svc.
  # The chart's default Service is kubescape-admission-webhook on port 443. If you change
  # operator.admissionWebhooks.service.port to a non-443 port, append it, for example
  # kubescape-admission-webhook.kubescape.svc:8443.
  - name: kubescape-admission-webhook.kubescape.svc
    user:
      client-certificate: /etc/kubernetes/admission/kubescape-webhook-client.crt
      client-key: /etc/kubernetes/admission/kubescape-webhook-client.key
```

The client certificate must be issued by the CA stored in `clientAuth.secretName`.

### Scope the client identity to this webhook. Do not use a `'*'` user.

The kubeconfig `users[].name` decides which webhook endpoints the API server presents a credential
to. The upstream reference
([Authenticate API servers](https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/#authenticate-apiservers))
documents three forms:

- **The exact Service DNS name, or `host:port` for a URL webhook.** For a Service on a port other
  than 443, the port must be included on Kubernetes 1.16+.
- **A leading wildcard such as `*.example.org`.** This matches prefixing segments.
- **`'*'`, the default match.** It applies to every webhook that has no other matching entry.

Use the exact name shown above. A `'*'` entry, or a broad wildcard such as `*.svc`, makes the API
server present this certificate to **unrelated** webhooks too. That includes third-party and
URL-based webhooks that anyone allowed to create webhook configurations can register. Those
endpoints never receive the private key, but every one of them now sees, and could choose to trust,
the same "Kubescape webhook caller" identity. That makes the identity useless as a statement about
which webhook was called. If another webhook also trusts the CA that issued it, both webhooks accept
each other's caller. A `'*'` entry can also collide with credentials other webhooks already rely on
in the same kubeconfig. A namespace wildcard (`*.kubescape.svc`) is narrower but still covers every
Service in that namespace, so prefer the exact name.

### Trust a dedicated CA, not the cluster CA

The webhook accepts **any** client certificate that chains to the configured CA. In
kubescape/operator#522 it sets `ClientAuth: RequireAndVerifyClientCert` with that CA pool and does
**not** check the certificate's subject, CN or SANs. That makes the CA itself the only scope, so:

- **Create a dedicated CA used for nothing else** than issuing this one API-server client
  certificate, and put only that CA in `clientAuth.secretName`.
- **Never** use the cluster CA (for example `/etc/kubernetes/pki/ca.crt`) or any CA that also
  signs kubelet, user, controller or other components' client certificates. Every certificate that
  CA has issued (node kubelets, admin kubeconfigs and so on) would then pass the webhook's mTLS check.
- Do not reuse a CA or client certificate that is already trusted by unrelated webhooks.
- Issue the client certificate with `extendedKeyUsage = clientAuth`. Go's TLS server verification
  (which the operator uses) requires the client-auth usage. It rejects a leaf certificate whose
  extended key usage lists other purposes (for example only `serverAuth`). Keep its lifetime short
  enough to rotate routinely (see [Certificate rotation](#certificate-rotation)).

## Control-plane compatibility limitations

- A Helm chart cannot set a control-plane flag, and several managed control planes (EKS/GKE/AKS) do
  not expose `--admission-control-config-file`. On those, this feature cannot be used and the webhook
  stays server-TLS-only.
- Authentication covers only the transport peer (the API server). It does not distinguish *which*
  identity beyond "signed by the configured CA", so the CA must be dedicated to this purpose (see
  [Trust a dedicated CA, not the cluster CA](#trust-a-dedicated-ca-not-the-cluster-ca)).
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

Rotation needs no operator restart, but it is **not instantaneous**. A new CA takes effect only
after two independent steps.

### 1. Secret volume projection delay (kubelet)

Updating the Secret does **not** immediately change the file the operator reads. The kubelet
updates mounted Secret volumes on an eventually-consistent basis. Per the
[Kubernetes Secret documentation](https://kubernetes.io/docs/concepts/configuration/secret/#using-secrets-as-files-from-a-pod),
the delay can be as long as the kubelet sync period plus the cache propagation delay of the
kubelet's `configMapAndSecretChangeDetectionStrategy`:

- `Watch` (the default): the watch propagation delay.
- `Cache`: the configured cache TTL.
- `Get`: zero.

The kubelet's default `syncFrequency` is `1m`, so expect a lag of up to roughly a minute plus the
propagation delay on default settings. Do not assume that
`kubectl apply`/`create secret` has changed the CA pool. The chart mounts the Secret as a directory
(not a `subPath`), so it does receive updates. A `subPath` mount would never receive them. When the
kubelet updates the volume, it atomically swaps the `..data` symlink, so the operator reads either
the old file or the new one, never a partial write.

### 2. Operator reload (per new TLS handshake)

On every new TLS handshake the operator `stat`s the CA file. If its identity, size or mtime
changed, it re-reads and re-parses it. The new pool applies to **new** connections only. A
connection that is already established keeps the pool it was verified with. The API server reuses
(keep-alive) connections to webhooks, so the old CA can stay in effect on an existing connection
after the file has changed.

### Last-good-pool behavior: what it does and does not cover

This behavior was verified against the kubescape/operator#522 implementation (`parsePool`, which
uses Go's `x509.CertPool.AppendCertsFromPEM`, and `reloadIfChanged`):

| CA file state | At startup | On reload |
|---|---|---|
| Missing / unreadable | Webhook server does not start; the operator logs `admission server stopped` and stops (fail-closed) | Previous pool **kept**; a warning is logged |
| Changed while being read (stat mismatch) | Does not start (as above) | Previous pool **kept**; warning logged |
| **No** valid certificate (empty, garbage, every block malformed) | Does not start (as above) | Previous pool **kept**; warning logged |
| **At least one** valid certificate plus malformed, truncated or non-certificate PEM blocks | **Starts** with only the valid certificates; nothing is logged | **Replaces** the previous pool with only the valid certificates; nothing is logged |
| All certificates valid | Starts | Replaces the previous pool |

Client verification stays enforced in every row. The last-good pool protects you **only when the
new file yields zero certificates**. A **partially malformed** bundle is **not** rejected. The
malformed blocks are silently dropped and the remaining certificates become the active pool. If
the dropped block was the CA that signs the API server's current client certificate, the webhook
starts rejecting the API server. Admission is unaffected because of `failurePolicy: Ignore`, but
admission telemetry stops. kubescape/operator#522 has no test for partial bundles. A stricter
operator-side behavior is recommended separately: reject the whole bundle, and keep the last-good
pool, if any `CERTIFICATE` block fails to parse.

### Safe rotation procedure

1. **Add before you remove.** Update the Secret so `caKey` holds a bundle with **both** the old
   and the new CA. Validate the bundle before applying it. Every block must parse:
   `openssl storeutl -noout -certs ca-bundle.pem` must exit `0` and report the expected
   `Total found:` count. OpenSSL 3 reports a malformed block as an error, a non-zero exit and a
   lower count.
   Do not rely on the operator to reject a partially broken bundle.
2. **Wait for projection.** Wait out the kubelet propagation delay above. To confirm the change,
   check the mounted file, for example with
   `kubectl -n kubescape exec deploy/operator -- cat /etc/admission-client-ca/ca.crt`.
3. **Switch the API server** to a client certificate issued by the new CA, on every API-server
   instance.
4. **Confirm a fresh handshake with the new certificate from every API-server instance.** Continued
   admission telemetry is not enough: an API server can keep sending reviews over an existing
   connection that was authenticated with the old certificate, and only fail on its next new
   connection after the old CA is gone. Make each instance open new connections (for example by
   restarting it), then confirm admission telemetry continues for requests that instance serves.
   You can also check the new certificate directly with the `--cert`/`--key` command in
   [Verifying that authentication is active](#verifying-that-authentication-is-active).
5. **Remove the old CA** from the bundle only after that, and wait for projection again.

The existing server-certificate rotation is unchanged; client verification is layered on top.

## Verifying that authentication is active

1. With a trusted client certificate, admission telemetry continues for legitimate workloads —
   confirming the API server's certificate is trusted.
2. A request to the webhook **without** a client certificate should be rejected at the TLS
   handshake. Connect to the webhook Service DNS name, which is the name on its server certificate,
   and trust the CA that signed that certificate, so that a server name or trust problem is not
   mistaken for the client-certificate rejection:

   ```bash
   NS=kubescape
   HOST=kubescape-admission-webhook.$NS.svc
   # CA of the webhook server certificate. With the default certificates.strategy (template) it is
   # tls.crt in the kubescape-admission-webhook-ca Secret; with the initContainer strategy
   # use the "ca" key of the kubescape-admission-webhook-tls-init Secret instead.
   kubectl -n $NS get secret kubescape-admission-webhook-ca \
     -o jsonpath='{.data.tls\.crt}' | base64 -d > webhook-ca.crt
   kubectl -n $NS port-forward svc/kubescape-admission-webhook 8443:443 > port-forward.log 2>&1 &
   PF_PID=$!
   # wait until the local listener is up, so curl tests the TLS handshake, not a refused connection
   until grep -q 'Forwarding from' port-forward.log; do sleep 1; done
   curl -sv --cacert webhook-ca.crt --resolve "$HOST:8443:127.0.0.1" "https://$HOST:8443/health"
   kill $PF_PID
   ```

   Expected: the server certificate is verified, then the webhook ends the handshake with a
   `certificate required` (TLS 1.3) or `handshake failure` (TLS 1.2) alert, and no
   HTTP response comes back. If curl instead reports `SSL certificate problem` or
   `no alternative certificate subject name matches`, the trust or name setup is wrong, not client
   authentication. Adding `--cert client.crt --key client.key` with a certificate issued by the
   configured client CA should get an HTTP response.

3. If admission telemetry stops after enabling, the API-server client certificate is not trusted by
   the configured CA — fix the CA/kubeconfig and re-check. The webhook fails closed, so it will not
   revert to unauthenticated.

## Disabling the feature safely

Set `operator.admissionWebhooks.clientAuth.enabled: false` (the default) and upgrade. The rendered
manifests and the webhook's TLS behaviour return to server-TLS-only; the CA mount and env var are
removed. With `enabled: false` the rendered Deployment is identical to a chart without this feature,
so disabling is a safe rollback.
