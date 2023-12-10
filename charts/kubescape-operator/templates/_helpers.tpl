{{- define "checksums" -}}
capabilitiesConfig: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.configMapsDirectory "components-configmap.yaml") . | sha256sum }}
cloudConfig: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.configMapsDirectory "cloudapi-configmap.yaml") . | sha256sum }}
cloudSecret: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.configMapsDirectory "cloud-secret.yaml" ) . | sha256sum }}
hostScannerConfig: {{ include (printf "%s/kubescape/host-scanner-definition-configmap.yaml" $.Template.BasePath ) . | sha256sum }}
matchingRulesConfig: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.configMapsDirectory "matchingRules-configmap.yaml") . | sha256sum }}
nodeAgentConfig: {{ include (printf "%s/node-agent/configmap.yaml" $.Template.BasePath) . | sha256sum }}
operatorConfig: {{ include (printf "%s/operator/configmap.yaml" $.Template.BasePath) . | sha256sum }}
proxySecret: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.proxySecretDirectory "proxy-secret.yaml") . | sha256sum }}
{{- end -}}


{{- define "configurations" -}}
{{- $createCloudSecret := (empty .Values.credentials.cloudSecret) -}}
{{- $otel := not (empty .Values.configurations.otelUrl) -}}
{{- $submit := not (empty .Values.server) -}}
createCloudSecret: {{ $createCloudSecret }}
ksOtel: {{ $submit }}
otel: {{ $otel }}
otelPort : {{ if $otel }}{{ splitList ":" .Values.configurations.otelUrl | last }}{{ else }}""{{ end }}
runtimeObservability: {{ eq .Values.capabilities.runtimeObservability "enable" }}
submit: {{ $submit }}
  {{- if $submit -}}
    {{- if empty .Values.account -}}
      {{- fail "submitting is enabled but value for account is not defined: please register at https://cloud.armosec.io to get yours and re-run with  --set account=<your Guid>" }}
    {{- end -}}
    {{- if empty .Values.clusterName -}}
      {{- fail "value for clusterName is not defined: re-run with  --set clusterName=<your cluster name>" }}
    {{- end -}}
  {{- end -}}
{{- end -}}

{{- define "components" -}}
{{- $configurations := fromYaml (include "configurations" .) }}
gateway:
  enabled: {{ $configurations.submit }}
hostScanner:
  enabled: {{ eq .Values.capabilities.nodeScan "enable" }}
kollector:
  enabled: {{ $configurations.submit }}
kubescape:
  enabled: {{ or (eq .Values.capabilities.configurationScan "enable") (eq .Values.capabilities.continuousScan "enable") }}
kubescapeScheduler:
  enabled: {{ and $configurations.submit (eq .Values.capabilities.configurationScan "enable") }}
kubevuln:
  enabled: {{ eq .Values.capabilities.vulnerabilityScan "enable" }}
kubevulnScheduler:
  enabled: {{ and $configurations.submit (eq .Values.capabilities.vulnerabilityScan "enable") }}
nodeAgent:
  enabled: {{ (eq .Values.capabilities.relevancy "enable") }}
operator:
  enabled: true
otelCollector:
  enabled: {{ or $configurations.ksOtel $configurations.otel }}
serviceDiscovery:
  enabled: {{ $configurations.submit }}
storage:
  enabled: true
cloudSecret:
  create: {{ $configurations.createCloudSecret }}
  name: {{ if $configurations.createCloudSecret }}"cloud-secret"{{ else }}{{ .Values.credentials.cloudSecret }}{{ end }}
{{- end -}}
