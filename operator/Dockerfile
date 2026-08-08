# Build the manager binary
FROM golang:1.23@sha256:60deed95d3888cc5e4d9ff8a10c54e5edc008c6ae3fba6187be6fb592e19e8c0 AS builder
ARG TARGETOS
ARG TARGETARCH

WORKDIR /workspace
COPY go.mod go.sum ./
RUN go mod download
COPY . .

RUN CGO_ENABLED=0 GOOS=${TARGETOS:-linux} GOARCH=${TARGETARCH} go build -a -o manager cmd/main.go

FROM debian:bookworm-slim@sha256:abd67ffcfa541b485a3dff59865ab629aa048a6c613e639d36e7456b0b229241 AS git
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /git-libs \
    && ldd /usr/bin/git | awk '/=> \/lib/ {print $3}' | xargs -I '{}' cp --parents '{}' /git-libs/

FROM gcr.io/distroless/base-debian12:nonroot@sha256:63f52bd27b6aa6555f5d56500b70d7bb0afe51c654905be88a2c1cf967a77b1a
LABEL org.opencontainers.image.source=https://github.com/opsdevcode/repave
LABEL org.opencontainers.image.licenses=MIT
WORKDIR /
COPY --from=builder /workspace/manager .
COPY --from=git /usr/bin/git /usr/bin/git
COPY --from=git /usr/lib/git-core /usr/lib/git-core
COPY --from=git /git-libs/lib /lib
COPY --from=git /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
USER 65532:65532

ENTRYPOINT ["/manager"]
