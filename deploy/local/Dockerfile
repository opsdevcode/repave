FROM python:3.12-slim

WORKDIR /app

COPY engine/pyproject.toml /app/engine/pyproject.toml
COPY engine/src /app/engine/src
RUN pip install --no-cache-dir /app/engine

COPY schemas /app/schemas
COPY blueprints /app/blueprints
COPY examples /app/examples
COPY README.md /app/README.md

EXPOSE 8080

CMD ["repave", "serve", "--repo-root", "/app", "--host", "0.0.0.0", "--port", "8080"]
