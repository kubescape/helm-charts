{{/* standardize cloud provider */}}
{{- define "cloud_provider" -}}
  {{- if .Values.cloud_provider_engine -}}
    {{- $provider := lower .Values.cloud_provider_engine -}}
    {{- if or (contains "eks" $provider) (contains "aws" $provider) (contains "amazon" $provider) -}}
eks
    {{- else if or (contains "gke" $provider) (contains "gcp" $provider) (contains "google" $provider) -}}
gke
    {{- end -}}
  {{- end -}}
{{- end }}

{{- define "account_guid" -}}
  {{- if .Values.armoKubescape.submit }}
    {{- if .Values.accountGuid -}}
    {{- else -}}
      {{- fail "submitting is enabled but value for accountGuid is not defined: please register at https://cloud.armosec.io to get yours and re-run with  --set accountGuid=<your Guid>" }}
    {{- end -}}
  {{- end }}
{{- end }}

{{- define "cluster_name" -}}
  {{- if .Values.armoKubescape.submit }}
    {{- if .Values.clusterName -}}
    {{- else -}}
      {{- fail "value for clusterName is not defined: re-run with  --set clusterName=<your cluster name>" }}
    {{- end -}}
  {{- end }}
{{- end }}

