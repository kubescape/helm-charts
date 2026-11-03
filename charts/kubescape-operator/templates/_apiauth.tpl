{{/*
In-cluster API authentication (global.apiAuth).
Servers (kubescape, kubevuln, synchronizer, operator) validate the caller's
service-account token with a TokenReview for the configured audience and
authorize it with a SubjectAccessReview in POD_NAMESPACE.
Callers (operator, node-agent) send a projected token mounted from
apiauth.callerVolume.
*/}}

{{- define "apiauth.tokenDir" -}}
/var/run/secrets/kubescape.io/api-token
{{- end -}}

{{- define "apiauth.tokenFile" -}}
{{ include "apiauth.tokenDir" . }}/token
{{- end -}}

{{/*
Server env. Always rendered so that global.apiAuth.enabled=false reaches the
servers as KS_API_AUTH_DISABLED.
Usage: {{- include "apiauth.serverEnv" . | nindent 12 }}
*/}}
{{- define "apiauth.serverEnv" -}}
- name: KS_API_AUDIENCE
  value: {{ .Values.global.apiAuth.audience | quote }}
- name: POD_NAMESPACE
  valueFrom:
    fieldRef:
      fieldPath: metadata.namespace
{{- if not .Values.global.apiAuth.enabled }}
- name: KS_API_AUTH_DISABLED
  value: "true"
{{- end }}
{{- end -}}

{{/*
Projected service-account token volume for callers; empty when apiAuth is disabled.
*/}}
{{- define "apiauth.callerVolume" -}}
{{- if .Values.global.apiAuth.enabled -}}
- name: kubescape-api-token
  projected:
    sources:
      - serviceAccountToken:
          audience: {{ .Values.global.apiAuth.audience | quote }}
          expirationSeconds: 3600
          path: token
{{- end }}
{{- end -}}

{{- define "apiauth.callerVolumeMount" -}}
{{- if .Values.global.apiAuth.enabled -}}
- name: kubescape-api-token
  mountPath: {{ include "apiauth.tokenDir" . }}
  readOnly: true
{{- end }}
{{- end -}}
