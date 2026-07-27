FROM python:3.12-slim

ARG TERRAFORM_VERSION=1.9.8
ARG TFLINT_VERSION=0.55.1
ARG CONFTEST_VERSION=0.56.0

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Gate toolchain: terraform, tflint, checkov, conftest (+ git for module repo bootstrap)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip git \
    && rm -rf /var/lib/apt/lists/* \
    && ARCH="$(dpkg --print-architecture)" \
    && case "$ARCH" in \
         amd64) CONF_ARCH="x86_64" ;; \
         arm64) CONF_ARCH="arm64" ;; \
         *) echo "unsupported architecture: $ARCH" >&2; exit 1 ;; \
       esac \
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
    && curl -fsSL \
      "https://github.com/open-policy-agent/conftest/releases/download/v${CONFTEST_VERSION}/conftest_${CONFTEST_VERSION}_Linux_${CONF_ARCH}.tar.gz" \
      | tar xz -C /usr/local/bin conftest \
    && uv pip install --system --no-cache "checkov>=3.2.0" \
    && git config --global user.email "repave@local.dev" \
    && git config --global user.name "repave"

WORKDIR /app

COPY engine/pyproject.toml engine/uv.lock /app/engine/
COPY engine/src /app/engine/src
# Editable install so compose bind-mount of /app picks up template/CSS changes
# without rebuilding the image for every portal tweak.
RUN uv pip install --system --no-cache -e /app/engine

COPY schemas /app/schemas
COPY blueprints /app/blueprints
COPY standards /app/standards
COPY policy /app/policy
# Root README.md and examples/ test fixtures are bind-mounted at /app for compose;
# service images ship standards/ and policy/ only (not examples/).

EXPOSE 8088

CMD ["repave", "serve", "--repo-root", "/app", "--host", "0.0.0.0", "--port", "8088"]
