# Multi-stage build for minimal production image
# Uses UBI (Universal Base Image) for OpenShift compatibility
FROM registry.access.redhat.com/ubi9/go-toolset:1.21 AS builder

WORKDIR /opt/app-root/src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o api-gateway .

FROM registry.access.redhat.com/ubi9/ubi-micro:latest

COPY --from=builder /opt/app-root/src/api-gateway /usr/local/bin/api-gateway

# OpenShift runs containers as non-root with a random UID
# The binary must be executable by any user
RUN chmod 755 /usr/local/bin/api-gateway

EXPOSE 8080

USER 1001

ENTRYPOINT ["/usr/local/bin/api-gateway"]
