# syntax=docker/dockerfile:1
# uv comes from its published image by default; set UV_SOURCE=pip when ghcr.io is
# unreachable (air-gapped or proxy-restricted networks). Both paths install UV_VERSION.
ARG UV_VERSION=0.11.33
ARG UV_SOURCE=registry

FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS base

LABEL org.opencontainers.image.source=https://github.com/opsdevcode/repave
LABEL org.opencontainers.image.licenses=MIT

FROM ghcr.io/astral-sh/uv:0.11.33@sha256:77280f2f771df71f90786c314fe1bbc1e023feac652969bbf139c280babf2eb7 AS uv-bin

FROM base AS uv-registry
COPY --from=uv-bin /uv /usr/local/bin/uv

FROM base AS uv-pip
ARG UV_VERSION
RUN python -m pip install --no-cache-dir "uv==${UV_VERSION}"

FROM uv-${UV_SOURCE} AS runtime

# Certificates dropped in deploy/local/certs are trusted by curl, pip/uv, ansible-galaxy
# and git alike; see deploy/local/certs/README.md.
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# Last-resort escape hatch for TLS-inspecting proxies without an obtainable CA.
ARG REPAVE_TLS_INSECURE=0
ARG INSTALL_ANSIBLE_COLLECTIONS=1
# 1 = full portal dry-run gates (default). 0 = slimmer portal-only image (Helm image.gateToolchain: false).
ARG INSTALL_GATE_TOOLCHAIN=1
# 1 = embed generation corpus in image (default). 0 = mount corpus OCI artifact at runtime.
ARG INCLUDE_CORPUS=1

COPY deploy/local/certs/ /usr/local/share/ca-certificates/repave/

# Gate toolchain: deploy/local/install-gate-toolchain.sh sources gate-toolchain-pins.env
COPY ansible/requirements-gate-collections.yml /app/ansible/requirements-gate-collections.yml
RUN mkdir -p /app/deploy/local
COPY deploy/local/gate-toolchain-pins.env /app/deploy/local/gate-toolchain-pins.env
COPY deploy/local/install-gate-toolchain.sh /app/deploy/local/install-gate-toolchain.sh
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip git \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates \
    && sed -i 's/\r$//' /app/deploy/local/install-gate-toolchain.sh \
    && chmod +x /app/deploy/local/install-gate-toolchain.sh \
    && if [ "${INSTALL_GATE_TOOLCHAIN}" = "1" ]; then \
         REPO_ROOT=/app USE_UV_PIP=1 \
           REPAVE_TLS_INSECURE="${REPAVE_TLS_INSECURE}" \
           INSTALL_ANSIBLE_COLLECTIONS="${INSTALL_ANSIBLE_COLLECTIONS}" \
           /app/deploy/local/install-gate-toolchain.sh; \
       fi \
    && rm /app/deploy/local/install-gate-toolchain.sh \
    && git config --global user.email "repave@local.dev" \
    && git config --global user.name "repave"

WORKDIR /app

COPY engine/pyproject.toml engine/uv.lock /app/engine/
COPY engine/src /app/engine/src
# Editable install so compose bind-mount of /app picks up template/CSS changes
# without rebuilding the image for every portal tweak.
RUN uv pip install --system --no-cache -e "/app/engine[s3,postgres]"

RUN if [ "${INSTALL_GATE_TOOLCHAIN}" = "1" ]; then \
      repave doctor --strict --repo-root /app; \
    fi

COPY schemas /app/schemas
COPY blueprints /app/blueprints
COPY standards /app/standards
COPY policy /app/policy
RUN if [ "${INCLUDE_CORPUS}" = "0" ]; then \
      rm -rf /app/schemas /app/blueprints /app/standards /app/policy; \
    fi
# Root README.md and examples/ test fixtures are bind-mounted at /app for compose;
# service images ship standards/ and policy/ only (not examples/) when INCLUDE_CORPUS=1.

EXPOSE 8088

CMD ["repave", "serve", "--repo-root", "/app", "--host", "0.0.0.0", "--port", "8088"]
