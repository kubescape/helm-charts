{{- define "kubescape.certificates.strategy" -}}
{{- $strategy := default "helm" .Values.certificates.strategy -}}
{{- if not (has $strategy (list "helm" "hook")) -}}
{{- fail (printf "certificates.strategy must be one of [helm, hook], got %q" $strategy) -}}
{{- end -}}
{{- $strategy -}}
{{- end }}
