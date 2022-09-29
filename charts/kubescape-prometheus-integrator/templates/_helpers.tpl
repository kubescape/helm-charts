{{/* standardize cloud provider */}}
{{- define "cloud_provider" -}}
  {{- if .Values.cloudProviderMetadata.cloudProviderEngine -}}
    {{- $provider := lower .Values.cloudProviderMetadata.cloudProviderEngine -}}
    {{- if or (contains "eks" $provider) (contains "aws" $provider) (contains "amazon" $provider) -}}
eks
    {{- else if or (contains "gke" $provider) (contains "gcp" $provider) (contains "google" $provider) -}}
gke
    {{- end -}}
  {{- end -}}
{{- end -}}
  