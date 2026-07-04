"""
TrustyAI monitoring setup -- configures bias and drift monitors for a tabular model.

Connects to the TrustyAI service REST API, registers SPD (Statistical Parity
Difference), DIR (Disparate Impact Ratio), and MeanShift drift monitors for
the income prediction model, then uploads sample inference data and queries
the computed metrics with human-readable interpretation.

Demonstrates:
- Connecting to the TrustyAI service via its OpenShift Route
- Uploading inference data for monitoring (simulating model predictions)
- Configuring bias monitors (SPD, DIR) for a protected attribute
- Configuring drift monitors (MeanShift) against a training baseline
- Querying current metric values and interpreting results
- Understanding what metric values mean for model fairness

Environment variables:
    TRUSTYAI_ROUTE -- hostname of the TrustyAI service Route
                      (e.g., trustyai-service-trustyai-tutorial.apps.cluster.example.com)
                      Set with: oc get route trustyai-service -n trustyai-tutorial -o jsonpath='{.spec.host}'
    MODEL_NAME     -- name of the InferenceService to monitor (default: income-predictor)

Usage:
    export TRUSTYAI_ROUTE="$(oc get route trustyai-service -n trustyai-tutorial -o jsonpath='{.spec.host}')"
    export MODEL_NAME="income-predictor"
    python3 setup_monitoring.py

Requirements:
    pip install requests
"""

import json
import os
import random
import sys
import time

import requests


# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

TRUSTYAI_ROUTE = os.environ.get("TRUSTYAI_ROUTE")
MODEL_NAME = os.environ.get("MODEL_NAME", "income-predictor")

# TrustyAI API base URL (HTTPS via the OpenShift Route)
BASE_URL = f"https://{TRUSTYAI_ROUTE}" if TRUSTYAI_ROUTE else None

# Feature names matching the income prediction model schema.
# These correspond to the Adult Census / income prediction dataset features,
# encoded as integers for the OpenVINO model.
FEATURE_NAMES = [
    "age", "workclass", "education-num", "marital-status", "occupation",
    "relationship", "race", "gender", "capital-gain", "capital-loss",
    "hours-per-week",
]

# Protected attribute configuration for bias monitoring
PROTECTED_ATTRIBUTE = "gender"
PRIVILEGED_VALUE = 1       # male (encoded)
UNPRIVILEGED_VALUE = 0     # female (encoded)
FAVORABLE_OUTCOME = 1      # income >50K
OUTCOME_NAME = "predict"
BATCH_SIZE = 5000

# Number of sample inferences to generate and upload
NUM_SAMPLES = 200


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def check_environment() -> None:
    """Verify required environment variables are set."""
    if not TRUSTYAI_ROUTE:
        print("Error: TRUSTYAI_ROUTE environment variable is not set.", file=sys.stderr)
        print("Set it with:", file=sys.stderr)
        print(
            '  export TRUSTYAI_ROUTE="$(oc get route trustyai-service '
            "-n trustyai-tutorial -o jsonpath='{.spec.host}')\"",
            file=sys.stderr,
        )
        sys.exit(1)


def api_get(path: str) -> dict:
    """Send a GET request to the TrustyAI API."""
    url = f"{BASE_URL}{path}"
    response = requests.get(url, verify=False, timeout=30)
    response.raise_for_status()
    return response.json()


def api_post(path: str, payload: dict) -> dict:
    """Send a POST request to the TrustyAI API."""
    url = f"{BASE_URL}{path}"
    response = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json"},
        verify=False,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def generate_sample_inference() -> dict:
    """Generate a single sample inference record for the income prediction model.

    Returns a dict with feature values and a simulated prediction outcome.
    The data is designed to introduce a slight bias where the privileged group
    (gender=1) has a somewhat higher rate of favorable outcomes, so the bias
    monitors have something meaningful to detect.
    """
    gender = random.choice([0, 1])
    age = random.randint(18, 70)
    workclass = random.randint(0, 8)
    education_num = random.randint(1, 16)
    marital_status = random.randint(0, 6)
    occupation = random.randint(0, 14)
    relationship = random.randint(0, 5)
    race = random.randint(0, 4)
    capital_gain = random.choice([0, 0, 0, random.randint(1000, 99999)])
    capital_loss = random.choice([0, 0, 0, random.randint(100, 4000)])
    hours_per_week = random.randint(10, 80)

    # Simulate a prediction with slight bias:
    # Base probability of favorable outcome depends on education and hours
    base_prob = 0.15 + (education_num / 16) * 0.3 + (hours_per_week / 80) * 0.15
    if capital_gain > 5000:
        base_prob += 0.2
    # Introduce slight bias: privileged group gets a small boost
    if gender == PRIVILEGED_VALUE:
        base_prob += 0.05
    prediction = 1 if random.random() < base_prob else 0

    features = {
        "age": age,
        "workclass": workclass,
        "education-num": education_num,
        "marital-status": marital_status,
        "occupation": occupation,
        "relationship": relationship,
        "race": race,
        "gender": gender,
        "capital-gain": capital_gain,
        "capital-loss": capital_loss,
        "hours-per-week": hours_per_week,
    }

    return {"features": features, "prediction": prediction}


# ---------------------------------------------------------------------------
# Monitoring setup steps
# ---------------------------------------------------------------------------

def check_service_health() -> None:
    """Step 1: Verify TrustyAI service is reachable and report tracked models."""
    print("=" * 60)
    print("Step 1: Checking TrustyAI service health")
    print("=" * 60)

    try:
        info = api_get("/info")
        print(f"TrustyAI service is reachable at: {BASE_URL}")
        if info:
            print(f"Currently tracking {len(info)} model(s):")
            for model_name in info:
                obs = info[model_name].get("data", {}).get("observations", 0)
                print(f"  - {model_name}: {obs} observations")
        else:
            print("No models being tracked yet (expected before first inference).")
        print()
    except requests.exceptions.ConnectionError:
        print(f"Error: Cannot connect to TrustyAI service at {BASE_URL}", file=sys.stderr)
        print("Verify the TrustyAI pod is running:", file=sys.stderr)
        print("  oc get pods -n trustyai-tutorial -l app.kubernetes.io/name=trustyai-service", file=sys.stderr)
        sys.exit(1)


def upload_inference_data() -> None:
    """Step 2: Upload sample inference data for monitoring.

    In a real deployment, TrustyAI intercepts inference data automatically
    from the model server via KServe payload logging. For this tutorial,
    we upload synthetic data via the TrustyAI data upload API to simulate
    inference history without requiring a live model endpoint.
    """
    print("=" * 60)
    print(f"Step 2: Uploading {NUM_SAMPLES} sample inference records")
    print("=" * 60)

    # Generate sample data
    random.seed(42)
    samples = [generate_sample_inference() for _ in range(NUM_SAMPLES)]

    # Count outcome distribution by group for reporting
    priv_total = sum(1 for s in samples if s["features"]["gender"] == PRIVILEGED_VALUE)
    priv_favorable = sum(
        1 for s in samples
        if s["features"]["gender"] == PRIVILEGED_VALUE and s["prediction"] == FAVORABLE_OUTCOME
    )
    unpriv_total = sum(1 for s in samples if s["features"]["gender"] == UNPRIVILEGED_VALUE)
    unpriv_favorable = sum(
        1 for s in samples
        if s["features"]["gender"] == UNPRIVILEGED_VALUE and s["prediction"] == FAVORABLE_OUTCOME
    )

    # Format data for TrustyAI upload API
    payload = {
        "modelId": MODEL_NAME,
        "dataTag": "TRAINING",
        "data": [],
    }

    for sample in samples:
        record = {
            "input": sample["features"],
            "output": {OUTCOME_NAME: sample["prediction"]},
        }
        payload["data"].append(record)

    try:
        api_post("/data/upload", payload)
        print(f"Uploaded {NUM_SAMPLES} records successfully.")
    except requests.exceptions.HTTPError as e:
        print(f"Warning: Data upload returned {e.response.status_code}.", file=sys.stderr)
        print("This may be expected if TrustyAI intercepts data automatically", file=sys.stderr)
        print("from the model server rather than via the upload API.", file=sys.stderr)
        print("Continuing with monitor configuration...", file=sys.stderr)

    print()
    print("Data distribution summary:")
    if priv_total > 0:
        print(f"  Privileged group (gender={PRIVILEGED_VALUE}, male):     "
              f"{priv_favorable}/{priv_total} favorable "
              f"({priv_favorable / priv_total:.1%})")
    if unpriv_total > 0:
        print(f"  Unprivileged group (gender={UNPRIVILEGED_VALUE}, female): "
              f"{unpriv_favorable}/{unpriv_total} favorable "
              f"({unpriv_favorable / unpriv_total:.1%})")

    # Compute expected metrics for comparison
    if priv_total > 0 and unpriv_total > 0:
        priv_rate = priv_favorable / priv_total
        unpriv_rate = unpriv_favorable / unpriv_total
        expected_spd = unpriv_rate - priv_rate
        expected_dir = unpriv_rate / priv_rate if priv_rate > 0 else float("inf")
        print(f"\n  Expected SPD (approx): {expected_spd:.4f}")
        print(f"  Expected DIR (approx): {expected_dir:.4f}")
    print()


def configure_spd_monitor() -> None:
    """Step 3: Configure Statistical Parity Difference (SPD) monitor.

    SPD = P(outcome=favorable | unprivileged) - P(outcome=favorable | privileged)

    Values near 0 indicate fairness. Acceptable range: [-0.1, 0.1].
    Negative values mean the unprivileged group receives fewer favorable outcomes.
    """
    print("=" * 60)
    print("Step 3: Configuring SPD (Statistical Parity Difference) monitor")
    print("=" * 60)

    payload = {
        "modelId": MODEL_NAME,
        "protectedAttribute": PROTECTED_ATTRIBUTE,
        "favorableOutcome": FAVORABLE_OUTCOME,
        "outcomeName": OUTCOME_NAME,
        "privilegedAttribute": PRIVILEGED_VALUE,
        "unprivilegedAttribute": UNPRIVILEGED_VALUE,
        "batchSize": BATCH_SIZE,
    }

    try:
        result = api_post("/metrics/spd/request", payload)
        request_id = result.get("requestId", "N/A")
        print(f"SPD monitor configured successfully.")
        print(f"  Request ID: {request_id}")
        print(f"  Schedule:   recurring (per metrics.schedule in TrustyAIService CR)")
        print()
        print("SPD measures the difference in favorable outcome rates:")
        print(f"  SPD = P({OUTCOME_NAME}={FAVORABLE_OUTCOME} | {PROTECTED_ATTRIBUTE}={UNPRIVILEGED_VALUE})")
        print(f"      - P({OUTCOME_NAME}={FAVORABLE_OUTCOME} | {PROTECTED_ATTRIBUTE}={PRIVILEGED_VALUE})")
        print()
        print("Interpretation:")
        print("  SPD =  0.0         -- perfect fairness")
        print("  SPD in [-0.1, 0.1] -- acceptable range")
        print("  SPD < -0.1         -- potential bias against unprivileged group")
        print("  SPD >  0.1         -- potential bias favoring unprivileged group")
    except requests.exceptions.HTTPError as e:
        print(f"Error configuring SPD monitor: {e.response.status_code}", file=sys.stderr)
        print(f"Response: {e.response.text}", file=sys.stderr)
    print()


def configure_dir_monitor() -> None:
    """Step 4: Configure Disparate Impact Ratio (DIR) monitor.

    DIR = P(outcome=favorable | unprivileged) / P(outcome=favorable | privileged)

    Values near 1.0 indicate fairness. The "four-fifths rule" (80% rule)
    considers DIR < 0.8 as evidence of adverse impact.
    """
    print("=" * 60)
    print("Step 4: Configuring DIR (Disparate Impact Ratio) monitor")
    print("=" * 60)

    payload = {
        "modelId": MODEL_NAME,
        "protectedAttribute": PROTECTED_ATTRIBUTE,
        "favorableOutcome": FAVORABLE_OUTCOME,
        "outcomeName": OUTCOME_NAME,
        "privilegedAttribute": PRIVILEGED_VALUE,
        "unprivilegedAttribute": UNPRIVILEGED_VALUE,
        "batchSize": BATCH_SIZE,
    }

    try:
        result = api_post("/metrics/dir/request", payload)
        request_id = result.get("requestId", "N/A")
        print(f"DIR monitor configured successfully.")
        print(f"  Request ID: {request_id}")
        print()
        print("DIR measures the ratio of favorable outcome rates:")
        print(f"  DIR = P({OUTCOME_NAME}={FAVORABLE_OUTCOME} | {PROTECTED_ATTRIBUTE}={UNPRIVILEGED_VALUE})")
        print(f"      / P({OUTCOME_NAME}={FAVORABLE_OUTCOME} | {PROTECTED_ATTRIBUTE}={PRIVILEGED_VALUE})")
        print()
        print("Interpretation:")
        print("  DIR = 1.0          -- perfect fairness")
        print("  DIR in [0.8, 1.2]  -- acceptable range (the '80% rule')")
        print("  DIR < 0.8          -- disparate impact detected")
        print("  DIR > 1.2          -- reverse disparate impact")
    except requests.exceptions.HTTPError as e:
        print(f"Error configuring DIR monitor: {e.response.status_code}", file=sys.stderr)
        print(f"Response: {e.response.text}", file=sys.stderr)
    print()


def configure_drift_monitor() -> None:
    """Step 5: Configure MeanShift drift monitor.

    MeanShift compares the mean of each feature in recent inferences against
    the baseline data (tagged as 'TRAINING'). If the mean shifts significantly,
    it indicates the incoming data distribution has changed and the model may
    need retraining.
    """
    print("=" * 60)
    print("Step 5: Configuring MeanShift drift monitor")
    print("=" * 60)

    payload = {
        "modelId": MODEL_NAME,
        "referenceTag": "TRAINING",
    }

    try:
        result = api_post("/metrics/drift/meanshift/request", payload)
        request_id = result.get("requestId", "N/A")
        print(f"MeanShift drift monitor configured successfully.")
        print(f"  Request ID:    {request_id}")
        print(f"  Reference tag: TRAINING (baseline data uploaded in Step 2)")
        print()
        print("MeanShift drift detection compares the mean of each feature in")
        print("recent inferences against the training baseline. If the mean shifts")
        print("significantly, it indicates the incoming data distribution has changed")
        print("and the model may need retraining.")
        print()
        print("Other available drift algorithms (not configured here):")
        print("  - FourierMMD:  detects complex distribution changes via MMD in Fourier space")
        print("  - KSTest:      Kolmogorov-Smirnov test for any distributional difference")
    except requests.exceptions.HTTPError as e:
        print(f"Error configuring drift monitor: {e.response.status_code}", file=sys.stderr)
        print(f"Response: {e.response.text}", file=sys.stderr)
    print()


def query_metrics() -> None:
    """Step 6: Query current metric values and display results with interpretation."""
    print("=" * 60)
    print("Step 6: Querying current metric values")
    print("=" * 60)
    print()

    # Wait for metrics to be computed (metrics.schedule is 5s in the CR)
    print("Waiting 10 seconds for metric computation...")
    time.sleep(10)

    # --- SPD ---
    print("-" * 40)
    print("SPD (Statistical Parity Difference)")
    print("-" * 40)
    try:
        spd_result = api_get("/metrics/spd")
        spd_value = spd_result.get("value", "N/A")
        spd_status = spd_result.get("status", "N/A")
        definition = spd_result.get("specificDefinition", "")

        print(f"  Value:  {spd_value}")
        print(f"  Status: {spd_status}")
        if definition:
            print(f"  Detail: {definition}")

        if isinstance(spd_value, (int, float)):
            if abs(spd_value) <= 0.1:
                print("  --> Within acceptable range. No significant bias detected.")
            else:
                direction = "against" if spd_value < 0 else "favoring"
                print(f"  --> OUTSIDE acceptable range. Bias {direction} unprivileged group.")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print("  No SPD data available yet. Send more inferences and retry.")
        else:
            print(f"  Error: {e.response.status_code} -- {e.response.text}")
    print()

    # --- DIR ---
    print("-" * 40)
    print("DIR (Disparate Impact Ratio)")
    print("-" * 40)
    try:
        dir_result = api_get("/metrics/dir")
        dir_value = dir_result.get("value", "N/A")
        dir_status = dir_result.get("status", "N/A")
        definition = dir_result.get("specificDefinition", "")

        print(f"  Value:  {dir_value}")
        print(f"  Status: {dir_status}")
        if definition:
            print(f"  Detail: {definition}")

        if isinstance(dir_value, (int, float)):
            if 0.8 <= dir_value <= 1.2:
                print("  --> Within acceptable range. No disparate impact detected.")
            elif dir_value < 0.8:
                print("  --> BELOW 0.8 threshold. Disparate impact against unprivileged group.")
            else:
                print("  --> ABOVE 1.2 threshold. Reverse disparate impact detected.")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print("  No DIR data available yet. Send more inferences and retry.")
        else:
            print(f"  Error: {e.response.status_code} -- {e.response.text}")
    print()

    # --- Drift ---
    print("-" * 40)
    print("MeanShift Drift")
    print("-" * 40)
    try:
        drift_result = api_get("/metrics/drift/meanshift")
        if isinstance(drift_result, dict):
            drift_value = drift_result.get("value", "N/A")
            drift_status = drift_result.get("status", "N/A")
            print(f"  Value:  {drift_value}")
            print(f"  Status: {drift_status}")
            if drift_status == "NO_DRIFT":
                print("  --> No significant drift detected. Data distribution is stable.")
            elif drift_status == "DRIFT":
                print("  --> Drift detected. Incoming data differs from training baseline.")
        elif isinstance(drift_result, list):
            print("  Per-feature drift values:")
            for feature_drift in drift_result:
                fname = feature_drift.get("featureName", "unknown")
                fvalue = feature_drift.get("value", "N/A")
                fstatus = feature_drift.get("status", "")
                status_indicator = " [DRIFT]" if fstatus == "DRIFT" else ""
                print(f"    {fname}: {fvalue}{status_indicator}")
        else:
            print(f"  Result: {json.dumps(drift_result, indent=2)}")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print("  No drift data available yet. Need inferences after the baseline window.")
        else:
            print(f"  Error: {e.response.status_code} -- {e.response.text}")
    print()


def print_summary() -> None:
    """Print a summary of configured monitors and next steps."""
    print("=" * 60)
    print("Setup Complete")
    print("=" * 60)
    print()
    print(f"Model:               {MODEL_NAME}")
    print(f"TrustyAI endpoint:   {BASE_URL}")
    print(f"Protected attribute: {PROTECTED_ATTRIBUTE}")
    print(f"Privileged value:    {PRIVILEGED_VALUE} (male)")
    print(f"Unprivileged value:  {UNPRIVILEGED_VALUE} (female)")
    print(f"Favorable outcome:   {OUTCOME_NAME}={FAVORABLE_OUTCOME} (income >50K)")
    print()
    print("Configured monitors:")
    print("  1. SPD       -- Statistical Parity Difference (bias)")
    print("  2. DIR       -- Disparate Impact Ratio (bias)")
    print("  3. MeanShift -- data drift detection")
    print()
    print("Prometheus metrics exported (query in Grafana or OpenShift Console):")
    print(f'  trustyai_spd{{namespace="trustyai-tutorial"}}')
    print(f'  trustyai_dir{{namespace="trustyai-tutorial"}}')
    print(f'  trustyai_meanshift{{namespace="trustyai-tutorial"}}')
    print()
    print("Alert rule examples (PromQL):")
    print(f'  abs(trustyai_spd{{namespace="trustyai-tutorial"}}) > 0.1')
    print(f'  trustyai_dir{{namespace="trustyai-tutorial"}} < 0.8')
    print()
    print("Next steps:")
    print("  1. View metrics in the OpenShift console: Observe > Metrics")
    print("  2. Build a Grafana dashboard with the PromQL queries above")
    print("  3. Configure PrometheusRule alert rules for bias threshold violations")
    print("  4. See L2-M5.5 for building production dashboards")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    check_environment()

    # Suppress InsecureRequestWarning for self-signed certificates
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    print()
    print("TrustyAI Model Monitoring Setup")
    print("=" * 60)
    print(f"Target: {BASE_URL}")
    print(f"Model:  {MODEL_NAME}")
    print()

    try:
        check_service_health()
        upload_inference_data()
        configure_spd_monitor()
        configure_dir_monitor()
        configure_drift_monitor()
        query_metrics()
        print_summary()

    except requests.exceptions.ConnectionError:
        print(f"\nError: Lost connection to TrustyAI service at {BASE_URL}", file=sys.stderr)
        print("Check that the TrustyAI pod is still running:", file=sys.stderr)
        print("  oc get pods -n trustyai-tutorial -l app.kubernetes.io/name=trustyai-service", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
