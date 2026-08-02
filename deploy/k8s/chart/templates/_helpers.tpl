{{/*
Expand the name of the chart.
*/}}
{{- define "repave.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "repave.fullname" -}}
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

{{- define "repave.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "repave.labels" -}}
helm.sh/chart: {{ include "repave.chart" . }}
{{ include "repave.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "repave.selectorLabels" -}}
app.kubernetes.io/name: {{ include "repave.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "repave.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "repave.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "repave.image" -}}
{{- if .Values.image.digest }}
{{- printf "%s@%s" .Values.image.repository .Values.image.digest }}
{{- else }}
{{- $tag := default .Chart.AppVersion .Values.image.tag -}}
{{- printf "%s:%s" .Values.image.repository $tag }}
{{- end }}
{{- end }}

{{- define "repave.workerImage" -}}
{{- $repo := default "ghcr.io/opsdevcode/repave-engine" .Values.workerImage.repository -}}
{{- if .Values.workerImage.digest }}
{{- printf "%s@%s" $repo .Values.workerImage.digest }}
{{- else }}
{{- $tag := default (default .Chart.AppVersion .Values.image.tag) .Values.workerImage.tag -}}
{{- printf "%s:%s" $repo $tag }}
{{- end }}
{{- end }}

{{- define "repave.corpusImage" -}}
{{- if .Values.corpus.digest }}
{{- printf "%s@%s" .Values.corpus.repository .Values.corpus.digest }}
{{- else }}
{{- $tag := default .Chart.AppVersion .Values.corpus.tag -}}
{{- printf "%s:%s" .Values.corpus.repository $tag }}
{{- end }}
{{- end }}

{{- define "repave.corpusInitContainer" -}}
{{- if .Values.corpus.enabled }}
- name: corpus-init
  image: {{ include "repave.corpusImage" . }}
  imagePullPolicy: {{ .Values.corpus.pullPolicy }}
  command:
    - /bin/sh
    - -c
    - cp -a /app/. /corpus-data/
  volumeMounts:
    - name: corpus-data
      mountPath: /corpus-data
{{- end }}
{{- end }}

{{- define "repave.corpusVolumeMounts" -}}
{{- if .Values.corpus.enabled }}
- name: corpus-data
  mountPath: /app/schemas
  subPath: schemas
- name: corpus-data
  mountPath: /app/blueprints
  subPath: blueprints
- name: corpus-data
  mountPath: /app/standards
  subPath: standards
- name: corpus-data
  mountPath: /app/policy
  subPath: policy
{{- end }}
{{- end }}

{{- define "repave.corpusVolume" -}}
{{- if .Values.corpus.enabled }}
- name: corpus-data
  emptyDir: {}
{{- end }}
{{- end }}

{{- define "repave.githubAuthEnv" -}}
{{- $secretName := include "repave.secretName" . }}
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

{{- define "repave.secretName" -}}
{{- if .Values.secrets.existingSecret }}
{{- .Values.secrets.existingSecret }}
{{- else if .Values.secrets.create }}
{{- include "repave.fullname" . }}
{{- else }}
{{- "" }}
{{- end }}
{{- end }}

{{- define "repave.environmentVendingEnabled" -}}
{{- and .Values.repave.environmentVending.enabled .Values.repave.environmentVending.gitopsRepo }}
{{- end }}

{{- define "repave.environmentRegistryMountPath" -}}
{{- $file := .Values.repave.environmentVending.file | default "/data/environments/registry.jsonl" -}}
{{- dir $file -}}
{{- end }}

{{- define "repave.environmentDataVolumeMount" -}}
{{- if include "repave.environmentVendingEnabled" . }}
- name: environments
  mountPath: {{ include "repave.environmentRegistryMountPath" . | quote }}
{{- end }}
{{- end }}

{{- define "repave.environmentDataVolume" -}}
{{- if include "repave.environmentVendingEnabled" . }}
- name: environments
  {{- if .Values.persistence.environments.existingClaim }}
  persistentVolumeClaim:
    claimName: {{ .Values.persistence.environments.existingClaim }}
  {{- else if .Values.persistence.environments.enabled }}
  persistentVolumeClaim:
    claimName: {{ include "repave.fullname" . }}-environments
  {{- else }}
  emptyDir: {}
  {{- end }}
{{- end }}
{{- end }}

{{- define "repave.environmentVendingEnv" -}}
{{- if include "repave.environmentVendingEnabled" . }}
- name: REPAVE_ENVIRONMENT_VENDING
  value: "1"
- name: REPAVE_ENVIRONMENT_REGISTRY_FILE
  value: {{ .Values.repave.environmentVending.file | quote }}
{{- end }}
{{- end }}
