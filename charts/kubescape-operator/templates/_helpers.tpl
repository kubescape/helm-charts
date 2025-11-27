{{/*
Expand the name of the chart.
*/}}
{{- define "kubescape-operator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "kubescape-operator.fullname" -}}
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
{{- define "kubescape-operator.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common annotations
*/}}
{{- define "kubescape-operator.annotations" -}}
{{- if .Values.additionalAnnotations }}
{{ toYaml .Values.additionalAnnotations }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "kubescape-operator.labels" -}}
helm.sh/chart: {{ include "kubescape-operator.chart" . }}
{{ include "kubescape-operator.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: kubescape
app: {{ .app }}
tier: {{ .tier }}
kubescape.io/ignore: "true"
{{- if .Values.additionalLabels }}
{{ toYaml .Values.additionalLabels }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "kubescape-operator.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kubescape-operator.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: {{ .app }}
{{- end }}

{{/*
Node-agent init containers - combines startup-jitter (if enabled), serviceDiscovery (if enabled), and custom initContainers
*/}}
{{- define "nodeAgent.initContainers" -}}
{{- $components := fromYaml (include "components" .) }}
{{- $no_proxy_envar_list := (include "no_proxy_envar_list" .) -}}
{{- $initContainers := list }}
{{- if .Values.nodeAgent.startupJitterContainer.enabled }}
{{- $startupJitter := dict "name" "startup-jitter" "image" "busybox:latest" "command" (list "/bin/sh" "-c" (printf "SLEEP_TIME=$(( $RANDOM %% %d ))\necho \"Pod $(hostname) will sleep for $SLEEP_TIME seconds\"\nsleep $SLEEP_TIME\necho \"Pod $(hostname) finished sleeping after $SLEEP_TIME seconds\"" (int .Values.nodeAgent.startupJitterContainer.maxStartupJitter))) }}
{{- $initContainers = append $initContainers $startupJitter }}
{{- end }}
{{- if $components.serviceDiscovery.enabled }}
{{- $serviceDiscoveryContainer := dict "name" .Values.serviceDiscovery.urlDiscovery.name "image" (printf "%s:%s" .Values.serviceDiscovery.urlDiscovery.image.repository .Values.serviceDiscovery.urlDiscovery.image.tag) "imagePullPolicy" .Values.serviceDiscovery.urlDiscovery.image.pullPolicy "securityContext" (dict "allowPrivilegeEscalation" false "readOnlyRootFilesystem" true "runAsNonRoot" true) "resources" .Values.serviceDiscovery.resources "volumeMounts" (list (dict "name" "services" "mountPath" "/data")) }}
{{- $args := list "-method=get" "-scheme=https" (printf "-host=%s" .Values.server) "-path=api/v2/servicediscovery" "-path-output=/data/services.json" }}
{{- if .Values.serviceDiscovery.urlDiscovery.insecureSkipTLSVerify }}
{{- $args = append $args "-skip-ssl-verify=true" }}
{{- end }}
{{- $serviceDiscoveryContainer = merge $serviceDiscoveryContainer (dict "args" $args) }}
{{- if ne .Values.global.httpsProxy "" }}
{{- $env := list (dict "name" "HTTPS_PROXY" "value" .Values.global.httpsProxy) (dict "name" "no_proxy" "value" $no_proxy_envar_list) }}
{{- $serviceDiscoveryContainer = merge $serviceDiscoveryContainer (dict "env" $env) }}
{{- end }}
{{- if ne .Values.global.proxySecretFile "" }}
{{- $volumeMounts := append (index $serviceDiscoveryContainer "volumeMounts") (dict "name" "proxy-secret" "mountPath" "/etc/ssl/certs/proxy.crt" "subPath" "proxy.crt") }}
{{- $serviceDiscoveryContainer = merge $serviceDiscoveryContainer (dict "volumeMounts" $volumeMounts) }}
{{- end }}
{{- $initContainers = append $initContainers $serviceDiscoveryContainer }}
{{- end }}
{{- if .Values.nodeAgent.initContainers }}
{{- $initContainers = concat $initContainers .Values.nodeAgent.initContainers }}
{{- end }}
{{- if $initContainers }}
{{- toYaml $initContainers }}
{{- end }}
{{- end }}
