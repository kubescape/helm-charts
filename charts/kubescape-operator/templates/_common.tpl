{{/* validate alertCRD.scopeClustered and alertCRD.scopeNamespaced are mutual exclusive */}}
{{- if and .Values.alertCRD.scopeClustered .Values.alertCRD.scopeNamespaced }}
{{- fail "alertCRD.scopeClustered and alertCRD.scopeNamespaced cannot both be true" }}
{{- end }}

{{- define "checksums" -}}
capabilitiesConfig: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.configMapsDirectory "components-configmap.yaml") . | replace .Chart.AppVersion "" | sha256sum }}
cloudConfig: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.configMapsDirectory "cloudapi-configmap.yaml") . | replace .Chart.AppVersion "" | sha256sum }}
cloudSecret: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.configMapsDirectory "cloud-secret.yaml" ) . | replace .Chart.AppVersion "" | sha256sum }}
matchingRulesConfig: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.configMapsDirectory "matchingRules-configmap.yaml") . | replace .Chart.AppVersion "" | sha256sum }}
nodeAgentConfig: {{ include (printf "%s/node-agent/configmap.yaml" $.Template.BasePath) . | replace .Chart.AppVersion "" | sha256sum }}
operatorConfig: {{ include (printf "%s/operator/configmap.yaml" $.Template.BasePath) . | replace .Chart.AppVersion "" | sha256sum }}
proxySecret: {{ include (printf "%s/%s/%s" $.Template.BasePath $.Values.global.proxySecretDirectory "proxy-secret.yaml") . | replace .Chart.AppVersion "" | sha256sum }}
storageConfig: {{ include (printf "%s/storage/configmap.yaml" $.Template.BasePath) . | replace .Chart.AppVersion "" | sha256sum }}
synchronizerConfig: {{ include (printf "%s/synchronizer/configmap.yaml" $.Template.BasePath) . | replace .Chart.AppVersion "" | sha256sum }}
admissionCertgenScripts: {{ include (printf "%s/operator/admission-webhook/configmap.yaml" $.Template.BasePath) . | replace .Chart.AppVersion "" | sha256sum }}
storageCertgenScripts: {{ include (printf "%s/storage/certgen/configmap.yaml" $.Template.BasePath) . | replace .Chart.AppVersion "" | sha256sum }}
{{- end -}}


{{- define "configurations" -}}
{{- $createCloudSecret := (empty .Values.credentials.cloudSecret) -}}
{{- $submit := not (empty .Values.server) -}}
{{- $virtualCrds := not (empty .Values.storage.forceVirtualCrds) -}}
continuousScan: {{ and (eq .Values.capabilities.continuousScan "enable") (not $submit) }}
createCloudSecret: {{ $createCloudSecret }}
runtimeObservability: {{ eq .Values.capabilities.runtimeObservability "enable" }}
backendStorageEnabled: {{ eq (index .Values.capabilities "backend-storage" | default "") "enable" }}
virtualCrds: {{ or $virtualCrds (not $submit) }}
submit: {{ $submit }}
  {{- if $submit -}}
    {{- if and (empty .Values.account) $createCloudSecret -}}
      {{- fail "submitting is enabled but value for account is not defined: please register at https://cloud.armosec.io to get yours and re-run with  --set account=<your Guid>" }}
    {{- end -}}
    {{- if and (empty .Values.accessKey) $createCloudSecret -}}
      {{- fail "submitting is enabled but value for accessKey is not defined: To obtain an access key, go to 'Settings' -> 'Agent Access Keys' at https://cloud.armosec.io and re-run with  --set accessKey=<your key>" }}
    {{- end -}}
    {{- if empty .Values.clusterName -}}
      {{- fail "value for clusterName is not defined: re-run with  --set clusterName=<your cluster name>" }}
    {{- end -}}
  {{- end -}}
{{- end -}}

{{- define "kubescape.schedulerRequestBody" -}}
{{- $requestBody := deepCopy (.Values.kubescapeScheduler.requestBody | default (dict)) -}}
{{- if eq .Values.capabilities.kubescapeOffline "enable" -}}
  {{- $commands := list -}}
  {{- range $command := ($requestBody.commands | default (list)) -}}
    {{- $renderedCommand := deepCopy $command -}}
    {{- $args := $renderedCommand.args | default (dict) -}}
    {{- if hasKey $args "scanV1" -}}
      {{- $scanV1 := $args.scanV1 | default (dict) -}}
      {{- $_ := set $scanV1 "keepLocal" true -}}
      {{- $_ := set $args "scanV1" $scanV1 -}}
      {{- $_ := set $renderedCommand "args" $args -}}
    {{- end -}}
    {{- $commands = append $commands $renderedCommand -}}
  {{- end -}}
  {{- $_ := set $requestBody "commands" $commands -}}
{{- end -}}
{{- $requestBody | toJson -}}
{{- end -}}

{{- define "components" -}}
{{- $configurations := fromYaml (include "configurations" .) }}
{{- $nodeScanEnabled := and (eq .Values.capabilities.nodeScan "enable") (not $configurations.backendStorageEnabled) }}
{{- $configurationScanEnabled := and (eq .Values.capabilities.configurationScan "enable") (not $configurations.backendStorageEnabled) }}
{{- $vulnerabilityScanEnabled := and (eq .Values.capabilities.vulnerabilityScan "enable") (not $configurations.backendStorageEnabled) }}
kubescape:
  enabled: {{ $configurationScanEnabled }}
kubescapeScheduler:
  enabled: {{ $configurationScanEnabled }}
kubevuln:
  enabled: {{ $vulnerabilityScanEnabled }}
kubevulnScheduler:
  enabled: {{ $vulnerabilityScanEnabled }}
nodeAgent:
  enabled: {{ or
   (eq .Values.capabilities.relevancy "enable")
   (eq .Values.capabilities.runtimeObservability "enable")
   (eq .Values.capabilities.networkPolicyService "enable")
   (eq .Values.capabilities.runtimeDetection "enable")
   (eq .Values.capabilities.malwareDetection "enable")
   (eq .Values.capabilities.nodeProfileService "enable")
   (eq .Values.capabilities.seccompProfileService "enable")
  }}
operator:
  enabled: {{ eq .Values.capabilities.operator "enable" }}
serviceDiscovery:
  enabled: {{ $configurations.submit }}
storage:
  enabled: {{ not $configurations.backendStorageEnabled }}
prometheusExporter:
  enabled: {{ eq .Values.capabilities.prometheusExporter "enable" }}
cloudSecret:
  create: {{ $configurations.createCloudSecret }}
  name: {{ if $configurations.createCloudSecret }}"cloud-secret"{{ else }}{{ .Values.credentials.cloudSecret }}{{ end }}
synchronizer:
  enabled: {{ $configurations.submit }}
clamAV:
  enabled: {{ eq .Values.capabilities.malwareDetection "enable" }}
sbomScanner:
  enabled: {{ and (eq .Values.capabilities.nodeSbomGeneration "enable") .Values.nodeAgent.sbomScanner.enabled }}
customCaCertificates:
  name: custom-ca-certificates
autoUpdater:
  enabled: {{ eq .Values.capabilities.autoUpgrading "enable" }}
{{- end -}}

{{/*
"capabilities.gates" is the single source of truth for capability flags that are
silently ANDed with an internal precondition before they reach a rendered
manifest. The node-agent configmap consumes the effective.* values, while the
ks-capabilities configmap and NOTES.txt consume effectiveCapabilities/warnings.
Because the gate logic lives here only, the rendered value and the warning about
that value can never drift apart. See issue #851.
*/}}
{{- define "capabilities.gates" -}}
{{- $c := .Values.capabilities -}}
{{- $configurations := fromYaml (include "configurations" .) -}}
{{- $submit := $configurations.submit -}}
{{- $synchronizerEnabled := (fromYaml (include "components" .)).synchronizer.enabled -}}
{{- $backendStorage := $configurations.backendStorageEnabled -}}
{{- $runtimeDetection := eq $c.runtimeDetection "enable" -}}
{{- $nodeProfileService := and $synchronizerEnabled (eq $c.nodeProfileService "enable") -}}
{{- $networkStreaming := and $submit (eq $c.networkEventsStreaming "enable") -}}
{{- $httpDetection := and (eq $c.httpDetection "enable") $runtimeDetection -}}
# effective.* are the node-agent config.json flags, consumed by node-agent/configmap.yaml
effective:
  nodeProfileServiceEnabled: {{ $nodeProfileService }}
  networkStreamingEnabled: {{ $networkStreaming }}
  httpDetectionEnabled: {{ $httpDetection }}
# effectiveCapabilities is requested-vs-effective per gated capability, consumed by ks-capabilities
effectiveCapabilities:
  nodeProfileService: {{ if $nodeProfileService }}enable{{ else }}disable{{ end }}
  networkEventsStreaming: {{ if $networkStreaming }}enable{{ else }}disable{{ end }}
  httpDetection: {{ if $httpDetection }}enable{{ else }}disable{{ end }}
  nodeScan: {{ if and (eq $c.nodeScan "enable") $backendStorage }}backend{{ else }}{{ $c.nodeScan }}{{ end }}
  configurationScan: {{ if and (eq $c.configurationScan "enable") $backendStorage }}backend{{ else }}{{ $c.configurationScan }}{{ end }}
  vulnerabilityScan: {{ if and (eq $c.vulnerabilityScan "enable") $backendStorage }}backend{{ else }}{{ $c.vulnerabilityScan }}{{ end }}
warnings:
{{- if and (eq $c.nodeProfileService "enable") (not $nodeProfileService) }}
- "capabilities.nodeProfileService=enable but the backend is not configured (.Values.server is empty / submit is disabled). This capability requires the synchronizer, which is only enabled when connected to a backend, so nodeProfileServiceEnabled renders as FALSE in the node-agent configmap and node profiles will NOT be generated. To use it, set .Values.server (requires account and accessKey, or an existing credentials.cloudSecret)."
{{- end }}
{{- if and (eq $c.networkEventsStreaming "enable") (not $networkStreaming) }}
- "capabilities.networkEventsStreaming=enable but the backend is not configured (.Values.server is empty / submit is disabled). This capability requires submitting data to a backend, so networkStreamingEnabled renders as FALSE in the node-agent configmap and network events will NOT be streamed. To use it, set .Values.server (requires account and accessKey, or an existing credentials.cloudSecret)."
{{- end }}
{{- if and (eq $c.httpDetection "enable") (not $httpDetection) }}
- "capabilities.httpDetection=enable but capabilities.runtimeDetection is not enabled. HTTP detection runs on top of runtime detection, so httpDetectionEnabled renders as FALSE in the node-agent configmap. To use it, set capabilities.runtimeDetection=enable."
{{- end }}
{{- end -}}

{{- define "kubescape.certgen.scriptsHash" -}}
{{- printf "%s%s" (.Files.Get "scripts/certgen-create.sh") (.Files.Get "scripts/certgen-patch.sh") | sha256sum | trunc 8 -}}
{{- end }}

{{- define "kubescape.certificates.strategy" -}}
{{- $strategy := default "template" .Values.certificates.strategy -}}
{{- if not (has $strategy (list "template" "initContainer")) -}}
{{- fail (printf "certificates.strategy must be one of [template, initContainer], got %q" $strategy) -}}
{{- end -}}
{{- $strategy -}}
{{- end }}
