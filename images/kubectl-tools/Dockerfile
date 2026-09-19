FROM alpine:3.24@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6 AS downloader

ARG TARGETARCH
ARG KUBECTL_VERSION=v1.36.4

RUN apk upgrade --no-cache \
    && apk add --no-cache ca-certificates curl \
    && case "$TARGETARCH" in amd64|arm64) ;; *) exit 1 ;; esac \
    && curl -fsSLo /usr/local/bin/kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
    && curl -fsSLo /tmp/kubectl.sha256 "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl.sha256" \
    && echo "$(cat /tmp/kubectl.sha256)  /usr/local/bin/kubectl" | sha256sum -c - \
    && chmod 0755 /usr/local/bin/kubectl \
    && rm /tmp/kubectl.sha256

FROM alpine:3.24@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6

RUN apk upgrade --no-cache && apk add --no-cache bash ca-certificates jq openssl
COPY --from=downloader /usr/local/bin/kubectl /usr/local/bin/kubectl
