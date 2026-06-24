package main

import (
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"os"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	paymentsProcessed = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "payment_service_payments_processed_total",
			Help: "Total number of payments processed",
		},
		[]string{"status"},
	)
	paymentAmount = prometheus.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "payment_service_amount_dollars",
			Help:    "Payment amounts in dollars",
			Buckets: []float64{1, 5, 10, 25, 50, 100, 250, 500, 1000},
		},
	)
	paymentProcessingDuration = prometheus.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "payment_service_processing_duration_seconds",
			Help:    "Time spent processing a payment",
			Buckets: []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0},
		},
	)
	httpRequestsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "payment_service_http_requests_total",
			Help: "Total HTTP requests",
		},
		[]string{"method", "endpoint", "status"},
	)
)

func init() {
	prometheus.MustRegister(paymentsProcessed)
	prometheus.MustRegister(paymentAmount)
	prometheus.MustRegister(paymentProcessingDuration)
	prometheus.MustRegister(httpRequestsTotal)
}

type PaymentRequest struct {
	OrderID string  `json:"order_id"`
	Amount  float64 `json:"amount"`
	Method  string  `json:"method"`
}

type PaymentResponse struct {
	TransactionID string `json:"transaction_id"`
	OrderID       string `json:"order_id"`
	Status        string `json:"status"`
	Message       string `json:"message"`
}

func getEnv(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok {
		return value
	}
	return fallback
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "healthy", "service": "payment-service"})
}

func readyHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ready", "service": "payment-service"})
}

func processPaymentHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	start := time.Now()

	var req PaymentRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		httpRequestsTotal.WithLabelValues("POST", "/api/payments", "400").Inc()
		return
	}

	// Simulate payment processing latency
	processingTime := time.Duration(50+rand.Intn(200)) * time.Millisecond
	time.Sleep(processingTime)

	// Simulate occasional payment failures (5% failure rate)
	status := "approved"
	message := "Payment processed successfully"
	httpStatus := http.StatusOK

	if rand.Float64() < 0.05 {
		status = "declined"
		message = "Payment declined by processor"
		httpStatus = http.StatusPaymentRequired
	}

	paymentAmount.Observe(req.Amount)
	paymentsProcessed.WithLabelValues(status).Inc()
	paymentProcessingDuration.Observe(time.Since(start).Seconds())

	resp := PaymentResponse{
		TransactionID: fmt.Sprintf("txn-%d", rand.Intn(1000000)),
		OrderID:       req.OrderID,
		Status:        status,
		Message:       message,
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(httpStatus)
	json.NewEncoder(w).Encode(resp)
	httpRequestsTotal.WithLabelValues("POST", "/api/payments", fmt.Sprintf("%d", httpStatus)).Inc()
}

func main() {
	port := getEnv("PORT", "8080")

	http.HandleFunc("/healthz", healthHandler)
	http.HandleFunc("/readyz", readyHandler)
	http.HandleFunc("/api/payments", processPaymentHandler)
	http.Handle("/metrics", promhttp.Handler())

	log.Printf("Payment Service starting on port %s", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
