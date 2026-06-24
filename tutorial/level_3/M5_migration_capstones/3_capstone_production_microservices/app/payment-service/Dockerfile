FROM registry.access.redhat.com/ubi9/go-toolset:1.21 AS builder

WORKDIR /opt/app-root/src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o payment-service .

FROM registry.access.redhat.com/ubi9/ubi-micro:latest

COPY --from=builder /opt/app-root/src/payment-service /usr/local/bin/payment-service
RUN chmod 755 /usr/local/bin/payment-service

EXPOSE 8080
USER 1001

ENTRYPOINT ["/usr/local/bin/payment-service"]
