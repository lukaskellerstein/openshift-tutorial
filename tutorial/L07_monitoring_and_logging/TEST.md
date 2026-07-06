# L07 — Testing & Validation Guide

Walk through the ShopInsights Dashboard and OpenShift Console to verify that Prometheus metrics, Loki centralized logs, and alerting rules are all working.

**Prerequisites:** Run `scripts/setup.sh` first. The instrumented Products Service, ServiceMonitor, PrometheusRule, LokiStack, and ClusterLogForwarder should all be deployed.

---

## URLs You Need

Open these two URLs in separate browser tabs:

| Tab | URL |
|-----|-----|
| **ShopInsights Dashboard** | `https://<dashboard-ui route>/` |
| **OpenShift Console** | `https://<console route>/` |

To get the exact URLs for your cluster:

```bash
echo "Dashboard UI:     https://$(oc get route dashboard-ui -n shopinsights -o jsonpath='{.spec.host}')"
echo "OpenShift Console: https://$(oc get route console -n openshift-console -o jsonpath='{.spec.host}')"
```

---

## Step 1: Generate traffic from the ShopInsights Dashboard

Open the **ShopInsights Dashboard** in your browser. You should see a page with three tabs at the top: **Products**, **Orders**, and **Analytics**.

### 1a. Products tab (generates metrics on the Products Service)

1. The **Products** tab is selected by default. You should see a table with columns: **ID**, **Name**, **Category**, **Price**, **Stock**.
2. Click the **Refresh** button (top-right of the table) **10–15 times**. Each click sends a `GET /products` request to the Products Service, which increments the `http_requests_total` counter and records a duration in the `http_request_duration_seconds` histogram.
3. Click the **Add Product** button. A form appears — fill in a name (e.g. `Test Widget`), category, price, and stock, then submit. This sends a `POST /products` request.
4. After adding, the table should show your new product at the bottom.

### 1b. Orders tab

1. Click the **Orders** tab. You should see a table with columns: **ID**, **Customer**, **Product**, **Qty**, **Total**, **Status**, **Date**.
2. Click **Refresh** a few times. Each click sends a `GET /orders` request to the Orders Service.
3. Click **Create Order** to submit a new order if you want additional traffic.

### 1c. Analytics tab

1. Click the **Analytics** tab. You should see four summary cards at the top:
   - **Total Products** — number of products in the catalog
   - **Total Orders** — number of orders placed
   - **Total Revenue** — sum of all order totals
   - **Avg Order Value** — average order total
2. Below the cards, you should see three tables: **Revenue by Category**, **Revenue by Month**, and **Top Products by Revenue**.
3. Click **Refresh** a few times. Each click sends a `GET /analytics/summary` request to the Analytics Service.

> **Why this matters:** Every request you make in the Dashboard generates Prometheus metrics (counters, histograms), application logs (stdout), and DuckDB query timers. You'll observe all of these in the OpenShift Console next.

---

## Step 2: View metrics in the OpenShift Console

Switch to the **OpenShift Console** browser tab. You should be in the **Administrator** perspective — verify by checking that the left sidebar shows items like **Home**, **Workloads**, **Networking**, **Storage**, **Observe**, etc.

> **Note:** In OpenShift 4.20+, there may not be a perspective-switcher dropdown in the top-left corner. If you only see the Administrator sidebar, the Developer perspective may need to be enabled separately (look for "Enable the Developer Perspective" in the Getting Started panel on the Overview page).

### 2a. Navigate to the Metrics page

1. In the left sidebar, click **Observe**.
2. In the submenu that appears, click **Metrics**.
3. You should see a page titled **Metrics** with a text input area labeled **Expression** (or a query box) and an empty chart area below.

### 2b. Query: Request rate by endpoint

1. In the **Expression** field, paste this PromQL query:

   ```promql
   sum(rate(http_requests_total{namespace="shopinsights"}[5m])) by (exported_endpoint, method)
   ```

2. Click **Run queries** (the blue button to the right of the expression field).
3. You should see a line chart appear with one line per endpoint. Look for:
   - **`/products`** — should show the highest rate (from your Refresh clicks)
   - **`/orders`** — appears from Orders tab refreshes
   - **`/analytics/summary`** — appears from Analytics tab refreshes
   - **`/healthz`** and **`/ready`** — steady baseline from Kubernetes probes
   - **`/products/{id}`** — appears if you clicked on a product row to see its details
4. Switch between the **Chart** and **Table** views using the toggle above the results.

> **Note:** The app's `endpoint` label gets renamed to `exported_endpoint` by Prometheus because `endpoint` is a reserved ServiceMonitor label. Always use `exported_endpoint` in queries.

### 2c. Query: P95 latency by endpoint

1. Clear the expression field and paste:

   ```promql
   histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{namespace="shopinsights"}[5m])) by (le, exported_endpoint))
   ```

2. Click **Run queries**.
3. You should see lines showing the 95th-percentile response time for each endpoint. Expect:
   - **`/healthz`** — very fast (under 5ms)
   - **`/products`** — slightly slower (it queries DuckDB)

### 2d. Query: DuckDB query duration

1. Clear the expression field and paste:

   ```promql
   histogram_quantile(0.95, sum(rate(duckdb_query_duration_seconds_bucket{namespace="shopinsights"}[5m])) by (le, query_type))
   ```

2. Click **Run queries**.
3. You should see lines for different `query_type` values from all three services: `select_all`, `select_by_id`, `init_read_parquet` (from Products/Orders), `stats_count`, `stats_by_status` (from Orders), `build_orders_table`, `revenue_total` (from Analytics). All should be sub-millisecond.

### 2e. Query: Error rate

1. Clear the expression field and paste:

   ```promql
   sum(rate(http_requests_total{namespace="shopinsights", status=~"5.."}[5m])) / sum(rate(http_requests_total{namespace="shopinsights"}[5m])) * 100
   ```

2. Click **Run queries**.
3. **Expected:** The chart shows nothing (or 0%). Under normal operation, there are no 5xx errors.

---

## Step 3: Verify the scrape target

### 3a. Navigate to Targets

1. In the left sidebar, click **Observe** > **Targets**.
2. You should see a list of all Prometheus scrape targets, grouped by namespace.

### 3b. Find the ShopInsights service targets

1. In the **Filter** or search box, type `shopinsights` to narrow the list.
2. Look for three entries:
   - **`products-service-monitor`** (or `shopinsights/products-service-monitor`)
   - **`orders-service-monitor`** (or `shopinsights/orders-service-monitor`)
   - **`analytics-service-monitor`** (or `shopinsights/analytics-service-monitor`)
3. For each, verify:
   - **Status**: should show **Up** with a green indicator
   - **Last Scrape**: should show a recent timestamp (within the last 15 seconds)
   - **Scrape Duration**: typically 5–10 ms

> **What this tells you:** All three ServiceMonitors are correctly configured and Prometheus is actively scraping the `/metrics` endpoints from all ShopInsights services.

---

## Step 4: Check alerting rules

### 4a. Navigate to Alerting

1. In the left sidebar, click **Observe** > **Alerting**.
2. You should see a page with tabs: **Alerts** and **Alerting rules** (or **Silences**).

### 4b. View the alerting rules

1. Click the **Alerting rules** tab.
2. Click the **Source** filter dropdown and select **User** (this filters to rules defined in user namespaces, excluding platform rules).
3. You should see two rules:
   - **ProductsHighLatency** — Severity: Warning
   - **ProductsHighErrorRate** — Severity: Critical
4. Both should show **State: Inactive** (green) — meaning neither alert is currently firing.
5. Click on either rule name to expand it. You should see:
   - The PromQL expression that triggers the alert
   - Annotations (summary, description)
   - Labels (severity, namespace)

> **What this tells you:** The PrometheusRule CR is loaded and evaluated by Prometheus. Both rules are inactive because latency is below 500ms and there are no 5xx errors.

---

## Step 5: View centralized logs in Loki

### 5a. Navigate to Logs

1. In the left sidebar, click **Observe** > **Logs**.
2. You should see a log viewer page with filter dropdowns at the top.

> **If you don't see "Logs" under Observe:** The UIPlugin for the logging console plugin may not be deployed. Run `oc apply -f manifests/uiplugin-logging.yaml` from the L07 lesson directory and refresh the console.

### 5b. Filter by namespace

1. Click the **Namespace** dropdown and select **shopinsights**.
2. Log entries from all ShopInsights pods should appear in the log stream below.
3. You should see Uvicorn access log lines like:
   ```
   INFO: 10.x.x.x:xxxxx - "GET /products HTTP/1.1" 200 OK
   INFO: 10.x.x.x:xxxxx - "GET /healthz HTTP/1.1" 200 OK
   ```

### 5c. Filter by pod

1. Click the **Pod** dropdown and select the `products-service-*` pod.
2. Now you should see only logs from the Products Service.
3. Look for the `GET /products` log lines that correspond to your Refresh clicks in Step 1.

### 5d. Try a LogQL query

1. Click the **Show LogQL** toggle (or click the **LogQL** button — it may appear as a toggle or link near the query bar).
2. In the LogQL expression field, paste:

   ```logql
   {kubernetes_namespace_name="shopinsights"} |= "products"
   ```

3. Press **Enter** or click **Run query**.
4. You should see only log lines containing the word "products" from any pod in the `shopinsights` namespace.

---

## Step 6: View pod logs in the Developer perspective

### 6a. Switch to Developer perspective

1. If your Console has a perspective-switcher dropdown in the top-left corner, click it and select **Developer**.
2. If there's no dropdown (OpenShift 4.20+), go to **Home > Overview** and click **"Enable the Developer Perspective →"** in the Getting Started panel. Once enabled, a perspective switcher will appear — select **Developer**.

> **If the Developer perspective is already enabled**, you'll see a dropdown in the top-left corner that says "Administrator" — click it and select "Developer".

### 6b. Navigate to the Products Service pod

1. In the left sidebar, click **Topology**.
2. Make sure the project dropdown at the top shows **shopinsights**.
3. You should see circles/icons representing the ShopInsights deployments: `dashboard-ui`, `products-service`, `orders-service`, `analytics-service`.
4. Click the **products-service** icon.

### 6c. View pod logs

1. A side panel opens on the right. Click the **Resources** tab in the panel.
2. Click the pod name (e.g. `products-service-xxxxx-xxxxx`) to open the pod details page.
3. Click the **Logs** tab at the top of the pod details page.
4. You should see a live-streaming log view. New log lines appear in real time.
5. Go back to the **ShopInsights Dashboard** tab and click **Refresh** on the Products tab.
6. Switch back to the Console — you should see new `GET /products` log lines appear immediately.

### 6d. Developer Observe

1. In the Developer perspective left sidebar, click **Observe**.
2. You should see pre-built **CPU Usage** and **Memory Usage** graphs for workloads in the `shopinsights` project.
3. Click the **Metrics** tab to run custom PromQL queries (same queries from Step 2 work here too).
4. Click the **Events** tab to see Kubernetes events (pod scheduling, image pulls, restarts).

---

## Step 7: Generate more traffic and watch it flow

This step ties everything together. Open both the ShopInsights Dashboard and the OpenShift Console side by side.

1. In the **ShopInsights Dashboard**, click the **Products** tab and click **Refresh** rapidly (20+ times).
2. In the **OpenShift Console** (Administrator perspective — the default view with sidebar items like Home, Workloads, Observe):
   - Go to **Observe > Metrics** and re-run the request rate query from Step 2b. You should see the `/products` line spike upward.
   - Go to **Observe > Logs** and filter to `shopinsights` namespace. You should see a burst of new `GET /products` log lines.
   - Go to **Observe > Targets** — all three ServiceMonitor targets (`products-service-monitor`, `orders-service-monitor`, `analytics-service-monitor`) should still show **Up**.
   - Go to **Observe > Alerting** > **Alerting rules** (filtered to **User**) — both rules should still be **Inactive** (unless you managed to push latency above 500ms).

---

## Summary

| What You Did | What You Should See |
|-------------|---------------------|
| Clicked Refresh on Products tab | `http_requests_total` counter increases in Observe > Metrics |
| Clicked Refresh on Products tab | `GET /products` log lines appear in Observe > Logs |
| Clicked a product row | `GET /products/{id}` appears in metrics and logs |
| Added a product | `POST /products` appears in logs, `http_requests_total` counter increases |
| Clicked Orders / Analytics tabs | Traffic to orders-service and analytics-service visible in metrics and logs |
| Ran PromQL request rate query | Line chart with lines per endpoint from all three services |
| Ran PromQL P95 latency query | Line chart showing `/healthz` < `/products` |
| Ran PromQL error rate query | Empty chart or 0% (no errors) |
| Checked Observe > Targets | All three ServiceMonitors show Up (green) |
| Checked Observe > Alerting rules | ProductsHighLatency + ProductsHighErrorRate both Inactive |
| Filtered logs by namespace | Logs from all 4 ShopInsights services |
| Filtered logs by pod | Only Products Service logs |
| Ran LogQL query | Filtered logs containing "products" |
| Viewed Topology > pod > Logs | Real-time log streaming from Products Service |

---

## Known Limitations

1. **`exported_endpoint` vs `endpoint`** — Prometheus renames our app's `endpoint` label to `exported_endpoint` because `endpoint` is reserved by ServiceMonitors. Use `exported_endpoint` in all PromQL queries.

2. **Rate queries need time** — `rate(...[5m])` needs at least two scrapes within the 5-minute window. After deploying, wait ~30 seconds before running rate queries.

3. **Loki log ingestion delay** — Logs may take 10–30 seconds to appear in Observe > Logs after being generated. If logs are missing, wait and refresh.

4. **Container-level log filtering** — The ClusterLogForwarder collects only from `products-service`, `orders-service`, `analytics-service`, and `dashboard-ui` containers in the `shopinsights` namespace. Logs from other containers (build pods, sidecars) are not forwarded to Loki.

---

> **Next:** For custom Grafana dashboards with unified metrics, logs, and traces views, see **L12 — Custom Monitoring Dashboards (Grafana)**.
