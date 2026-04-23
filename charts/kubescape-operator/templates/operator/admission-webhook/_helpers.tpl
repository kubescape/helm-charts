{{- define "kubescape-admission.name" -}}
kubescape-admission-webhook
{{- end }}

{{- define "kubescape-admission.secretName" -}}
{{- include "kubescape-admission.name" . -}}
{{- end }}

{{- define "kubescape-admission.svcName" -}}
{{- printf "kubescape-admission-webhook.%s.svc" .Values.ksNamespace -}}
{{- end }}

{{- define "kubescape-admission.legacySecretName" -}}
{{- printf "%s-kubescape-tls-pair" (include "kubescape-admission.svcName" .) -}}
{{- end }}

{{- define "kubescape-admission.caSecretName" -}}
kubescape-admission-ca
{{- end }}

{{- define "kubescape-admission.certificateData" -}}
{{- $secretName := include "kubescape-admission.secretName" . -}}
{{- if not (hasKey .Values.global "_admissionCertificateData") -}}
{{- $_ := set .Values.global "_admissionCertificateData" dict -}}
{{- end -}}
{{- $cache := .Values.global._admissionCertificateData -}}
{{- if hasKey $cache $secretName -}}
{{- get $cache $secretName | toJson -}}
{{- else -}}
{{- $serviceName := include "kubescape-admission.name" . -}}
{{- $serviceFQDN := include "kubescape-admission.svcName" . -}}
{{- $data := dict "caCrt" "mock-ca-cert" "tlsCrt" "mock-cert-cert" "tlsKey" "mock-cert-key" -}}
{{- $currentSecret := lookup "v1" "Secret" .Values.ksNamespace $secretName -}}
{{- if and $currentSecret $currentSecret.data (hasKey $currentSecret.data "ca.crt") (hasKey $currentSecret.data "tls.crt") (hasKey $currentSecret.data "tls.key") -}}
{{- $_ := set $data "caCrt" (index $currentSecret.data "ca.crt" | b64dec) -}}
{{- $_ := set $data "tlsCrt" (index $currentSecret.data "tls.crt" | b64dec) -}}
{{- $_ := set $data "tlsKey" (index $currentSecret.data "tls.key" | b64dec) -}}
{{- else -}}
{{- $legacyCASecret := lookup "v1" "Secret" .Values.ksNamespace (include "kubescape-admission.caSecretName" .) -}}
{{- $legacyLeafSecret := lookup "v1" "Secret" .Values.ksNamespace (include "kubescape-admission.legacySecretName" .) -}}
{{- if and $legacyCASecret $legacyCASecret.data $legacyLeafSecret $legacyLeafSecret.data (hasKey $legacyCASecret.data "tls.crt") (hasKey $legacyLeafSecret.data "tls.crt") (hasKey $legacyLeafSecret.data "tls.key") -}}
{{- $_ := set $data "caCrt" (index $legacyCASecret.data "tls.crt" | b64dec) -}}
{{- $_ := set $data "tlsCrt" (index $legacyLeafSecret.data "tls.crt" | b64dec) -}}
{{- $_ := set $data "tlsKey" (index $legacyLeafSecret.data "tls.key" | b64dec) -}}
{{- else if not .Values.unittest -}}
{{- $ca := genCA (printf "%s-ca" $secretName) 3650 -}}
{{- $cert := genSignedCert $serviceFQDN nil (list $serviceName $serviceFQDN (printf "%s.cluster.local" $serviceFQDN)) 3650 $ca -}}
{{- $_ := set $data "caCrt" $ca.Cert -}}
{{- $_ := set $data "tlsCrt" $cert.Cert -}}
{{- $_ := set $data "tlsKey" $cert.Key -}}
{{- end -}}
{{- end -}}
{{- $_ := set $cache $secretName $data -}}
{{- $data | toJson -}}
{{- end -}}
{{- end }}
