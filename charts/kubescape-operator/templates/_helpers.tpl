
{{- define "configurations" -}}
{{- $otel := not (empty .Values.configurations.otelUrl) -}}
{{- $submit := not (empty .Values.server) -}}
ksOtel: {{ $submit }}
otel: {{ $otel }}
otelPort : {{ if $otel }}{{ splitList ":" .Values.configurations.otelUrl | last }}{{ else }}""{{ end }}
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
  enabled: {{ or (eq .Values.capabilities.configurationScan "enable") (eq .Values.capabilities.nodeScan "enable") }}
kubescapeScheduler:
  enabled: {{ and $configurations.submit (or (eq .Values.capabilities.configurationScan "enable") (eq .Values.capabilities.nodeScan "enable")) }}
kubevuln:
  enabled: {{ or (eq .Values.capabilities.relevancy "enable") (eq .Values.capabilities.vulnerabilityScan "enable") }}
kubevulnScheduler:
  enabled: {{ and $configurations.submit (or (eq .Values.capabilities.relevancy "enable") (eq .Values.capabilities.vulnerabilityScan "enable")) }}
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
{{- end -}}
