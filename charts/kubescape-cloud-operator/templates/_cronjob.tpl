{{/* calc values for kubescape cronjobs */}}
{{- define "kubescape_daily_scan_cron_tab_minute" -}}
  {{- if eq .Values.kubescapeScheduler.scanSchedule "0 8 * * *" -}}
{{  mod (randNumeric 2) 60 }}
    {{- else -}}
{{- (split " " .Values.kubescapeScheduler.scanSchedule)._0 -}}
  {{- end -}}
{{- end }}

{{- define "kubescape_daily_scan_cron_tab_hour" -}}
{{if eq .Values.kubescapeScheduler.scanSchedule "0 8 * * *"}}
{{mod (randNumeric 2) 24 }}
{{ else}}
{{ (split " " .Values.kubescapeScheduler.scanSchedule)._1 }}
{{ end }}
{{- end }}

{{- define "kubescape_daily_scan_cron_tab_days" -}}
{{if eq .Values.kubescapeScheduler.scanSchedule "0 8 * * *"}}
* * *
{{ else}}
{{ (split " " .Values.kubescapeScheduler.scanSchedule)._2 }} {{ (split " " .Values.kubescapeScheduler.scanSchedule)._3 }} {{ (split " " .Values.kubescapeScheduler.scanSchedule)._4 }} 
{{ end }}
{{- end }}


{{- define "kubescape_daily_scan_cron_tab" -}}
{{- $kubescape_daily_scan_cron_tab_minute := (include "kubescape_daily_scan_cron_tab_minute" .) -}}
{{- $kubescape_daily_scan_cron_tab_hour := (include "kubescape_daily_scan_cron_tab_hour" .) -}}
{{- $kubescape_daily_scan_cron_tab_days := (include "kubescape_daily_scan_cron_tab_days" .) -}}
{{ trimPrefix "\n" (trimSuffix  "\n" $kubescape_daily_scan_cron_tab_minute) }} {{ trimPrefix "\n" (trimSuffix  "\n" $kubescape_daily_scan_cron_tab_hour) }} {{ trimPrefix "\n" (trimSuffix  "\n" $kubescape_daily_scan_cron_tab_days) }}
{{- end }}





{{/* calc values for kube-vuln cronjobs */}}
{{- define "kubevuln_daily_scan_cron_tab_minute" -}}
  {{- if eq .Values.kubescapeScheduler.scanSchedule "0 0 * * *" -}}
{{  mod (randNumeric 2) 60 }}
    {{- else -}}
{{- (split " " .Values.kubescapeScheduler.scanSchedule)._0 -}}
  {{- end -}}
{{- end }}

{{- define "kubevuln_daily_scan_cron_tab_hour" -}}
{{if eq .Values.kubevulnScheduler.scanSchedule "0 0 * * *"}}
{{mod (randNumeric 2) 24 }}
{{ else}}
{{ (split " " .Values.kubevulnScheduler.scanSchedule)._1 }}
{{ end }}
{{- end }}

{{- define "kubevuln_daily_scan_cron_tab_days" -}}
{{if eq .Values.kubevulnScheduler.scanSchedule "0 0 * * *"}}
* * *
{{ else}}
{{ (split " " .Values.kubevulnScheduler.scanSchedule)._2 }} {{ (split " " .Values.kubevulnScheduler.scanSchedule)._3 }} {{ (split " " .Values.kubevulnScheduler.scanSchedule)._4 }} 
{{ end }}
{{- end }}


{{- define "kubevuln_daily_scan_cron_tab" -}}
{{- $kubevuln_daily_scan_cron_tab_minute := (include "kubevuln_daily_scan_cron_tab_minute" .) -}}
{{- $kubevuln_daily_scan_cron_tab_hour := (include "kubevuln_daily_scan_cron_tab_hour" .) -}}
{{- $kubevuln_daily_scan_cron_tab_days := (include "kubevuln_daily_scan_cron_tab_days" .) -}}
{{ trimPrefix "\n" (trimSuffix  "\n" $kubevuln_daily_scan_cron_tab_minute) }} {{ trimPrefix "\n" (trimSuffix  "\n" $kubevuln_daily_scan_cron_tab_hour) }} {{ trimPrefix "\n" (trimSuffix  "\n" $kubevuln_daily_scan_cron_tab_days) }}
{{- end }}