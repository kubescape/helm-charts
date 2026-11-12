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
  Create the name of the Kubescape Storage APIService
  */}}
{{- define "storage.apiServiceName" -}}
v1beta1.spdx.softwarecomposition.kubescape.io
{{- end }}

{{/*
  storage.mcpDuration checks one duration setting of storage.mcp, given as (list "name" value), and returns it as a
  string, or "" when it is unset or empty. A value without a unit or a zero duration fails the render: storage
  would not start with it.
  */}}
{{- define "storage.mcpDuration" -}}
{{- $name := index . 0 }}
{{- $v := index . 1 }}
{{- if not (or (kindIs "invalid" $v) (eq (toString $v) "")) }}
{{- if or (not (regexMatch "^([0-9]+(\\.[0-9]+)?(ns|us|ms|s|m|h))+$" (toString $v))) (regexMatch "^(0+(\\.0+)?(ns|us|ms|s|m|h))+$" (toString $v)) }}
{{- fail (printf "storage.mcp.%s must be a positive duration such as 30s, got %v" $name $v) }}
{{- end }}
{{- toString $v }}
{{- end }}
{{- end }}
