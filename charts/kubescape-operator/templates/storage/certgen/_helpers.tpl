{{- define "storage.certgen.name" -}}
{{- printf "%s-certgen" .Values.storage.name -}}
{{- end }}

{{- define "storage.certgen.secretName" -}}
{{- printf "%s-tls" .Values.storage.name -}}
{{- end }}

{{- define "storage.certgen.legacySecretName" -}}
{{- printf "%s-ca" .Values.storage.name -}}
{{- end }}

{{- define "storage.certgen.apiServiceName" -}}
v1beta1.spdx.softwarecomposition.kubescape.io
{{- end }}

{{- define "storage.certgen.certificateData" -}}
{{- $secretName := include "storage.certgen.secretName" . -}}
{{- if not (hasKey .Values.global "_storageCertificateData") -}}
{{- $_ := set .Values.global "_storageCertificateData" dict -}}
{{- end -}}
{{- $cache := .Values.global._storageCertificateData -}}
{{- if hasKey $cache $secretName -}}
{{- get $cache $secretName | toJson -}}
{{- else -}}
{{- $serviceName := .Values.storage.name -}}
{{- $serviceFQDN := printf "%s.%s.svc" .Values.storage.name .Values.ksNamespace -}}
{{- $data := dict "caCrt" "mock-ca-cert" "tlsCrt" "mock-cert-cert" "tlsKey" "mock-cert-key" -}}
{{- $currentSecret := lookup "v1" "Secret" .Values.ksNamespace $secretName -}}
{{- if and $currentSecret $currentSecret.data (hasKey $currentSecret.data "ca.crt") (hasKey $currentSecret.data "tls.crt") (hasKey $currentSecret.data "tls.key") -}}
{{- $_ := set $data "caCrt" (index $currentSecret.data "ca.crt" | b64dec) -}}
{{- $_ := set $data "tlsCrt" (index $currentSecret.data "tls.crt" | b64dec) -}}
{{- $_ := set $data "tlsKey" (index $currentSecret.data "tls.key" | b64dec) -}}
{{- else -}}
{{- $legacySecret := lookup "v1" "Secret" .Values.ksNamespace (include "storage.certgen.legacySecretName" .) -}}
{{- if and $legacySecret $legacySecret.data (hasKey $legacySecret.data "ca.crt") (hasKey $legacySecret.data "tls.crt") (hasKey $legacySecret.data "tls.key") -}}
{{- $_ := set $data "caCrt" (index $legacySecret.data "ca.crt" | b64dec) -}}
{{- $_ := set $data "tlsCrt" (index $legacySecret.data "tls.crt" | b64dec) -}}
{{- $_ := set $data "tlsKey" (index $legacySecret.data "tls.key" | b64dec) -}}
{{- else if not .Values.unittest -}}
{{- $validity := int .Values.storage.mtls.certificateValidityInDays -}}
{{- $ca := genCA (printf "%s-ca" $serviceName) $validity -}}
{{- $cert := genSignedCert $serviceFQDN nil (list $serviceName $serviceFQDN (printf "%s.cluster.local" $serviceFQDN)) $validity $ca -}}
{{- $_ := set $data "caCrt" $ca.Cert -}}
{{- $_ := set $data "tlsCrt" $cert.Cert -}}
{{- $_ := set $data "tlsKey" $cert.Key -}}
{{- end -}}
{{- end -}}
{{- $_ := set $cache $secretName $data -}}
{{- $data | toJson -}}
{{- end -}}
{{- end }}
