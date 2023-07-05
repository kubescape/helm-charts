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
  