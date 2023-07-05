{{/* standardize cloud provider */}}
{{- define "cloud_provider" -}}
  {{- if contains "eks" .Capabilities.KubeVersion.GitVersion -}}
    {{- print "eks" -}}
  {{- else if contains "gke" .Capabilities.KubeVersion.GitVersion -}}
    {{- print "gke" -}}
  {{- else if contains "azmk8s.io" .Values.clusterServer -}}
    {{- print "aks" -}}
  {{- else -}}
    {{- print "" -}}
  {{- end }}
{{- end }} 

{{- define "account_guid" -}}
  {{- if .Values.kubescape.submit }}
    {{- if .Values.account -}}
    {{- else -}}
      {{- fail "submitting is enabled but value for account is not defined: please register at https://cloud.armosec.io to get yours and re-run with  --set account=<your Guid>" }}
    {{- end -}}
  {{- end }}
{{- end }}

{{- define "cluster_name" -}}
  {{- if .Values.kubescape.submit }}
    {{- if .Values.clusterName -}}
    {{- else -}}
      {{- fail "value for clusterName is not defined: re-run with  --set clusterName=<your cluster name>" }}
    {{- end -}}
  {{- end }}
{{- end }}

{{- define "check.provider" -}}
  {{- $cloudProvider := include "cloud_provider" . -}}
  {{- if or (eq $cloudProvider "eks") (eq $cloudProvider "gke") (eq $cloudProvider "aks") -}}
    {{- print "true" -}}
  {{- else -}}
    {{- print "false" -}}
  {{- end -}}
{{- end -}}

{{- define "relevancy.Enabled" -}}
  {{- $isManaged := include "check.provider" . -}}
  {{ if eq .Values.capabilities.relevancy "enable" -}}
    {{- print "true" -}}
  {{ else if eq .Values.capabilities.relevancy "disable" -}}
    {{- print "false" -}}
  {{- else if and (eq .Values.capabilities.relevancy "detect") (eq $isManaged "true") -}}
    {{- print "true" -}}
  {{- else -}}
    {{- print "false" -}}
  {{- end -}}
{{- end -}}
