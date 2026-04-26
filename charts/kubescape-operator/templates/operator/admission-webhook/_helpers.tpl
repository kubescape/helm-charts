{{- define "kubescape-admission.name" -}}
kubescape-admission-webhook
{{- end }}

{{- define "kubescape-admission.secretName" -}}
{{- $strategy := default "helm" .Values.certificates.strategy -}}
{{- if eq $strategy "hook" -}}
{{- include "kubescape-admission.name" . -}}
{{- else -}}
{{- include "kubescape-admission.templatedSecretName" . -}}
{{- end }}

{{- define "kubescape-admission.templatedSecretName" -}}
{{- printf "%s-leaf" (include "kubescape-admission.name" .) -}}
{{- end }}

{{- define "kubescape-admission.templatedCaSecretName" -}}
{{- printf "%s-ca" (include "kubescape-admission.name" .) -}}
{{- end }}

{{- define "kubescape-admission.svcName" -}}
{{- printf "kubescape-admission-webhook.%s.svc" .Values.ksNamespace -}}
{{- end }}

{{- define "kubescape-admission.certificateData" -}}
{{- $svcName := (include "kubescape-admission.svcName" .) -}}
{{- $ca := dict "Key" "mock-ca-key" "Cert" "mock-ca-cert" -}}
{{- $cert := dict "Key" "mock-cert-key" "Cert" "mock-cert-cert" -}}
{{- if not .Values.unittest }}
  {{- $existingCASecret := (lookup "v1" "Secret" .Values.ksNamespace (include "kubescape-admission.templatedCaSecretName" .)) -}}
  {{- if and $existingCASecret $existingCASecret.data -}}
    {{- $_ := set $ca "Key" (index $existingCASecret.data "tls.key" | b64dec) -}}
    {{- $_ := set $ca "Cert" (index $existingCASecret.data "tls.crt" | b64dec) -}}
    {{- $existingCA := buildCustomCert ($ca.Cert | b64enc) ($ca.Key | b64enc) -}}
    {{/* Leaf cert validity: 10 years (3650 days). After expiry, delete the kubescape-admission-ca Secret and run helm upgrade to regenerate. */}}
    {{- $generatedCert := genSignedCert $svcName nil (list $svcName) 3650 $existingCA -}}
    {{- $_ := set $cert "Key" $generatedCert.Key -}}
    {{- $_ := set $cert "Cert" $generatedCert.Cert -}}
  {{- else -}}
    {{/* CA and leaf cert validity: 10 years (3650 days). After expiry, delete the kubescape-admission-ca Secret and run helm upgrade to regenerate. */}}
    {{- $generatedCA := genCA (printf "*.%s.svc" .Values.ksNamespace) 3650 -}}
    {{- $generatedCert := genSignedCert $svcName nil (list $svcName) 3650 $generatedCA -}}
    {{- $_ := set $ca "Key" $generatedCA.Key -}}
    {{- $_ := set $ca "Cert" $generatedCA.Cert -}}
    {{- $_ := set $cert "Key" $generatedCert.Key -}}
    {{- $_ := set $cert "Cert" $generatedCert.Cert -}}
  {{- end -}}
{{- end -}}
{{- $certData := dict "ca" $ca "cert" $cert -}}
{{- toYaml $certData -}}
{{- end -}}
