{{/*
Create the name of the Kubescape Storage Auth Reader RoleBinding to use
*/}}
{{- define "storage.authReaderRoleBindingName" -}}
  {{- .Values.storage.name | printf "%s-auth-reader" }}
{{- end }}

{{/*
  Create the name of the Kubescape Storage Auth Reader ClusterRoleBinding to use
  */}}
{{- define "storage.authDelegatorClusterRoleBindingName" -}}
  {{- .Values.storage.name | printf "%s:system:auth-delegator" }}
{{- end }}

{{/*
  Generate a private key and certificate pair for mTLS
*/}}
{{- define "storage.generateCerts.ca" -}}
{{- if not .Values.global.storageCA -}}
{{- $cn := printf "%s-%s" .Values.storage.name (randAlphaNum 10) -}}
{{- $ca := genCA (printf "%s-ca" $cn) (int .Values.storage.mtls.certificateValidityInDays) -}}
{{- $_ := set .Values.global "storageCA" $ca -}}
{{- end -}}
{{- .Values.global.storageCA | toJson -}}
{{- end -}}

{{- define "storage.generateCerts.cert" -}}
{{- $cn := printf "%s.%s.svc-%s" .Values.storage.name .Values.ksNamespace (randAlphaNum 10) -}}
{{- $ca := .Values.global.storageCA -}}
{{- $dnsNames := list (printf "%s.%s.svc" .Values.storage.name .Values.ksNamespace) (printf "%s.%s.svc.cluster.local" .Values.storage.name .Values.ksNamespace) -}}
{{- $cert := genSignedCert $cn nil $dnsNames (int .Values.storage.mtls.certificateValidityInDays) $ca -}}
{{- $cert | toJson -}}
{{- end -}}
