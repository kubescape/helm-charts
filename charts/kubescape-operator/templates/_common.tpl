{{/* validate alertCRD.scopeClustered and alertCRD.scopeNamespaced are mutual exclusive */}}
{{- if and .Values.alertCRD.scopeClustered .Values.alertCRD.scopeNamespaced }}
{{- fail "alertCRD.scopeClustered and alertCRD.scopeNamespaced cannot both be true" }}
{{- end }}

{{- define "checksums" -}}
capabilitiesConfig: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.configMapsDirectory "components-configmap.yaml") . | replace .Chart.AppVersion "" | sha256sum }}
cloudConfig: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.configMapsDirectory "cloudapi-configmap.yaml") . | replace .Chart.AppVersion "" | sha256sum }}
cloudSecret: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.configMapsDirectory "cloud-secret.yaml" ) . | replace .Chart.AppVersion "" | sha256sum }}
hostScannerConfig: {{ include (printf "%s/kubescape/host-scanner-definition-configmap.yaml" $.Template.BasePath ) . | replace .Chart.AppVersion "" | sha256sum }}
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
hostScanner:
  enabled: {{ eq .Values.capabilities.nodeScan "enable" }}
kubescape:
  enabled: {{ eq .Values.capabilities.configurationScan "enable" }}
kubescapeScheduler:
  enabled: {{ eq .Values.capabilities.configurationScan "enable" }}
kubevuln:
  enabled: {{ eq .Values.capabilities.vulnerabilityScan "enable" }}
kubevulnScheduler:
  enabled: {{ eq .Values.capabilities.vulnerabilityScan "enable" }}
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
  enabled: true
otelCollector:
  enabled: {{ and $configurations.ksOtel (not $configurations.otel) }}
serviceDiscovery:
  enabled: {{ $configurations.submit }}
storage:
  enabled: true
prometheusExporter:
  enabled: {{ eq .Values.capabilities.prometheusExporter "enable" }}
cloudSecret:
  create: {{ $configurations.createCloudSecret }}
  name: {{ if $configurations.createCloudSecret }}"cloud-secret"{{ else }}{{ .Values.credentials.cloudSecret }}{{ end }}
synchronizer:
  enabled: {{ $configurations.submit }}
clamAV:
  enabled: {{ eq .Values.capabilities.malwareDetection "enable" }}
customCaCertificates:
  name: custom-ca-certificates
autoUpdater:
  enabled: {{ eq .Values.capabilities.autoUpgrading "enable" }}
{{- end -}}

{{- define "admission-certificates" -}}
{{- $svcName := (printf "kubescape-admission-webhook.%s.svc" .Values.ksNamespace) -}}
{{- $ca := dict "Key" "mock-ca-key" "Cert" "mock-ca-cert" -}}
{{- $cert := dict "Key" "mock-cert-key" "Cert" "mock-cert-cert" -}}
{{- if not .Values.unittest }}
  {{- $generatedCA := genCA (printf "*.%s.svc" .Values.ksNamespace) 1024 -}}
  {{- $generatedCert := genSignedCert $svcName nil (list $svcName) 1024 $generatedCA -}}
  {{- $_ := set $ca "Key" $generatedCA.Key -}}
  {{- $_ := set $ca "Cert" $generatedCA.Cert -}}
  {{- $_ := set $cert "Key" $generatedCert.Key -}}
  {{- $_ := set $cert "Cert" $generatedCert.Cert -}}
{{- end -}}
{{- $certData := dict "ca" $ca "cert" $cert -}}
{{- toYaml $certData -}}
{{- end -}}
