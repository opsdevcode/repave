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
{{- $tag := default .Chart.AppVersion .Values.image.tag -}}
{{- printf "%s:%s" .Values.image.repository $tag }}
{{- end }}

{{- define "repave.workerImage" -}}
{{- $repo := default "ghcr.io/opsdevcode/repave-engine" .Values.workerImage.repository -}}
{{- $tag := default (default .Chart.AppVersion .Values.image.tag) .Values.workerImage.tag -}}
{{- printf "%s:%s" $repo $tag }}
{{- end }}

{{- define "repave.corpusImage" -}}
{{- $tag := default .Chart.AppVersion .Values.corpus.tag -}}
{{- printf "%s:%s" .Values.corpus.repository $tag }}
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

{{- define "repave.secretName" -}}
{{- if .Values.secrets.existingSecret }}
{{- .Values.secrets.existingSecret }}
{{- else if .Values.secrets.create }}
{{- include "repave.fullname" . }}
{{- else }}
{{- "" }}
{{- end }}
{{- end }}
