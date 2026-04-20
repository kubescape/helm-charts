{{- define "kubescape-admission.name" -}}
kubescape-admission-webhook
{{- end }}

{{- define "kubescape-admission.svcName" -}}
{{- printf "kubescape-admission-webhook.%s.svc" .Values.ksNamespace -}}
{{- end }}
