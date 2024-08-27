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
