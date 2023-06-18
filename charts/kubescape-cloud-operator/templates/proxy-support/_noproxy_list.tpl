{{- define "no_proxy_envar_list" -}}
    {{ $api_server_ip := "127.0.0.1" }}
    {{- $api_server_service := (lookup "v1" "Service" "default" "kubernetes") -}}
    {{- if $api_server_service -}}
      {{ $api_server_ip = $api_server_service.spec.clusterIP }}        
    {{- end -}}
    {{ .Values.gateway.name }},{{ .Values.kubescape.name }},{{ .Values.kubevuln.name }},{{ .Values.nodeAgent.name }},{{ .Values.operator.name }},otel-collector,kubernetes.default.svc.*,{{ $api_server_ip }}
{{- end -}}
