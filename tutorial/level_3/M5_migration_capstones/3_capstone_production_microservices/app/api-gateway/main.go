package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	httpRequestsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "api_gateway_http_requests_total",
			Help: "Total number of HTTP requests handled by the API gateway",
		},
		[]string{"method", "endpoint", "status"},
	)
	httpRequestDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "api_gateway_http_request_duration_seconds",
			Help:    "Duration of HTTP requests in seconds",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"method", "endpoint"},
	)
	upstreamErrors = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "api_gateway_upstream_errors_total",
			Help: "Total number of upstream service errors",
		},
		[]string{"service"},
	)
)

func init() {
	prometheus.MustRegister(httpRequestsTotal)
	prometheus.MustRegister(httpRequestDuration)
	prometheus.MustRegister(upstreamErrors)
}

func getEnv(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok {
		return value
	}
	return fallback
}

func proxyRequest(w http.ResponseWriter, r *http.Request, serviceURL string, serviceName string) {
	start := time.Now()

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(serviceURL + r.URL.Path)
	if err != nil {
		upstreamErrors.WithLabelValues(serviceName).Inc()
		http.Error(w, fmt.Sprintf("upstream %s unavailable: %v", serviceName, err), http.StatusBadGateway)
		httpRequestsTotal.WithLabelValues(r.Method, r.URL.Path, "502").Inc()
		return
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	w.Write(body)

	duration := time.Since(start).Seconds()
	httpRequestDuration.WithLabelValues(r.Method, r.URL.Path).Observe(duration)
	httpRequestsTotal.WithLabelValues(r.Method, r.URL.Path, fmt.Sprintf("%d", resp.StatusCode)).Inc()
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "healthy", "service": "api-gateway"})
}

func readyHandler(w http.ResponseWriter, r *http.Request) {
	orderURL := getEnv("ORDER_SERVICE_URL", "http://order-service:8080")
	client := &http.Client{Timeout: 2 * time.Second}
	_, err := client.Get(orderURL + "/healthz")
	if err != nil {
		http.Error(w, "upstream not ready", http.StatusServiceUnavailable)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ready"})
}

func main() {
	orderURL := getEnv("ORDER_SERVICE_URL", "http://order-service:8080")
	inventoryURL := getEnv("INVENTORY_SERVICE_URL", "http://inventory-service:8080")
	paymentURL := getEnv("PAYMENT_SERVICE_URL", "http://payment-service:8080")
	port := getEnv("PORT", "8080")

	http.HandleFunc("/healthz", healthHandler)
	http.HandleFunc("/readyz", readyHandler)

	http.HandleFunc("/api/orders", func(w http.ResponseWriter, r *http.Request) {
		proxyRequest(w, r, orderURL, "order-service")
	})
	http.HandleFunc("/api/inventory", func(w http.ResponseWriter, r *http.Request) {
		proxyRequest(w, r, inventoryURL, "inventory-service")
	})
	http.HandleFunc("/api/payments", func(w http.ResponseWriter, r *http.Request) {
		proxyRequest(w, r, paymentURL, "payment-service")
	})

	http.Handle("/metrics", promhttp.Handler())

	log.Printf("API Gateway starting on port %s", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
