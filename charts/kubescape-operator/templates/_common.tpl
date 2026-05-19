{{/* validate alertCRD.scopeClustered and alertCRD.scopeNamespaced are mutual exclusive */}}
{{- if and .Values.alertCRD.scopeClustered .Values.alertCRD.scopeNamespaced }}
{{- fail "alertCRD.scopeClustered and alertCRD.scopeNamespaced cannot both be true" }}
{{- end }}

{{- define "checksums" -}}
capabilitiesConfig: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.configMapsDirectory "components-configmap.yaml") . | replace .Chart.AppVersion "" | sha256sum }}
cloudConfig: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.configMapsDirectory "cloudapi-configmap.yaml") . | replace .Chart.AppVersion "" | sha256sum }}
cloudSecret: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.configMapsDirectory "cloud-secret.yaml" ) . | replace .Chart.AppVersion "" | sha256sum }}
matchingRulesConfig: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.configMapsDirectory "matchingRules-configmap.yaml") . | replace .Chart.AppVersion "" | sha256sum }}
nodeAgentConfig: {{ include (printf "%s/node-agent/configmap.yaml" $.Template.BasePath) . | replace .Chart.AppVersion "" | sha256sum }}
operatorConfig: {{ include (printf "%s/operator/configmap.yaml" $.Template.BasePath) . | replace .Chart.AppVersion "" | sha256sum }}
otelConfig: {{ include (printf "%s/otel-collector/configmap.yaml" $.Template.BasePath) . | replace .Chart.AppVersion "" | sha256sum }}
proxySecret: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.proxySecretDirectory "proxy-secret.yaml") . | replace .Chart.AppVersion "" | sha256sum }}
synchronizerConfig: {{ include (printf "%s/synchronizer/configmap.yaml" $.Template.BasePath) . | replace .Chart.AppVersion "" | sha256sum }}
{{- end -}}


{{- define "configurations" -}}
{{- $createCloudSecret := (empty .Values.credentials.cloudSecret) -}}
{{- $ksOtel := empty .Values.otelCollector.disable -}}
{{- $otel := not (empty .Values.configurations.otelUrl) -}}
{{- $submit := not (empty .Values.server) -}}
{{- $virtualCrds := not (empty .Values.storage.forceVirtualCrds) -}}
continuousScan: {{ and (eq .Values.capabilities.continuousScan "enable") (not $submit) }}
createCloudSecret: {{ $createCloudSecret }}
ksOtel: {{ and $ksOtel $submit }}
otel: {{ $otel }}
otelPort : {{ if $otel }}{{ splitList ":" .Values.configurations.otelUrl | last }}{{ else }}""{{ end }}
runtimeObservability: {{ eq .Values.capabilities.runtimeObservability "enable" }}
backendStorageEnabled: {{ eq (index .Values.capabilities "backend-storage" | default "") "enable" }}
virtualCrds: {{ or $virtualCrds (not $submit) }}
submit: {{ $submit }}
  {{- if $submit -}}
    {{- if and (empty .Values.account) $createCloudSecret -}}
      {{- fail "submitting is enabled but value for account is not defined: please register at https://cloud.armosec.io to get yours and re-run with  --set account=<your Guid>" }}
    {{- end -}}
    {{- if and (empty .Values.accessKey) $createCloudSecret -}}
      {{- fail "submitting is enabled but value for accessKey is not defined: To obtain an access key, go to 'Settings' -> 'Agent Access Keys' at https://cloud.armosec.io and re-run with  --set accessKey=<your key>" }}
    {{- end -}}
    {{- if empty .Values.clusterName -}}
      {{- fail "value for clusterName is not defined: re-run with  --set clusterName=<your cluster name>" }}
    {{- end -}}
  {{- end -}}
{{- end -}}

{{- define "components" -}}
{{- $configurations := fromYaml (include "configurations" .) }}
{{- $nodeScanEnabled := and (eq .Values.capabilities.nodeScan "enable") (not $configurations.backendStorageEnabled) }}
{{- $configurationScanEnabled := and (eq .Values.capabilities.configurationScan "enable") (not $configurations.backendStorageEnabled) }}
{{- $vulnerabilityScanEnabled := and (eq .Values.capabilities.vulnerabilityScan "enable") (not $configurations.backendStorageEnabled) }}
kubescape:
  enabled: {{ $configurationScanEnabled }}
kubescapeScheduler:
  enabled: {{ $configurationScanEnabled }}
kubevuln:
  enabled: {{ $vulnerabilityScanEnabled }}
kubevulnScheduler:
  enabled: {{ $vulnerabilityScanEnabled }}
nodeAgent:
  enabled: {{ or
   (eq .Values.capabilities.relevancy "enable")
   (eq .Values.capabilities.runtimeObservability "enable")
   (eq .Values.capabilities.networkPolicyService "enable")
   (eq .Values.capabilities.runtimeDetection "enable")
   (eq .Values.capabilities.malwareDetection "enable")
   (eq .Values.capabilities.nodeProfileService "enable")
   (eq .Values.capabilities.seccompProfileService "enable")
  }}
operator:
  enabled: {{ eq .Values.capabilities.operator "enable" }}
otelCollector:
  enabled: {{ and (empty .Values.otelCollector.disable) (or $configurations.ksOtel $configurations.otel) }}
serviceDiscovery:
  enabled: {{ $configurations.submit }}
storage:
  enabled: {{ not $configurations.backendStorageEnabled }}
prometheusExporter:
  enabled: {{ eq .Values.capabilities.prometheusExporter "enable" }}
cloudSecret:
  create: {{ $configurations.createCloudSecret }}
  name: {{ if $configurations.createCloudSecret }}"cloud-secret"{{ else }}{{ .Values.credentials.cloudSecret }}{{ end }}
synchronizer:
  enabled: {{ $configurations.submit }}
clamAV:
  enabled: {{ eq .Values.capabilities.malwareDetection "enable" }}
sbomScanner:
  enabled: {{ and (eq .Values.capabilities.nodeSbomGeneration "enable") .Values.nodeAgent.sbomScanner.enabled }}
customCaCertificates:
  name: custom-ca-certificates
autoUpdater:
  enabled: {{ eq .Values.capabilities.autoUpgrading "enable" }}
{{- end -}}

{{- define "kubescape.certificates.strategy" -}}
{{- $strategy := default "template" .Values.certificates.strategy -}}
{{- if not (has $strategy (list "template" "initContainer")) -}}
{{- fail (printf "certificates.strategy must be one of [template, initContainer], got %q" $strategy) -}}
{{- end -}}
{{- $strategy -}}
{{- end }}

{{- define "kubescape.certificates.initContainerImage" -}}
{{- printf "%s:%s" .Values.grypeOfflineDB.rollout.image.repository (.Values.grypeOfflineDB.rollout.image.tag | toString) -}}
{{- end -}}

{{- define "kubescape.certificates.createScript" -}}
set -euo pipefail

NAMESPACE=""
SECRET_NAME=""
HOSTS=""
OUT_DIR=""
CA_NAME="ca"
CERT_NAME="cert"
KEY_NAME="key"
DAYS="36500"

usage() {
  cat >&2 <<EOF
Usage: certgen-create.sh [flags]
  -n, --namespace      Namespace for the secret (required)
  -s, --secret-name    Name of the secret to read/create (required)
  -H, --host           Comma-separated DNS SANs for the leaf cert (required)
  -o, --out-dir        Directory to write the leaf cert/key into (required)
      --ca-name        Key in the secret for the CA cert (default: ca)
      --cert-name      Key in the secret for the leaf cert (default: cert)
      --key-name       Key in the secret for the leaf key (default: key)
      --days           Validity in days (default: 36500 ~= 100y)
EOF
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--namespace)   NAMESPACE="$2";   shift 2;;
    -s|--secret-name) SECRET_NAME="$2"; shift 2;;
    -H|--host)        HOSTS="$2";       shift 2;;
    -o|--out-dir)     OUT_DIR="$2";     shift 2;;
    --ca-name)        CA_NAME="$2";     shift 2;;
    --cert-name)      CERT_NAME="$2";   shift 2;;
    --key-name)       KEY_NAME="$2";    shift 2;;
    --days)           DAYS="$2";        shift 2;;
    -h|--help)        usage;;
    *) echo "unknown flag: $1" >&2; usage;;
  esac
done

[[ -n "$NAMESPACE"   ]] || { echo "--namespace required"   >&2; usage; }
[[ -n "$SECRET_NAME" ]] || { echo "--secret-name required" >&2; usage; }
[[ -n "$HOSTS"       ]] || { echo "--host required"        >&2; usage; }
[[ -n "$OUT_DIR"     ]] || { echo "--out-dir required"     >&2; usage; }

mkdir -p "$OUT_DIR"

if SECRET_JSON="$(kubectl -n "$NAMESPACE" get secret "$SECRET_NAME" -o json 2>/dev/null)"; then
  echo "secret $NAMESPACE/$SECRET_NAME exists, reusing"
  echo "$SECRET_JSON" | jq -er --arg k "$CERT_NAME" '.data[$k] // empty' | base64 -d > "$OUT_DIR/$CERT_NAME"
  echo "$SECRET_JSON" | jq -er --arg k "$KEY_NAME" '.data[$k] // empty' | base64 -d > "$OUT_DIR/$KEY_NAME"
  [[ -s "$OUT_DIR/$CERT_NAME" && -s "$OUT_DIR/$KEY_NAME" ]] || { echo "secret missing $CERT_NAME/$KEY_NAME" >&2; exit 1; }
  exit 0
fi

echo "secret $NAMESPACE/$SECRET_NAME not found, generating"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

SAN=""; i=0
IFS=',' read -ra HOST_ARR <<< "$HOSTS"
for h in "${HOST_ARR[@]}"; do
  i=$((i+1))
  SAN+="DNS.${i} = ${h}"$'\n'
done

cat > "$TMP/leaf.cnf" <<EOF
[req]
distinguished_name = dn
req_extensions     = v3
prompt             = no
[dn]
CN = ${HOST_ARR[0]}
[v3]
subjectAltName = @san
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
[san]
${SAN}
EOF

openssl ecparam -name prime256v1 -genkey -noout -out "$TMP/ca.key"
openssl req -x509 -new -key "$TMP/ca.key" -days "$DAYS" -subj "/O=certgen-ca" -out "$TMP/ca.crt"

openssl ecparam -name prime256v1 -genkey -noout -out "$TMP/tls.key"
openssl req -new -key "$TMP/tls.key" -config "$TMP/leaf.cnf" -out "$TMP/tls.csr"
openssl x509 -req -in "$TMP/tls.csr" -CA "$TMP/ca.crt" -CAkey "$TMP/ca.key" -CAcreateserial \
  -days "$DAYS" -extensions v3 -extfile "$TMP/leaf.cnf" -out "$TMP/tls.crt"

cp "$TMP/tls.crt" "$OUT_DIR/$CERT_NAME"
cp "$TMP/tls.key" "$OUT_DIR/$KEY_NAME"

kubectl -n "$NAMESPACE" create secret generic "$SECRET_NAME" \
  --from-file="${CA_NAME}=$TMP/ca.crt" \
  --from-file="${CERT_NAME}=$TMP/tls.crt" \
  --from-file="${KEY_NAME}=$TMP/tls.key"
{{- end -}}

{{- define "kubescape.certificates.patchScript" -}}
set -euo pipefail

NAMESPACE=""
SECRET_NAME=""
CA_NAME="ca"
RESOURCE_TYPE=""
RESOURCE_NAME=""
RETRIES="60"
RETRY_INTERVAL="5"

usage() {
  cat >&2 <<EOF
Usage: certgen-patch.sh [flags]
  -n, --namespace        Namespace of the secret (required)
  -s, --secret-name      Name of the secret holding the CA (required)
  -c, --ca-name          Key inside the secret holding the CA cert (default: ca)
  -t, --resource-type    Resource to patch: apiservice | vwc (required)
  -r, --resource-name    Name of the resource to patch (required)
      --retries          Max patch attempts (default: 60)
      --retry-interval   Seconds between attempts (default: 5)
EOF
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--namespace)      NAMESPACE="$2";      shift 2;;
    -s|--secret-name)    SECRET_NAME="$2";    shift 2;;
    -c|--ca-name)        CA_NAME="$2";        shift 2;;
    -t|--resource-type)  RESOURCE_TYPE="$2";  shift 2;;
    -r|--resource-name)  RESOURCE_NAME="$2";  shift 2;;
    --retries)           RETRIES="$2";        shift 2;;
    --retry-interval)    RETRY_INTERVAL="$2"; shift 2;;
    -h|--help)           usage;;
    *) echo "unknown flag: $1" >&2; usage;;
  esac
done

[[ -n "$NAMESPACE" ]] || { echo "--namespace required" >&2; usage; }
[[ -n "$SECRET_NAME" ]] || { echo "--secret-name required" >&2; usage; }
[[ -n "$RESOURCE_TYPE" ]] || { echo "--resource-type required" >&2; usage; }
[[ -n "$RESOURCE_NAME" ]] || { echo "--resource-name required" >&2; usage; }

case "$RESOURCE_TYPE" in
  apiservice|vwc) ;;
  *) echo "--resource-type must be 'apiservice' or 'vwc', got '$RESOURCE_TYPE'" >&2; exit 2;;
esac

CA_BUNDLE="$(kubectl -n "$NAMESPACE" get secret "$SECRET_NAME" -o json | jq -er --arg k "$CA_NAME" '.data[$k] // empty')"
[[ -n "$CA_BUNDLE" ]] || { echo "no '$CA_NAME' key in secret $NAMESPACE/$SECRET_NAME" >&2; exit 1; }

patch_once() {
  case "$RESOURCE_TYPE" in
    apiservice)
      kubectl patch apiservice "$RESOURCE_NAME" --type=merge \
        -p "{\"spec\":{\"caBundle\":\"$CA_BUNDLE\",\"insecureSkipTLSVerify\":false}}"
      ;;
    vwc)
      kubectl patch validatingwebhookconfiguration "$RESOURCE_NAME" --type=json \
        -p "[{\"op\":\"add\",\"path\":\"/webhooks/0/clientConfig/caBundle\",\"value\":\"$CA_BUNDLE\"}]"
      ;;
  esac
}

for i in $(seq 1 "$RETRIES"); do
  if patch_once; then
    exit 0
  fi
  echo "patch attempt $i/$RETRIES failed, retrying in ${RETRY_INTERVAL}s" >&2
  sleep "$RETRY_INTERVAL"
done

echo "patch failed after $RETRIES attempts" >&2
exit 1
{{- end -}}