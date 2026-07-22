FROM python:3.12-slim

ARG TERRAFORM_VERSION=1.9.8
ARG TFLINT_VERSION=0.55.1

# Gate toolchain: terraform, tflint, checkov (+ git for module repo bootstrap)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip git \
    && rm -rf /var/lib/apt/lists/* \
    && ARCH="$(dpkg --print-architecture)" \
    && curl -fsSL \
      "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${ARCH}.zip" \
      -o /tmp/terraform.zip \
    && unzip -q /tmp/terraform.zip -d /usr/local/bin \
    && rm /tmp/terraform.zip \
    && curl -fsSL \
      "https://github.com/terraform-linters/tflint/releases/download/v${TFLINT_VERSION}/tflint_linux_${ARCH}.zip" \
      -o /tmp/tflint.zip \
    && unzip -q /tmp/tflint.zip -d /usr/local/bin \
    && rm /tmp/tflint.zip \
    && pip install --no-cache-dir "checkov>=3.2.0" \
    && git config --global user.email "repave@local.dev" \
    && git config --global user.name "repave"

WORKDIR /app

COPY engine/pyproject.toml /app/engine/pyproject.toml
COPY engine/src /app/engine/src
RUN pip install --no-cache-dir /app/engine

COPY schemas /app/schemas
COPY blueprints /app/blueprints
COPY examples /app/examples
COPY README.md /app/README.md

EXPOSE 8088

CMD ["repave", "serve", "--repo-root", "/app", "--host", "0.0.0.0", "--port", "8088"]
