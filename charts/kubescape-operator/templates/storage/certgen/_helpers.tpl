{{- define "storage.certgen.name" -}}
{{- printf "%s-certgen" .Values.storage.name -}}
{{- end }}

{{- define "storage.certgen.secretName" -}}
{{- printf "%s-tls" .Values.storage.name -}}
{{- end }}

{{- define "storage.certgen.apiServiceName" -}}
v1beta1.spdx.softwarecomposition.kubescape.io
{{- end }}
