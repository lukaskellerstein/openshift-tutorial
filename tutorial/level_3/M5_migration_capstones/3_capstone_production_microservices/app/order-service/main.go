package main

import (
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	ordersCreated = prometheus.NewCounter(
		prometheus.CounterOpts{
			Name: "order_service_orders_created_total",
			Help: "Total number of orders created",
		},
	)
	ordersProcessing = prometheus.NewGauge(
		prometheus.GaugeOpts{
			Name: "order_service_orders_processing",
			Help: "Number of orders currently being processed",
		},
	)
	orderProcessingDuration = prometheus.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "order_service_processing_duration_seconds",
			Help:    "Time spent processing an order",
			Buckets: []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5},
		},
	)
	httpRequestsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "order_service_http_requests_total",
			Help: "Total HTTP requests",
		},
		[]string{"method", "endpoint", "status"},
	)
)

func init() {
	prometheus.MustRegister(ordersCreated)
	prometheus.MustRegister(ordersProcessing)
	prometheus.MustRegister(orderProcessingDuration)
	prometheus.MustRegister(httpRequestsTotal)
}

type Order struct {
	ID        string    `json:"id"`
	Product   string    `json:"product"`
	Quantity  int       `json:"quantity"`
	Status    string    `json:"status"`
	CreatedAt time.Time `json:"created_at"`
}

var (
	orders   = make(map[string]Order)
	ordersMu sync.RWMutex
)

func getEnv(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok {
		return value
	}
	return fallback
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "healthy", "service": "order-service"})
}

func readyHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ready", "service": "order-service"})
}

func listOrdersHandler(w http.ResponseWriter, r *http.Request) {
	ordersMu.RLock()
	defer ordersMu.RUnlock()

	orderList := make([]Order, 0, len(orders))
	for _, o := range orders {
		orderList = append(orderList, o)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(orderList)
	httpRequestsTotal.WithLabelValues("GET", "/api/orders", "200").Inc()
}

func createOrderHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	start := time.Now()
	ordersProcessing.Inc()
	defer ordersProcessing.Dec()

	var input struct {
		Product  string `json:"product"`
		Quantity int    `json:"quantity"`
	}
	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		httpRequestsTotal.WithLabelValues("POST", "/api/orders", "400").Inc()
		return
	}

	// Check inventory via inventory-service
	inventoryURL := getEnv("INVENTORY_SERVICE_URL", "http://inventory-service:8080")
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Get(fmt.Sprintf("%s/api/inventory/check?product=%s&quantity=%d",
		inventoryURL, input.Product, input.Quantity))
	if err != nil || resp.StatusCode != http.StatusOK {
		log.Printf("Inventory check failed: %v", err)
	}

	order := Order{
		ID:        fmt.Sprintf("ord-%d", rand.Intn(100000)),
		Product:   input.Product,
		Quantity:  input.Quantity,
		Status:    "pending",
		CreatedAt: time.Now(),
	}

	ordersMu.Lock()
	orders[order.ID] = order
	ordersMu.Unlock()

	ordersCreated.Inc()
	orderProcessingDuration.Observe(time.Since(start).Seconds())

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(order)
	httpRequestsTotal.WithLabelValues("POST", "/api/orders", "201").Inc()
}

func main() {
	port := getEnv("PORT", "8080")

	http.HandleFunc("/healthz", healthHandler)
	http.HandleFunc("/readyz", readyHandler)
	http.HandleFunc("/api/orders", func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			listOrdersHandler(w, r)
		case http.MethodPost:
			createOrderHandler(w, r)
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})
	http.Handle("/metrics", promhttp.Handler())

	log.Printf("Order Service starting on port %s", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
