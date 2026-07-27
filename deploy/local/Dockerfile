FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Gate toolchain: see deploy/local/install-gate-toolchain.sh (keep versions in ci_toolchain.py)
COPY deploy/local/install-gate-toolchain.sh /tmp/install-gate-toolchain.sh
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip git \
    && rm -rf /var/lib/apt/lists/* \
    && chmod +x /tmp/install-gate-toolchain.sh \
    && PIP="uv pip install --system --no-cache" /tmp/install-gate-toolchain.sh \
    && rm /tmp/install-gate-toolchain.sh \
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
