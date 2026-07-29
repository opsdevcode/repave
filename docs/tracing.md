# OpenTelemetry tracing (pipeline spans)

Repave emits **OpenTelemetry spans** around pipeline stages (`validate`, `render`, `gates`,
`publish`) when a tracer provider is configured. Without configuration, spans are no-ops (API-only
`opentelemetry-api` dependency).

## Install the exporter

```bash
cd engine && uv sync --extra dev --extra otel
```

The **`otel`** optional extra adds `opentelemetry-sdk` and the OTLP/HTTP exporter.

## Configure export

**Environment (recommended for Kubernetes):**

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
export OTEL_SERVICE_NAME=repave-engine
```

Repave also accepts `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `REPAVE_OTEL_EXPORTER_OTLP_ENDPOINT`,
and `REPAVE_OTEL_SERVICE_NAME`.

**`repave.config.yaml`:**

```yaml
tracing:
  enabled: true
  otlp_endpoint: http://127.0.0.1:4318
  service_name: repave-engine
```

Environment endpoints override the file when set. The portal calls `configure_tracing` at startup
(`create_app`).

## Verify

Run a collector (for example Jaeger or the OpenTelemetry Collector) listening on OTLP HTTP
`:4318`, enable tracing as above, trigger a dry-run generation, and confirm spans named
`repave.engine` under stages such as `pipeline.validate` and `pipeline.gates`.

Metrics and audit JSONL are separate; see [Operations README](operations/README.md) and
`repave.config.yaml` `audit`.
