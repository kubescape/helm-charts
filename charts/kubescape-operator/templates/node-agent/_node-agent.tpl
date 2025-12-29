{{/*
Node Agent shared template definitions.
This is the single source of truth for node-agent DaemonSet configuration.
Used by: daemonset.yaml, daemonsets.yaml, and template-configmap.yaml
*/}}

{{/*
Node Agent Resources
Parameters:
  - autoscalerMode: boolean - if true, outputs Go template placeholders
  - resources: the resources object to use (when autoscalerMode is false)
*/}}
{{- define "node-agent.resources" -}}
{{- if .autoscalerMode }}
requests:
  cpu: "{{`{{ .Resources.Requests.CPU }}`}}"
  memory: "{{`{{ .Resources.Requests.Memory }}`}}"
limits:
  cpu: "{{`{{ .Resources.Limits.CPU }}`}}"
  memory: "{{`{{ .Resources.Limits.Memory }}`}}"
{{- else }}
{{ toYaml .resources | trim }}
{{- end }}
{{- end -}}

{{/*
Node Agent Environment Variables
Parameters:
  - Values: .Values
  - components: $components
  - no_proxy_envar_list: the no_proxy list
  - autoscalerMode: boolean
  - testingMode: boolean - for MULTIPLY env var
*/}}
{{- define "node-agent.env" -}}
- name: GOMEMLIMIT
  valueFrom:
    resourceFieldRef:
      resource: limits.memory
      divisor: '1'
- name: GOMAXPROCS
  valueFrom:
    resourceFieldRef:
      resource: limits.cpu
      divisor: '1'
- name: HOST_ROOT
  value: "/host"
- name: KS_LOGGER_LEVEL
  value: "{{ .Values.logger.level }}"
- name: KS_LOGGER_NAME
  value: "{{ .Values.logger.name }}"
{{- if .components.otelCollector.enabled }}
- name: OTEL_COLLECTOR_SVC
  value: "otel-collector:4318"
{{- end }}
{{- if .Values.configurations.otelUrl }}
- name: OTEL_COLLECTOR_SVC
  value: {{ .Values.configurations.otelUrl }}
{{- end }}
{{- if and .components.clamAV.enabled (not .autoscalerMode) }}
- name: CLAMAV_SOCKET
  value: "/clamav/clamd.sock"
{{- end }}
{{- if ne .Values.global.overrideRuntimePath "" }}
- name: RUNTIME_PATH
  value: "{{ .Values.global.overrideRuntimePath }}"
{{- end }}
{{- if ne .Values.global.httpsProxy "" }}
- name: HTTPS_PROXY
  value: "{{ .Values.global.httpsProxy }}"
- name: no_proxy
  value: "{{ .no_proxy_envar_list }}"
{{- end }}
{{- if .Values.nodeAgent.config.skipKernelVersionCheck }}
- name: SKIP_KERNEL_VERSION_CHECK
  value: "true"
{{- end }}
{{- if .Values.nodeAgent.config.malwareScanAllFiles }}
- name: MALWARE_SCAN_ALL_FILES
  value: "true"
{{- end }}
- name: NODE_NAME
  valueFrom:
    fieldRef:
      fieldPath: spec.nodeName
- name: POD_NAME
  valueFrom:
    fieldRef:
      fieldPath: metadata.name
- name: NAMESPACE_NAME
  valueFrom:
    fieldRef:
      fieldPath: metadata.namespace
- name: KUBELET_ROOT
  value: "/var/lib/kubelet"
{{- if and .testingMode .Values.capabilities.testing.nodeAgentMultiplication.enabled }}
- name: MULTIPLY
  value: "true"
{{- end }}
- name: AGENT_VERSION
  value: "{{ .Values.nodeAgent.image.tag }}"
{{- range .Values.nodeAgent.env }}
{{- if .autoscalerMode }}
- {{ toYaml . | nindent 2 | trim }}
{{- else }}
- name: {{ .name }}
{{- if .value }}
  value: "{{ .value }}"
{{- end }}
{{- if .valueFrom }}
  valueFrom:
{{ toYaml .valueFrom | indent 4 }}
{{- end }}
{{- end }}
{{- end }}
{{- end -}}

{{/*
Node Agent Volume Mounts
Parameters:
  - Values: .Values
  - components: $components
*/}}
{{- define "node-agent.volumeMounts" -}}
{{- if .Values.volumeMounts }}
{{ toYaml .Values.volumeMounts | trim }}
{{- end }}
{{- if .Values.nodeAgent.volumeMounts }}
{{ toYaml .Values.nodeAgent.volumeMounts | trim }}
{{- end }}
- name: {{ .components.cloudSecret.name }}
  mountPath: /etc/credentials
  readOnly: true
- name: {{ .Values.global.cloudConfig }}
  mountPath: /etc/config/clusterData.json
  readOnly: true
  subPath: "clusterData.json"
{{- if .components.serviceDiscovery.enabled }}
- name: "services"
  mountPath: /etc/config/services.json
  readOnly: true
  subPath: "services.json"
{{- end }}
- name: config
  mountPath: /etc/config/config.json
  readOnly: true
  subPath: "config.json"
{{- if ne .Values.global.proxySecretFile "" }}
- name: proxy-secret
  mountPath: /etc/ssl/certs/proxy.crt
  subPath: proxy.crt
  readOnly: true
{{- end }}
{{- if .Values.global.overrideDefaultCaCertificates.enabled }}
- name: custom-ca-certificates
  mountPath: /etc/ssl/certs/ca-certificates.crt
  subPath: ca-certificates.crt
  readOnly: true
{{- end }}
{{- if .Values.global.extraCaCertificates.enabled }}
{{- range $key, $value := (lookup "v1" "Secret" .Values.ksNamespace .Values.global.extraCaCertificates.secretName).data }}
- name: extra-ca-certificates
  mountPath: /etc/ssl/certs/{{ $key }}
  subPath: {{ $key }}
  readOnly: true
{{- end }}
{{- end }}
{{- end -}}

{{/*
Node Agent Container
Parameters:
  - Values: .Values
  - components: $components
  - no_proxy_envar_list: the no_proxy list
  - autoscalerMode: boolean
  - testingMode: boolean
  - resources: resources object (when autoscalerMode is false)
  - indent: base indentation level
*/}}
{{- define "node-agent.container" -}}
- name: {{ .Values.nodeAgent.name }}
  image: "{{ .Values.nodeAgent.image.repository }}:{{ .Values.nodeAgent.image.tag }}"
  imagePullPolicy: {{ .Values.nodeAgent.image.pullPolicy }}
  livenessProbe:
    httpGet:
      path: /livez
      port: 7888
    initialDelaySeconds: 60
    periodSeconds: 3
  readinessProbe:
    httpGet:
      path: /readyz
      port: 7888
    initialDelaySeconds: 3
    periodSeconds: 3
  resources:
    {{- include "node-agent.resources" (dict "autoscalerMode" .autoscalerMode "resources" .resources) | nindent 4 }}
  env:
    {{- include "node-agent.env" (dict "Values" .Values "components" .components "no_proxy_envar_list" .no_proxy_envar_list "autoscalerMode" .autoscalerMode "testingMode" .testingMode) | nindent 4 }}
  securityContext:
    runAsUser: 0
    privileged: {{ .Values.nodeAgent.privileged }}
    capabilities:
      add:
        - SYS_ADMIN
        - SYS_PTRACE
        - NET_ADMIN
        - SYSLOG
        - SYS_RESOURCE
        - IPC_LOCK
        - NET_RAW
    seLinuxOptions:
      type: {{ .Values.nodeAgent.seLinuxType }}
  volumeMounts:
    {{- include "node-agent.volumeMounts" (dict "Values" .Values "components" .components) | nindent 4 }}
{{- end -}}

{{/*
ClamAV Container (optional)
Parameters:
  - Values: .Values
  - components: $components
*/}}
{{- define "node-agent.clamavContainer" -}}
{{- if .components.clamAV.enabled }}
- name: {{ .Values.clamav.name }}
  image: "{{ .Values.clamav.image.repository }}:{{ .Values.clamav.image.tag }}"
  imagePullPolicy: {{ .Values.clamav.image.pullPolicy }}
  securityContext:
    runAsUser: 0
    capabilities:
      add:
        - SYS_PTRACE
  resources:
{{ toYaml .Values.clamav.resources | indent 4 }}
  {{- if .Values.clamav.volumeMounts }}
  volumeMounts:
    {{- toYaml .Values.clamav.volumeMounts | nindent 4 }}
  {{- end }}
{{- end }}
{{- end -}}

{{/*
Node Agent Init Containers
Parameters:
  - Values: .Values
  - components: $components
  - no_proxy_envar_list: the no_proxy list
*/}}
{{- define "node-agent.initContainers" -}}
{{- if .Values.nodeAgent.startupJitterContainer.enabled }}
- name: startup-jitter
  image: "busybox:latest"
  command:
  - /bin/sh
  - -c
  - |
    SLEEP_TIME=$(( $RANDOM % {{ .Values.nodeAgent.startupJitterContainer.maxStartupJitter }} ))
    echo "Pod $(hostname) will sleep for $SLEEP_TIME seconds"
    sleep $SLEEP_TIME
    echo "Pod $(hostname) finished sleeping after $SLEEP_TIME seconds"
{{- end }}
{{- if .components.serviceDiscovery.enabled }}
- name: {{ .Values.serviceDiscovery.urlDiscovery.name }}
  image: "{{ .Values.serviceDiscovery.urlDiscovery.image.repository }}:{{ .Values.serviceDiscovery.urlDiscovery.image.tag }}"
  imagePullPolicy: {{ .Values.serviceDiscovery.urlDiscovery.image.pullPolicy }}
  securityContext:
    allowPrivilegeEscalation: false
    readOnlyRootFilesystem: true
  resources:
{{ toYaml .Values.serviceDiscovery.resources | indent 4 }}
  env:
{{- if ne .Values.global.httpsProxy "" }}
    - name: HTTPS_PROXY
      value: "{{ .Values.global.httpsProxy }}"
    - name: no_proxy
      value: "{{ .no_proxy_envar_list }}"
{{- end }}
  args:
    - -method=get
    - -scheme=https
    - -host={{ .Values.server }}
    - -path=api/v3/servicediscovery
    - -path-output=/data/services.json
{{- if .Values.serviceDiscovery.urlDiscovery.insecureSkipTLSVerify }}
    - -skip-ssl-verify=true
{{- end }}
  volumeMounts:
    - name: services
      mountPath: /data
{{- if ne .Values.global.proxySecretFile "" }}
    - name: proxy-secret
      mountPath: /etc/ssl/certs/proxy.crt
      subPath: proxy.crt
{{- end }}
{{- end }}
{{- end -}}

{{/*
Node Agent Volumes
Parameters:
  - Values: .Values
  - components: $components
*/}}
{{- define "node-agent.volumes" -}}
{{- if .Values.nodeAgent.volumes }}
{{ toYaml .Values.nodeAgent.volumes | trim }}
{{- end }}
{{- if .Values.volumes }}
{{ toYaml .Values.volumes | trim }}
{{- end }}
{{- if .Values.clamav.volumes }}
{{ toYaml .Values.clamav.volumes | trim }}
{{- end }}
- name: {{ .components.cloudSecret.name }}
  secret:
    secretName: {{ .components.cloudSecret.name }}
- name: {{ .Values.global.cloudConfig }}
  configMap:
    name: {{ .Values.global.cloudConfig }}
    items:
      - key: "clusterData"
        path: "clusterData.json"
- name: config
  configMap:
    name: {{ .Values.nodeAgent.name }}
    items:
      - key: "config.json"
        path: "config.json"
{{- if .components.serviceDiscovery.enabled }}
- name: "services"
  emptyDir: {}
{{- end }}
{{- if ne .Values.global.proxySecretFile "" }}
- name: proxy-secret
  secret:
    secretName: {{ .Values.global.proxySecretName }}
{{- end }}
{{- if .Values.global.overrideDefaultCaCertificates.enabled }}
- name: custom-ca-certificates
  secret:
    secretName: {{ .components.customCaCertificates.name }}
{{- end }}
{{- if .Values.global.extraCaCertificates.enabled }}
- name: extra-ca-certificates
  secret:
    secretName: {{ .Values.global.extraCaCertificates.secretName }}
{{- end }}
{{- end -}}

{{/*
Node Agent Pod Template Metadata Annotations
Parameters:
  - Values: .Values
  - checksums: $checksums
  - Capabilities: .Capabilities
  - autoscalerMode: boolean
  - nodeGroupLabel: string (for autoscaler mode)
*/}}
{{- define "node-agent.podAnnotations" -}}
{{- include "kubescape-operator.annotations" (dict "Values" .Values) }}
{{- with .Values.nodeAgent.podAnnotations }}
{{ toYaml . }}
{{- end }}
checksum/node-agent-config: {{ .checksums.nodeAgentConfig }}
checksum/cloud-secret: {{ .checksums.cloudSecret }}
checksum/cloud-config: {{ .checksums.cloudConfig }}
{{- if ne .Values.global.proxySecretFile "" }}
checksum/proxy-config: {{ .checksums.proxySecret }}
{{- end }}
{{- if lt (.Capabilities.KubeVersion.Minor | int) 29 }}
container.apparmor.security.beta.kubernetes.io/{{ .Values.nodeAgent.name }}: unconfined
{{- end }}
{{- if eq .Values.configurations.prometheusAnnotations "enable" }}
prometheus.io/path: /metrics
prometheus.io/port: "8080"
prometheus.io/scrape: "true"
{{- end }}
{{- end -}}

{{/*
Node Agent Pod Template Metadata Labels
Parameters:
  - Chart: .Chart
  - Release: .Release
  - Values: .Values
  - components: $components
  - autoscalerMode: boolean
  - nodeGroupLabel: string (for autoscaler mode)
*/}}
{{- define "node-agent.podLabels" -}}
{{- include "kubescape-operator.labels" (dict "Chart" .Chart "Release" .Release "Values" .Values "app" .Values.nodeAgent.name "tier" .Values.global.namespaceTier) }}
{{- with .Values.nodeAgent.podLabels }}
{{ toYaml . }}
{{- end }}
{{- if .Values.nodeAgent.gke.allowlist.enabled }}
cloud.google.com/matching-allowlist: {{ .Values.nodeAgent.gke.allowlist.name }}
{{- end }}
kubescape.io/tier: "core"
{{- if .autoscalerMode }}
kubescape.io/node-group: "{{`{{ .NodeGroupLabel }}`}}"
{{- end }}
{{- if .components.otelCollector.enabled }}
otel: enabled
{{- end }}
{{- end -}}

{{/*
Node Agent Pod Spec
Parameters:
  - Values: .Values
  - Chart: .Chart
  - Release: .Release
  - Capabilities: .Capabilities
  - components: $components
  - checksums: $checksums
  - no_proxy_envar_list: the no_proxy list
  - autoscalerMode: boolean
  - testingMode: boolean (for MULTIPLY env var and testing features)
  - resources: resources object (when autoscalerMode is false)
  - nodeSelector: optional custom nodeSelector
  - includeClamAV: boolean - whether to include ClamAV container
*/}}
{{- define "node-agent.podSpec" -}}
securityContext:
  {{- if ge (.Capabilities.KubeVersion.Minor | int) 29 }}
  appArmorProfile:
    type: Unconfined
  {{- end }}
{{- if .Values.imagePullSecrets }}
imagePullSecrets:
{{- if kindIs "string" .Values.imagePullSecrets }}
- name: {{ .Values.imagePullSecrets }}
{{- else }}
{{- range .Values.imagePullSecrets }}
- name: {{ . }}
{{- end }}
{{- end }}
{{- end }}
{{- if .Values.configurations.priorityClass.enabled }}
priorityClassName: kubescape-critical
{{- end }}
serviceAccountName: {{ .Values.nodeAgent.name }}
automountServiceAccountToken: true
hostPID: true
{{- $initContainers := include "node-agent.initContainers" (dict "Values" .Values "components" .components "no_proxy_envar_list" .no_proxy_envar_list) | trim }}
{{- if $initContainers }}
initContainers:
{{ $initContainers | nindent 0 }}
{{- end }}
volumes:
{{ include "node-agent.volumes" (dict "Values" .Values "components" .components) | trim | nindent 0 }}
containers:
{{- if .includeClamAV }}
{{ include "node-agent.clamavContainer" (dict "Values" .Values "components" .components) | trim | nindent 0 }}
{{- end }}
{{ include "node-agent.container" (dict "Values" .Values "components" .components "no_proxy_envar_list" .no_proxy_envar_list "autoscalerMode" .autoscalerMode "testingMode" .testingMode "resources" .resources) | trim | nindent 0 }}
nodeSelector:
{{- if .autoscalerMode }}
  kubernetes.io/os: linux
  {{ .Values.nodeAgent.autoscaler.nodeGroupLabel }}: "{{`{{ .NodeGroupLabel }}`}}"
{{- else if .nodeSelector }}
{{ toYaml .nodeSelector | nindent 2 }}
{{- else if .Values.nodeAgent.nodeSelector }}
{{ toYaml .Values.nodeAgent.nodeSelector | nindent 2 }}
{{- else if .Values.customScheduling.nodeSelector }}
{{ toYaml .Values.customScheduling.nodeSelector | nindent 2 }}
{{- end }}
affinity:
{{- if .Values.nodeAgent.affinity }}
{{ toYaml .Values.nodeAgent.affinity | nindent 2 }}
{{- else if and (not .autoscalerMode) .Values.customScheduling.affinity }}
{{ toYaml .Values.customScheduling.affinity | nindent 2 }}
{{- end }}
tolerations:
{{- if .Values.nodeAgent.tolerations }}
{{ toYaml .Values.nodeAgent.tolerations | nindent 2 }}
{{- else if .Values.customScheduling.tolerations }}
{{ toYaml .Values.customScheduling.tolerations | nindent 2 }}
{{- end }}
{{- end -}}

{{/*
Full Node Agent DaemonSet Spec (selector + template)
Parameters:
  - all parameters from node-agent.podSpec plus:
  - selectorLabels: additional selector labels (for autoscaler mode)
*/}}
{{- define "node-agent.daemonsetSpec" -}}
selector:
  matchLabels:
    {{- include "kubescape-operator.selectorLabels" (dict "Chart" .Chart "Release" .Release "Values" .Values "app" .Values.nodeAgent.name) | nindent 4 }}
    {{- if .autoscalerMode }}
    kubescape.io/node-group: "{{`{{ .NodeGroupLabel }}`}}"
    {{- end }}
template:
  metadata:
    annotations:
      {{- include "node-agent.podAnnotations" (dict "Values" .Values "checksums" .checksums "Capabilities" .Capabilities "autoscalerMode" .autoscalerMode) | nindent 6 }}
    labels:
      {{- include "node-agent.podLabels" (dict "Chart" .Chart "Release" .Release "Values" .Values "components" .components "autoscalerMode" .autoscalerMode) | nindent 6 }}
  spec:
    {{- include "node-agent.podSpec" (dict "Values" .Values "Chart" .Chart "Release" .Release "Capabilities" .Capabilities "components" .components "checksums" .checksums "no_proxy_envar_list" .no_proxy_envar_list "autoscalerMode" .autoscalerMode "testingMode" .testingMode "resources" .resources "nodeSelector" .nodeSelector "includeClamAV" .includeClamAV) | nindent 4 }}
{{- end -}}

