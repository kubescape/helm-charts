FROM --platform=$BUILDPLATFORM golang:1.26-trixie AS builder

ENV GO111MODULE=on CGO_ENABLED=0
WORKDIR /work
ARG TARGETOS TARGETARCH

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN GOOS=$TARGETOS GOARCH=$TARGETARCH go build -trimpath -ldflags="-s -w" -o /out/kubescape-ops-tool .

FROM gcr.io/distroless/static-debian13:nonroot

COPY --from=builder /out/kubescape-ops-tool /usr/bin/

USER nonroot
ENTRYPOINT ["/usr/bin/kubescape-ops-tool"]
