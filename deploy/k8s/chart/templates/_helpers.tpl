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

{{- define "repave.portalSelectorLabels" -}}
{{- include "repave.selectorLabels" . }}
app.kubernetes.io/component: portal
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
- name: corpus-data
  mountPath: /app/ansible
  subPath: ansible
- name: corpus-data
  mountPath: /app/observability
  subPath: observability
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
{{- if not .Values.repave.github.preferApp }}
- name: GITHUB_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ $secretName }}
      key: github-token
      optional: true
{{- end }}
{{- if .Values.repave.github.preferApp }}
- name: REPAVE_PREFER_GITHUB_APP
  value: "1"
{{- end }}
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

{{- define "repave.apiTokenEnv" -}}
{{- $secretName := include "repave.secretName" . }}
{{- if $secretName }}
- name: REPAVE_API_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ $secretName }}
      key: api-token
      optional: true
{{- end }}
{{- end }}

{{- define "repave.stateStoreEnv" -}}
{{- if .Values.repave.stateStore.enabled }}
{{- if not .Values.repave.stateStore.databaseUrl }}
{{- fail "repave.stateStore.enabled requires repave.stateStore.databaseUrl (PostgreSQL 14+)" }}
{{- end }}
{{- $secretName := include "repave.secretName" . }}
{{- if not $secretName }}
{{- fail "repave.stateStore.enabled requires secrets.existingSecret or secrets.create (for REPAVE_STATE_KEK)" }}
{{- end }}
- name: REPAVE_STATE_STORE_URL
  value: {{ .Values.repave.stateStore.databaseUrl | quote }}
- name: REPAVE_STATE_STORE_TENANT
  value: {{ .Values.repave.stateStore.defaultTenant | quote }}
{{- if .Values.repave.stateStore.requiredGates }}
- name: REPAVE_STATE_REQUIRED_GATES
  value: {{ .Values.repave.stateStore.requiredGates | join "," | quote }}
{{- end }}
- name: REPAVE_STATE_KEK
  valueFrom:
    secretKeyRef:
      name: {{ $secretName }}
      key: state-kek
      optional: false
- name: REPAVE_STATE_KEK_ID
  valueFrom:
    secretKeyRef:
      name: {{ $secretName }}
      key: state-kek-id
      optional: true
{{- end }}
{{- end }}

{{- define "repave.environmentReclaimApiBaseUrl" -}}
{{- if .Values.environmentReclaim.cronJob.apiBaseUrl }}
{{- .Values.environmentReclaim.cronJob.apiBaseUrl }}
{{- else }}
{{- printf "http://%s:%v" (include "repave.fullname" .) .Values.service.port }}
{{- end }}
{{- end }}

{{- define "repave.databaseUrlEnv" -}}
{{- $secret := .Values.repave.durability.databaseUrlSecret -}}
{{- if and $secret.name $secret.key }}
- name: REPAVE_DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ $secret.name | quote }}
      key: {{ $secret.key | quote }}
{{- else if .Values.repave.durability.databaseUrl }}
- name: REPAVE_DATABASE_URL
  value: {{ .Values.repave.durability.databaseUrl | quote }}
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

{{- define "repave.fleetOperatorNamespace" -}}
{{- default .Release.Namespace .Values.fleetOperatorSnapshot.cronJob.operatorNamespace -}}
{{- end }}

{{- define "repave.fleetDataVolumeMount" -}}
{{- if .Values.repave.fleet.enabled }}
- name: fleet
  mountPath: /data/fleet
{{- end }}
{{- end }}

{{- define "repave.fleetDataVolume" -}}
{{- if .Values.repave.fleet.enabled }}
- name: fleet
  {{- if and .Values.persistence.fleet.enabled (not .Values.persistence.fleet.existingClaim) }}
  persistentVolumeClaim:
    claimName: {{ include "repave.fullname" . }}-fleet
  {{- else if .Values.persistence.fleet.existingClaim }}
  persistentVolumeClaim:
    claimName: {{ .Values.persistence.fleet.existingClaim }}
  {{- else }}
  emptyDir: {}
  {{- end }}
{{- end }}
{{- end }}
