package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strconv"
	"sync"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	inventoryChecks = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "inventory_service_checks_total",
			Help: "Total number of inventory checks",
		},
		[]string{"product", "result"},
	)
	inventoryLevel = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "inventory_service_stock_level",
			Help: "Current stock level per product",
		},
		[]string{"product"},
	)
	httpRequestsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "inventory_service_http_requests_total",
			Help: "Total HTTP requests",
		},
		[]string{"method", "endpoint", "status"},
	)
)

func init() {
	prometheus.MustRegister(inventoryChecks)
	prometheus.MustRegister(inventoryLevel)
	prometheus.MustRegister(httpRequestsTotal)
}

type Product struct {
	Name     string `json:"name"`
	Quantity int    `json:"quantity"`
	Price    float64 `json:"price"`
}

var (
	inventory   map[string]*Product
	inventoryMu sync.RWMutex
)

func initInventory() {
	inventory = map[string]*Product{
		"widget-a": {Name: "widget-a", Quantity: 100, Price: 9.99},
		"widget-b": {Name: "widget-b", Quantity: 50, Price: 19.99},
		"gadget-x": {Name: "gadget-x", Quantity: 200, Price: 4.99},
		"gadget-y": {Name: "gadget-y", Quantity: 75, Price: 14.99},
	}
	for name, p := range inventory {
		inventoryLevel.WithLabelValues(name).Set(float64(p.Quantity))
	}
}

func getEnv(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok {
		return value
	}
	return fallback
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "healthy", "service": "inventory-service"})
}

func readyHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ready", "service": "inventory-service"})
}

func listInventoryHandler(w http.ResponseWriter, r *http.Request) {
	inventoryMu.RLock()
	defer inventoryMu.RUnlock()

	products := make([]Product, 0, len(inventory))
	for _, p := range inventory {
		products = append(products, *p)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(products)
	httpRequestsTotal.WithLabelValues("GET", "/api/inventory", "200").Inc()
}

func checkInventoryHandler(w http.ResponseWriter, r *http.Request) {
	product := r.URL.Query().Get("product")
	quantityStr := r.URL.Query().Get("quantity")

	if product == "" || quantityStr == "" {
		http.Error(w, "product and quantity required", http.StatusBadRequest)
		return
	}

	quantity, err := strconv.Atoi(quantityStr)
	if err != nil {
		http.Error(w, "invalid quantity", http.StatusBadRequest)
		return
	}

	inventoryMu.RLock()
	p, exists := inventory[product]
	inventoryMu.RUnlock()

	if !exists {
		inventoryChecks.WithLabelValues(product, "not_found").Inc()
		http.Error(w, "product not found", http.StatusNotFound)
		return
	}

	available := p.Quantity >= quantity
	result := "sufficient"
	if !available {
		result = "insufficient"
	}
	inventoryChecks.WithLabelValues(product, result).Inc()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"product":   product,
		"requested": quantity,
		"available": p.Quantity,
		"sufficient": available,
	})
}

func main() {
	initInventory()
	port := getEnv("PORT", "8080")

	http.HandleFunc("/healthz", healthHandler)
	http.HandleFunc("/readyz", readyHandler)
	http.HandleFunc("/api/inventory", listInventoryHandler)
	http.HandleFunc("/api/inventory/check", checkInventoryHandler)
	http.Handle("/metrics", promhttp.Handler())

	log.Printf("Inventory Service starting on port %s", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
