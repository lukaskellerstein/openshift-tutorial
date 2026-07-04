"""
Agent Regression Test -- Compare Two Agent Versions

Loads evaluation results for two agent versions from MLflow and performs
a statistical comparison to detect regressions. Outputs a comparison
report with metric deltas, p-values, and pass/fail verdicts.

This script is designed to run after two evaluation pipeline runs have
completed (one for the baseline agent version and one for the candidate).
It reads the detailed per-scenario results logged as MLflow artifacts and
computes statistical significance for each metric dimension.

Usage:
    python agent_regression_test.py \
        --baseline-version v1.0.0 \
        --candidate-version v1.1.0 \
        --mlflow-tracking-uri http://mlflow.mlflow.svc:5000 \
        --experiment-name agent-eval \
        --output-json regression_report.json

    # With custom thresholds
    python agent_regression_test.py \
        --baseline-version v1.0.0 \
        --candidate-version v1.1.0 \
        --mlflow-tracking-uri http://mlflow.mlflow.svc:5000 \
        --experiment-name agent-eval \
        --max-regression 0.05 \
        --significance-level 0.05

Requirements:
    pip install mlflow==2.22.0 scipy==1.14.0
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from typing import Optional

import mlflow
from mlflow.tracking import MlflowClient
from scipy import stats


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MetricComparison:
    """Result of comparing a single metric between two versions."""

    metric_name: str
    baseline_value: float
    candidate_value: float
    delta: float
    delta_percent: float
    p_value: Optional[float]
    test_used: str
    is_significant: bool
    direction: str  # "higher_is_better" or "lower_is_better"
    verdict: str    # "PASS", "REGRESSION", "IMPROVEMENT", or "NO_DATA"


@dataclass
class RegressionReport:
    """Full regression test report comparing two agent versions."""

    baseline_version: str
    candidate_version: str
    experiment_name: str
    comparisons: list
    overall_verdict: str  # "PASS" or "REGRESSION"
    regression_count: int
    improvement_count: int
    neutral_count: int


# ---------------------------------------------------------------------------
# MLflow data retrieval
# ---------------------------------------------------------------------------

def get_run_by_version(
    client: MlflowClient,
    experiment_name: str,
    agent_version: str,
) -> Optional[mlflow.entities.Run]:
    """Find the most recent MLflow run for a given agent version.

    Searches the specified experiment for runs tagged with the given
    agent version. Returns the most recent run if multiple exist.

    Args:
        client: MLflow tracking client.
        experiment_name: Name of the MLflow experiment.
        agent_version: Agent version string to search for.

    Returns:
        The MLflow Run object, or None if not found.
    """
    experiment = client.get_experiment_by_name(experiment_name)
    if experiment is None:
        print(f"ERROR: Experiment '{experiment_name}' not found")
        return None

    # Search for runs with the matching agent_version parameter
    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string=f"params.agent_version = '{agent_version}'",
        order_by=["start_time DESC"],
        max_results=1,
    )

    if not runs:
        print(f"ERROR: No run found for agent version '{agent_version}'")
        return None

    return runs[0]


def get_run_metrics(run: mlflow.entities.Run) -> dict:
    """Extract evaluation metrics from an MLflow run.

    Args:
        run: MLflow Run object.

    Returns:
        Dictionary of metric name to metric value.
    """
    return {
        key: value
        for key, value in run.data.metrics.items()
    }


def get_detailed_results(
    client: MlflowClient,
    run: mlflow.entities.Run,
) -> Optional[dict]:
    """Download and parse the detailed results artifact from an MLflow run.

    The evaluation pipeline logs a JSON artifact at
    evaluation/detailed_results containing per-scenario metrics.

    Args:
        client: MLflow tracking client.
        run: MLflow Run object.

    Returns:
        Parsed JSON dict of detailed results, or None on error.
    """
    import os
    import tempfile

    try:
        # Download the evaluation artifacts directory
        artifact_dir = client.download_artifacts(
            run.info.run_id,
            "evaluation",
            dst_path=tempfile.mkdtemp(),
        )

        # Look for the detailed results file
        for filename in os.listdir(artifact_dir):
            if "detailed" in filename or filename.endswith(".json"):
                filepath = os.path.join(artifact_dir, filename)
                with open(filepath, "r") as f:
                    return json.load(f)

    except Exception as e:
        print(f"WARNING: Could not load detailed results: {e}")

    return None


# ---------------------------------------------------------------------------
# Statistical tests
# ---------------------------------------------------------------------------

def compare_rates(
    baseline_successes: int,
    baseline_total: int,
    candidate_successes: int,
    candidate_total: int,
) -> tuple[float, str]:
    """Compare two success rates using a two-proportion z-test.

    Used for categorical metrics like task completion rate and safety
    compliance rate.

    Args:
        baseline_successes: Number of successes in baseline.
        baseline_total: Total scenarios in baseline.
        candidate_successes: Number of successes in candidate.
        candidate_total: Total scenarios in candidate.

    Returns:
        Tuple of (p_value, test_name).
    """
    # Pooled proportion
    p_pool = (baseline_successes + candidate_successes) / (
        baseline_total + candidate_total
    )

    # Avoid division by zero
    if p_pool == 0 or p_pool == 1:
        return 1.0, "two-proportion-z-test"

    # Standard error
    se = (p_pool * (1 - p_pool) * (1 / baseline_total + 1 / candidate_total)) ** 0.5

    if se == 0:
        return 1.0, "two-proportion-z-test"

    # Z statistic
    p1 = baseline_successes / baseline_total
    p2 = candidate_successes / candidate_total
    z = (p2 - p1) / se

    # Two-tailed p-value
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    return p_value, "two-proportion-z-test"


def compare_continuous(
    baseline_values: list[float],
    candidate_values: list[float],
) -> tuple[float, str]:
    """Compare two sets of continuous measurements using Welch's t-test.

    Used for continuous metrics like response time. Welch's t-test does
    not assume equal variances between the two groups.

    Args:
        baseline_values: List of metric values from the baseline run.
        candidate_values: List of metric values from the candidate run.

    Returns:
        Tuple of (p_value, test_name).
    """
    if len(baseline_values) < 2 or len(candidate_values) < 2:
        return 1.0, "welch-t-test (insufficient data)"

    result = stats.ttest_ind(
        baseline_values,
        candidate_values,
        equal_var=False,  # Welch's t-test
    )
    return result.pvalue, "welch-t-test"


# ---------------------------------------------------------------------------
# Core comparison logic
# ---------------------------------------------------------------------------

def run_comparison(
    baseline_metrics: dict,
    candidate_metrics: dict,
    baseline_detailed: Optional[dict],
    candidate_detailed: Optional[dict],
    max_regression: float,
    significance_level: float,
) -> list[MetricComparison]:
    """Compare all metrics between baseline and candidate.

    For each metric dimension, computes the delta, performs a statistical
    test (where per-scenario data is available), and renders a verdict.

    Args:
        baseline_metrics: Aggregated metrics from the baseline run.
        candidate_metrics: Aggregated metrics from the candidate run.
        baseline_detailed: Per-scenario results from the baseline (optional).
        candidate_detailed: Per-scenario results from the candidate (optional).
        max_regression: Maximum allowed regression before marking as FAIL.
                        For rate metrics (0-1), this is an absolute delta.
                        For time metrics, this is a relative percentage.
        significance_level: P-value threshold for statistical significance.

    Returns:
        List of MetricComparison results.
    """

    # Define which metrics to compare and their properties
    metric_configs = [
        {
            "name": "task_completion_rate",
            "direction": "higher_is_better",
            "is_rate": True,
        },
        {
            "name": "tool_selection_precision",
            "direction": "higher_is_better",
            "is_rate": True,
        },
        {
            "name": "tool_selection_recall",
            "direction": "higher_is_better",
            "is_rate": True,
        },
        {
            "name": "reasoning_score",
            "direction": "higher_is_better",
            "is_rate": True,
        },
        {
            "name": "avg_response_time",
            "direction": "lower_is_better",
            "is_rate": False,
        },
        {
            "name": "p95_response_time",
            "direction": "lower_is_better",
            "is_rate": False,
        },
        {
            "name": "safety_compliance_rate",
            "direction": "higher_is_better",
            "is_rate": True,
        },
    ]

    comparisons = []

    for config in metric_configs:
        name = config["name"]

        # Get metric values
        baseline_val = baseline_metrics.get(name)
        candidate_val = candidate_metrics.get(name)

        if baseline_val is None or candidate_val is None:
            comparisons.append(MetricComparison(
                metric_name=name,
                baseline_value=baseline_val or 0.0,
                candidate_value=candidate_val or 0.0,
                delta=0.0,
                delta_percent=0.0,
                p_value=None,
                test_used="none",
                is_significant=False,
                direction=config["direction"],
                verdict="NO_DATA",
            ))
            continue

        # Compute delta
        delta = candidate_val - baseline_val
        delta_percent = (
            (delta / baseline_val * 100) if baseline_val != 0 else 0.0
        )

        # Statistical testing
        # Use per-scenario data if available for more granular comparison
        p_value = None
        test_used = "aggregate-only"

        if baseline_detailed and candidate_detailed:
            baseline_scenarios = baseline_detailed.get("per_scenario", [])
            candidate_scenarios = candidate_detailed.get("per_scenario", [])

            if name in ("avg_response_time", "p95_response_time"):
                # Extract per-scenario response times
                b_times = [s["response_time"] for s in baseline_scenarios if s.get("response_time")]
                c_times = [s["response_time"] for s in candidate_scenarios if s.get("response_time")]
                if b_times and c_times:
                    p_value, test_used = compare_continuous(b_times, c_times)

            elif config["is_rate"]:
                # For rate metrics, use the aggregate counts for a proportions test
                b_total = int(baseline_metrics.get("total_scenarios", 0))
                c_total = int(candidate_metrics.get("total_scenarios", 0))
                if b_total > 0 and c_total > 0:
                    b_successes = int(round(baseline_val * b_total))
                    c_successes = int(round(candidate_val * c_total))
                    p_value, test_used = compare_rates(
                        b_successes, b_total, c_successes, c_total
                    )

        is_significant = p_value is not None and p_value < significance_level

        # Determine verdict
        if config["direction"] == "higher_is_better":
            is_regression = delta < -max_regression
            is_improvement = delta > max_regression and is_significant
        else:
            # Lower is better (e.g., response time)
            is_regression = delta > (baseline_val * max_regression) if baseline_val > 0 else delta > 0
            is_improvement = delta < -(baseline_val * max_regression) if baseline_val > 0 else delta < 0
            is_improvement = is_improvement and is_significant

        if is_regression and is_significant:
            verdict = "REGRESSION"
        elif is_improvement:
            verdict = "IMPROVEMENT"
        else:
            verdict = "PASS"

        comparisons.append(MetricComparison(
            metric_name=name,
            baseline_value=round(baseline_val, 4),
            candidate_value=round(candidate_val, 4),
            delta=round(delta, 4),
            delta_percent=round(delta_percent, 2),
            p_value=round(p_value, 6) if p_value is not None else None,
            test_used=test_used,
            is_significant=is_significant,
            direction=config["direction"],
            verdict=verdict,
        ))

    return comparisons


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def print_report(report: RegressionReport):
    """Print the regression report as a formatted console table.

    Args:
        report: The full regression report.
    """
    print()
    print("=" * 90)
    print("AGENT REGRESSION TEST REPORT")
    print("=" * 90)
    print(f"  Baseline:  {report.baseline_version}")
    print(f"  Candidate: {report.candidate_version}")
    print(f"  Experiment: {report.experiment_name}")
    print("-" * 90)
    print(
        f"  {'Metric':<30} {'Baseline':>10} {'Candidate':>10} "
        f"{'Delta':>10} {'p-value':>10} {'Verdict':>12}"
    )
    print("-" * 90)

    for c in report.comparisons:
        p_str = f"{c.p_value:.4f}" if c.p_value is not None else "N/A"
        delta_str = f"{c.delta:+.4f}"

        # Color-code the verdict for terminal output
        verdict_str = c.verdict
        if c.verdict == "REGRESSION":
            verdict_str = f"** {c.verdict} **"
        elif c.verdict == "IMPROVEMENT":
            verdict_str = f"++ {c.verdict} ++"

        print(
            f"  {c.metric_name:<30} {c.baseline_value:>10.4f} "
            f"{c.candidate_value:>10.4f} {delta_str:>10} "
            f"{p_str:>10} {verdict_str:>12}"
        )

    print("-" * 90)
    print(
        f"  Regressions: {report.regression_count}  |  "
        f"Improvements: {report.improvement_count}  |  "
        f"Neutral: {report.neutral_count}"
    )
    print(f"  Overall verdict: {report.overall_verdict}")
    print("=" * 90)
    print()


def save_report_json(report: RegressionReport, output_path: str):
    """Save the regression report as a JSON file.

    Args:
        report: The full regression report.
        output_path: File path to write the JSON report to.
    """
    # Convert dataclasses to dicts
    report_dict = {
        "baseline_version": report.baseline_version,
        "candidate_version": report.candidate_version,
        "experiment_name": report.experiment_name,
        "overall_verdict": report.overall_verdict,
        "regression_count": report.regression_count,
        "improvement_count": report.improvement_count,
        "neutral_count": report.neutral_count,
        "comparisons": [asdict(c) for c in report.comparisons],
    }

    with open(output_path, "w") as f:
        json.dump(report_dict, f, indent=2)

    print(f"Report saved to {output_path}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Compare evaluation results between two agent versions. "
            "Reads metrics from MLflow, performs statistical significance "
            "testing, and produces a regression report."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Basic comparison\n"
            "  python agent_regression_test.py \\\n"
            "      --baseline-version v1.0.0 \\\n"
            "      --candidate-version v1.1.0 \\\n"
            "      --mlflow-tracking-uri http://mlflow.mlflow.svc:5000 \\\n"
            "      --experiment-name agent-eval\n"
            "\n"
            "  # Strict thresholds, JSON output\n"
            "  python agent_regression_test.py \\\n"
            "      --baseline-version v1.0.0 \\\n"
            "      --candidate-version v1.1.0 \\\n"
            "      --mlflow-tracking-uri http://mlflow.mlflow.svc:5000 \\\n"
            "      --experiment-name agent-eval \\\n"
            "      --max-regression 0.02 \\\n"
            "      --significance-level 0.01 \\\n"
            "      --output-json report.json\n"
        ),
    )

    parser.add_argument(
        "--baseline-version",
        required=True,
        help="Agent version to use as the baseline (e.g., v1.0.0).",
    )
    parser.add_argument(
        "--candidate-version",
        required=True,
        help="Agent version to compare against the baseline (e.g., v1.1.0).",
    )
    parser.add_argument(
        "--mlflow-tracking-uri",
        required=True,
        help="URI of the MLflow tracking server (e.g., http://mlflow.mlflow.svc:5000).",
    )
    parser.add_argument(
        "--experiment-name",
        required=True,
        help="Name of the MLflow experiment containing the evaluation runs.",
    )
    parser.add_argument(
        "--max-regression",
        type=float,
        default=0.05,
        help=(
            "Maximum allowed regression before marking as FAIL. "
            "For rate metrics (0-1 scale), this is an absolute delta. "
            "For time metrics, this is a relative fraction. Default: 0.05."
        ),
    )
    parser.add_argument(
        "--significance-level",
        type=float,
        default=0.05,
        help=(
            "P-value threshold for statistical significance. "
            "Changes below this p-value are considered statistically "
            "significant. Default: 0.05."
        ),
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Path to write the regression report as JSON. Optional.",
    )

    args = parser.parse_args()

    # ---- Connect to MLflow -----------------------------------------------
    mlflow.set_tracking_uri(args.mlflow_tracking_uri)
    client = MlflowClient()

    # ---- Retrieve runs ---------------------------------------------------
    print(f"Looking up baseline version: {args.baseline_version}")
    baseline_run = get_run_by_version(
        client, args.experiment_name, args.baseline_version
    )
    if baseline_run is None:
        print(
            f"Could not find a run for baseline version "
            f"'{args.baseline_version}' in experiment '{args.experiment_name}'."
        )
        sys.exit(1)
    print(f"  Found run: {baseline_run.info.run_id}")

    print(f"Looking up candidate version: {args.candidate_version}")
    candidate_run = get_run_by_version(
        client, args.experiment_name, args.candidate_version
    )
    if candidate_run is None:
        print(
            f"Could not find a run for candidate version "
            f"'{args.candidate_version}' in experiment '{args.experiment_name}'."
        )
        sys.exit(1)
    print(f"  Found run: {candidate_run.info.run_id}")

    # ---- Extract metrics -------------------------------------------------
    baseline_metrics = get_run_metrics(baseline_run)
    candidate_metrics = get_run_metrics(candidate_run)

    print(f"\nBaseline metrics: {json.dumps(baseline_metrics, indent=2)}")
    print(f"Candidate metrics: {json.dumps(candidate_metrics, indent=2)}")

    # ---- Load detailed results (if available) ----------------------------
    print("\nLoading detailed per-scenario results...")
    baseline_detailed = get_detailed_results(client, baseline_run)
    candidate_detailed = get_detailed_results(client, candidate_run)

    if baseline_detailed:
        print("  Baseline detailed results loaded")
    else:
        print("  WARNING: No detailed results for baseline -- statistical tests will be limited")

    if candidate_detailed:
        print("  Candidate detailed results loaded")
    else:
        print("  WARNING: No detailed results for candidate -- statistical tests will be limited")

    # ---- Run comparison --------------------------------------------------
    comparisons = run_comparison(
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
        baseline_detailed=baseline_detailed,
        candidate_detailed=candidate_detailed,
        max_regression=args.max_regression,
        significance_level=args.significance_level,
    )

    # ---- Build report ----------------------------------------------------
    regression_count = sum(1 for c in comparisons if c.verdict == "REGRESSION")
    improvement_count = sum(1 for c in comparisons if c.verdict == "IMPROVEMENT")
    neutral_count = sum(
        1 for c in comparisons if c.verdict in ("PASS", "NO_DATA")
    )
    overall_verdict = "REGRESSION" if regression_count > 0 else "PASS"

    report = RegressionReport(
        baseline_version=args.baseline_version,
        candidate_version=args.candidate_version,
        experiment_name=args.experiment_name,
        comparisons=comparisons,
        overall_verdict=overall_verdict,
        regression_count=regression_count,
        improvement_count=improvement_count,
        neutral_count=neutral_count,
    )

    # ---- Output report ---------------------------------------------------
    print_report(report)

    if args.output_json:
        save_report_json(report, args.output_json)

    # ---- Exit code -------------------------------------------------------
    # Exit 1 if any regressions detected (useful for CI/CD pipelines)
    if overall_verdict == "REGRESSION":
        print("Exiting with code 1 (regression detected)")
        sys.exit(1)
    else:
        print("Exiting with code 0 (no regressions)")
        sys.exit(0)


if __name__ == "__main__":
    main()
