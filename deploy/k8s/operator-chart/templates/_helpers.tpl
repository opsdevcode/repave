{{/*
Expand the name of the chart.
*/}}
{{- define "repave-operator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "repave-operator.fullname" -}}
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

{{- define "repave-operator.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "repave-operator.labels" -}}
helm.sh/chart: {{ include "repave-operator.chart" . }}
{{ include "repave-operator.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: operator
{{- end }}

{{- define "repave-operator.selectorLabels" -}}
app.kubernetes.io/name: {{ include "repave-operator.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "repave-operator.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "repave-operator.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "repave-operator.image" -}}
{{- $tag := default .Chart.AppVersion .Values.image.tag -}}
{{- printf "%s:%s" .Values.image.repository $tag }}
{{- end }}

{{- define "repave-operator.webhookSecretName" -}}
{{- if .Values.webhook.existingSecret }}
{{- .Values.webhook.existingSecret }}
{{- else }}
{{- .Values.webhook.secretName }}
{{- end }}
{{- end }}

{{- define "repave-operator.secretName" -}}
{{- if .Values.secrets.existingSecret }}
{{- .Values.secrets.existingSecret }}
{{- else if .Values.secrets.create }}
{{- include "repave-operator.fullname" . }}
{{- else }}
{{- "" }}
{{- end }}
{{- end }}

{{- define "repave-operator.githubAuthEnv" -}}
{{- $secretName := include "repave-operator.secretName" . }}
{{- if $secretName }}
- name: GITHUB_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ $secretName }}
      key: github-token
      optional: true
- name: GITHUB_APP_ID
  valueFrom:
    secretKeyRef:
      name: {{ $secretName }}
      key: github-app-id
      optional: true
- name: GITHUB_APP_INSTALLATION_ID
  valueFrom:
    secretKeyRef:
      name: {{ $secretName }}
      key: github-app-installation-id
      optional: true
- name: GITHUB_APP_PRIVATE_KEY
  valueFrom:
    secretKeyRef:
      name: {{ $secretName }}
      key: github-app-private-key
      optional: true
{{- end }}
{{- end }}

{{- define "repave-operator.notifyEnv" -}}
{{- if .Values.notify.enabled }}
{{- if .Values.notify.slackWebhookUrl }}
- name: REPAVE_SLACK_WEBHOOK_URL
  value: {{ .Values.notify.slackWebhookUrl | quote }}
{{- end }}
{{- if .Values.notify.teamsWebhookUrl }}
- name: REPAVE_TEAMS_WEBHOOK_URL
  value: {{ .Values.notify.teamsWebhookUrl | quote }}
{{- end }}
{{- if .Values.notify.genericWebhookUrl }}
- name: REPAVE_NOTIFY_WEBHOOK_URL
  value: {{ .Values.notify.genericWebhookUrl | quote }}
{{- end }}
- name: REPAVE_OPERATOR_NOTIFY_ENABLED
  value: "true"
{{- if .Values.notify.events }}
- name: REPAVE_OPERATOR_NOTIFY_EVENTS
  value: {{ .Values.notify.events | quote }}
{{- end }}
{{- end }}
{{- end }}

{{- define "repave-operator.renderCrd" -}}
{{- $raw := .content -}}
{{- $raw = replace $raw "__OPERATOR_NAMESPACE__" .namespace -}}
{{- $raw = replace $raw "__WEBHOOK_SERVICE_NAME__" .serviceName -}}
{{- if .caBundle -}}
{{- $raw = replace $raw "__WEBHOOK_CA_BUNDLE__" (printf "caBundle: %s" .caBundle) -}}
{{- else -}}
{{- $raw = replace $raw "__WEBHOOK_CA_BUNDLE__" "" -}}
{{- end -}}
{{- $raw -}}
{{- end }}
