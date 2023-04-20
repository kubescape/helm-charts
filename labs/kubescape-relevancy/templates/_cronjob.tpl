{{/* calc values for kubescape cronjobs */}}
{{- define "kubescape_daily_scan_cron_tab_minute" -}}   
{{  mod (randNumeric 2) 60 }}
{{- end }}

{{- define "kubescape_daily_scan_cron_tab_hour" -}}
{{mod (randNumeric 2) 24 }}
{{- end }}

{{- define "kubescape_daily_scan_cron_tab" -}}
  {{- if eq .Values.kubescapeScheduler.scanSchedule "0 8 * * *" -}}
    {{- $existingSchedule := (lookup "batch/v1" "CronJob" .Values.ksNamespace .Values.kubescapeScheduler.name) -}}
    {{- if $existingSchedule -}}
      {{ $existingSchedule.spec.schedule }}
    {{- else -}}
      {{- $kubescape_daily_scan_cron_tab_minute := (include "kubescape_daily_scan_cron_tab_minute" .) -}}
      {{- $kubescape_daily_scan_cron_tab_hour := (include "kubescape_daily_scan_cron_tab_hour" .) -}}
      {{ trimPrefix "\n" (trimSuffix  "\n" $kubescape_daily_scan_cron_tab_minute) }} {{ trimPrefix "\n" (trimSuffix  "\n" $kubescape_daily_scan_cron_tab_hour) }} * * *
    {{- end -}}
  {{- else -}}
    {{- .Values.kubescapeScheduler.scanSchedule -}}
  {{- end -}}
{{- end }}





{{/* calc values for kube-vuln cronjobs */}}
{{- define "kubevuln_daily_scan_cron_tab_minute" -}}   
{{  mod (randNumeric 2) 60 }}
{{- end }}

{{- define "kubevuln_daily_scan_cron_tab_hour" -}}
{{mod (randNumeric 2) 24 }}
{{- end }}


{{- define "kubevuln_daily_scan_cron_tab" -}}
  {{- if eq .Values.kubevulnScheduler.scanSchedule "0 0 * * *" -}}
    {{- $existingSchedule := (lookup "batch/v1" "CronJob" .Values.ksNamespace .Values.kubevulnScheduler.name) -}}
    {{- if $existingSchedule -}}
      {{ $existingSchedule.spec.schedule }}
    {{- else -}}
      {{- $kubescape_daily_scan_cron_tab_minute := (include "kubescape_daily_scan_cron_tab_minute" .) -}}
      {{- $kubescape_daily_scan_cron_tab_hour := (include "kubescape_daily_scan_cron_tab_hour" .) -}}
      {{ trimPrefix "\n" (trimSuffix  "\n" $kubescape_daily_scan_cron_tab_minute) }} {{ trimPrefix "\n" (trimSuffix  "\n" $kubescape_daily_scan_cron_tab_hour) }} * * *
    {{- end -}}
  {{- else -}}
    {{- .Values.kubevulnScheduler.scanSchedule -}}
  {{- end -}}
{{- end }}
