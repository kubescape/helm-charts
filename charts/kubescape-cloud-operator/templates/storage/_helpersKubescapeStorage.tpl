{{/*
Expand the name of the chart.
*/}}
{{- define "kubescape-storage.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "kubescape-storage.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "kubescape-storage.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "kubescape-storage.labels" -}}
helm.sh/chart: {{ include "kubescape-storage.chart" . }}
{{ include "kubescape-storage.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "kubescape-storage.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kubescape-storage.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

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
