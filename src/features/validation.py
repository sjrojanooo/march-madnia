"""
Feature validation module - data quality gate between feature engineering and model training.

Validates the feature matrix before training begins, checking data integrity,
statistical properties, and cross-feature relationships.
"""

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import skew

logger = logging.getLogger(__name__)

# Expected seasons in the dataset (no 2020 due to COVID cancellation)
EXPECTED_SEASONS = [2019, 2021, 2022, 2023, 2024, 2025]

# Features expected to be in 0-1 range (percentages)
PERCENTAGE_FEATURES = {"efg_pct", "ts_pct", "fg_pct", "ft_pct", "fg3_pct"}

# Seed range
SEED_RANGE = (1, 16)


# ---------------------------------------------------------------------------
# Data Integrity Checks
# ---------------------------------------------------------------------------


def null_audit(df: pd.DataFrame) -> dict[str, float]:
    """Flag features with >5% missing values.

    Returns:
        Dict of {column_name: pct_missing} for columns exceeding 5% threshold.
    """
    if df.empty:
        return {}

    pct_missing = df.isnull().mean()
    flagged = pct_missing[pct_missing > 0.05]
    result = {col: round(float(pct), 4) for col, pct in flagged.items()}

    if result:
        logger.warning("Columns with >5%% missing values: %s", list(result.keys()))
    else:
        logger.info("Null audit passed - no columns exceed 5%% missing threshold.")

    return result


def dtype_check(df: pd.DataFrame) -> list[str]:
    """Verify all feature columns are numeric.

    Returns:
        List of non-numeric column names.
    """
    if df.empty:
        return []

    non_numeric = [col for col in df.columns if not pd.api.types.is_numeric_dtype(df[col])]

    if non_numeric:
        logger.warning("Non-numeric columns found: %s", non_numeric)
    else:
        logger.info("Dtype check passed - all columns are numeric.")

    return non_numeric


def range_validation(df: pd.DataFrame) -> dict[str, tuple[float, float, float, float]]:
    """Check features fall within logical bounds.

    Handles:
        - efg_pct, ts_pct, and other percentage features: 0-1 (flags 0-100 scale)
        - seed: 1-16
        - General percentages: 0-1

    Returns:
        Dict of {col: (actual_min, actual_max, expected_min, expected_max)} for violations.
    """
    if df.empty:
        return {}

    violations: dict[str, tuple[float, float, float, float]] = {}
    numeric_cols = df.select_dtypes(include=[np.number]).columns

    for col in numeric_cols:
        col_lower = col.lower()
        actual_min = float(df[col].min())
        actual_max = float(df[col].max())

        if col_lower == "seed":
            expected_min, expected_max = float(SEED_RANGE[0]), float(SEED_RANGE[1])
            if actual_min < expected_min or actual_max > expected_max:
                violations[col] = (actual_min, actual_max, expected_min, expected_max)

        elif col_lower in PERCENTAGE_FEATURES or col_lower.endswith("_pct"):
            expected_min, expected_max = 0.0, 1.0
            # If values are in 0-100 range, flag for normalization
            if actual_max > 1.0 and actual_max <= 100.0:
                logger.warning(
                    "Column '%s' appears to be on 0-100 scale (max=%.2f). "
                    "Consider normalizing to 0-1.",
                    col,
                    actual_max,
                )
                violations[col] = (actual_min, actual_max, expected_min, expected_max)
            elif actual_min < expected_min or actual_max > expected_max:
                violations[col] = (actual_min, actual_max, expected_min, expected_max)

    if violations:
        logger.warning("Range violations found in %d columns.", len(violations))
    else:
        logger.info("Range validation passed.")

    return violations


def duplicate_check(df: pd.DataFrame) -> int:
    """Check for duplicate rows.

    Returns:
        Count of duplicate rows.
    """
    if df.empty:
        return 0

    n_dupes = int(df.duplicated().sum())

    if n_dupes > 0:
        logger.warning("Found %d duplicate rows.", n_dupes)
    else:
        logger.info("No duplicate rows found.")

    return n_dupes


def season_coverage(df: pd.DataFrame) -> list[int]:
    """Confirm expected seasons are all present.

    Looks for a column named 'season' or 'Season' (case-insensitive).

    Returns:
        List of missing seasons.
    """
    if df.empty:
        return list(EXPECTED_SEASONS)

    season_col = None
    for col in df.columns:
        if col.lower() == "season":
            season_col = col
            break

    if season_col is None:
        logger.warning("No 'season' column found - cannot validate season coverage.")
        return list(EXPECTED_SEASONS)

    present_seasons = set(df[season_col].dropna().unique().astype(int))
    missing = [s for s in EXPECTED_SEASONS if s not in present_seasons]

    if missing:
        logger.warning("Missing seasons: %s", missing)
    else:
        logger.info("Season coverage passed - all expected seasons present.")

    return missing


# ---------------------------------------------------------------------------
# Statistical Validation
# ---------------------------------------------------------------------------


def distribution_analysis(df: pd.DataFrame) -> dict[str, float]:
    """Compute skewness for each numeric column. Flag if abs(skew) > 2.0.

    Returns:
        Dict of {col: skewness_value} for flagged columns.
    """
    if df.empty:
        return {}

    numeric_df = df.select_dtypes(include=[np.number])
    if numeric_df.shape[1] == 0:
        return {}

    flagged: dict[str, float] = {}
    for col in numeric_df.columns:
        col_data = numeric_df[col].dropna()
        if len(col_data) < 3:
            continue
        s = float(skew(col_data, nan_policy="omit"))
        if abs(s) > 2.0:
            flagged[col] = round(s, 4)

    if flagged:
        logger.warning("Highly skewed features (|skew| > 2.0): %s", list(flagged.keys()))
    else:
        logger.info("Distribution analysis passed - no extreme skewness detected.")

    return flagged


def outlier_detection(df: pd.DataFrame) -> dict[str, int]:
    """IQR-based outlier detection.

    Values beyond Q1 - 1.5*IQR or Q3 + 1.5*IQR are considered outliers.

    Returns:
        Dict of {col: n_outliers} for columns with outliers.
    """
    if df.empty:
        return {}

    numeric_df = df.select_dtypes(include=[np.number])
    result: dict[str, int] = {}

    for col in numeric_df.columns:
        col_data = numeric_df[col].dropna()
        if len(col_data) < 4:
            continue

        q1 = float(col_data.quantile(0.25))
        q3 = float(col_data.quantile(0.75))
        iqr = q3 - q1

        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        n_outliers = int(((col_data < lower_bound) | (col_data > upper_bound)).sum())
        if n_outliers > 0:
            result[col] = n_outliers

    if result:
        logger.info("Outliers detected in %d columns.", len(result))

    return result


def correlation_matrix(df: pd.DataFrame) -> list[tuple[str, str, float]]:
    """Find highly correlated feature pairs (>0.90).

    Returns:
        List of (col1, col2, correlation) tuples.
    """
    if df.empty:
        return []

    numeric_df = df.select_dtypes(include=[np.number])
    if numeric_df.shape[1] < 2:
        return []

    corr = numeric_df.corr()
    high_corr: list[tuple[str, str, float]] = []

    for i in range(len(corr.columns)):
        for j in range(i + 1, len(corr.columns)):
            val = corr.iloc[i, j]
            if abs(val) > 0.90:
                high_corr.append((corr.columns[i], corr.columns[j], round(float(val), 4)))

    if high_corr:
        logger.warning("Found %d highly correlated feature pairs (|r| > 0.90).", len(high_corr))
    else:
        logger.info("No highly correlated feature pairs found.")

    return high_corr


def variance_check(df: pd.DataFrame) -> list[str]:
    """Flag near-zero variance features (std < 0.01).

    Returns:
        List of column names with near-zero variance.
    """
    if df.empty:
        return []

    numeric_df = df.select_dtypes(include=[np.number])
    low_var = [col for col in numeric_df.columns if numeric_df[col].std() < 0.01]

    if low_var:
        logger.warning("Near-zero variance features: %s", low_var)
    else:
        logger.info("Variance check passed.")

    return low_var


def target_leakage_check(df: pd.DataFrame, target_col: str) -> list[str]:
    """Check if any feature has >0.95 correlation with target.

    Returns:
        List of suspicious column names.
    """
    if df.empty or target_col not in df.columns:
        return []

    numeric_df = df.select_dtypes(include=[np.number])
    if target_col not in numeric_df.columns or numeric_df.shape[1] < 2:
        return []

    feature_cols = [c for c in numeric_df.columns if c != target_col]
    if not feature_cols:
        return []

    corr_with_target = numeric_df[feature_cols].corrwith(numeric_df[target_col])
    suspicious = [col for col, val in corr_with_target.items() if abs(val) > 0.95]

    if suspicious:
        logger.warning("Potential target leakage detected: %s", suspicious)
    else:
        logger.info("No target leakage detected.")

    return suspicious


# ---------------------------------------------------------------------------
# Cross-Feature Validation
# ---------------------------------------------------------------------------


def feature_target_correlation(df: pd.DataFrame, target_col: str) -> dict[str, float]:
    """Compute correlation of each feature with target.

    Flags features with abs(corr) < 0.01 as potentially useless.

    Returns:
        Dict of {col: correlation} for potentially useless features.
    """
    if df.empty or target_col not in df.columns:
        return {}

    numeric_df = df.select_dtypes(include=[np.number])
    if target_col not in numeric_df.columns or numeric_df.shape[1] < 2:
        return {}

    feature_cols = [c for c in numeric_df.columns if c != target_col]
    if not feature_cols:
        return {}

    corr_with_target = numeric_df[feature_cols].corrwith(numeric_df[target_col])
    weak = {col: round(float(val), 6) for col, val in corr_with_target.items() if abs(val) < 0.01}

    if weak:
        logger.info(
            "Features with near-zero target correlation (|r| < 0.01): %s",
            list(weak.keys()),
        )

    return weak


def vif_multicollinearity(df: pd.DataFrame) -> dict[str, float]:
    """Variance Inflation Factor for each feature. Flags VIF > 10.

    Uses statsmodels if available, otherwise computes manually as 1/(1-R^2)
    from OLS regression of each feature against all others.

    Returns:
        Dict of {col: vif_value} for features with VIF > 10.
    """
    if df.empty:
        return {}

    numeric_df = df.select_dtypes(include=[np.number]).dropna()
    if numeric_df.shape[1] < 2 or numeric_df.shape[0] < numeric_df.shape[1]:
        logger.warning(
            "Insufficient data for VIF computation (rows=%d, cols=%d).",
            numeric_df.shape[0],
            numeric_df.shape[1],
        )
        return {}

    try:
        from statsmodels.stats.outliers_influence import variance_inflation_factor

        vif_data: dict[str, float] = {}
        X = numeric_df.values.astype(float)

        for i, col in enumerate(numeric_df.columns):
            try:
                vif_val = float(variance_inflation_factor(X, i))
                if vif_val > 10:
                    vif_data[col] = round(vif_val, 2)
            except Exception:
                logger.debug("VIF computation failed for column '%s'.", col)
                continue

    except ImportError:
        logger.info("statsmodels not available, computing VIF manually.")
        vif_data = {}

        for col in numeric_df.columns:
            other_cols = [c for c in numeric_df.columns if c != col]
            if not other_cols:
                continue

            y = numeric_df[col].values
            X = numeric_df[other_cols].values

            # Add intercept
            X = np.column_stack([np.ones(X.shape[0]), X])

            try:
                # OLS: beta = (X'X)^-1 X'y
                beta = np.linalg.lstsq(X, y, rcond=None)[0]
                y_pred = X @ beta
                ss_res = np.sum((y - y_pred) ** 2)
                ss_tot = np.sum((y - np.mean(y)) ** 2)

                if ss_tot == 0:
                    continue

                r_squared = 1 - (ss_res / ss_tot)

                if r_squared >= 1.0:
                    vif_val = float("inf")
                else:
                    vif_val = 1.0 / (1.0 - r_squared)

                if vif_val > 10:
                    vif_data[col] = round(vif_val, 2)
            except Exception:
                logger.debug("Manual VIF computation failed for column '%s'.", col)
                continue

    if vif_data:
        logger.warning("High VIF features (>10): %s", list(vif_data.keys()))
    else:
        logger.info("VIF check passed - no severe multicollinearity detected.")

    return vif_data


def class_balance(df: pd.DataFrame, target_col: str) -> dict[str, Any]:
    """Check win/loss ratio is approximately 50/50.

    Returns:
        Dict with 'counts', 'ratios', and 'balanced' (bool) keys.
    """
    if df.empty or target_col not in df.columns:
        return {"counts": {}, "ratios": {}, "balanced": False}

    counts = df[target_col].value_counts()
    total = len(df[target_col].dropna())

    if total == 0:
        return {"counts": {}, "ratios": {}, "balanced": False}

    ratios = {str(k): round(float(v / total), 4) for k, v in counts.items()}
    counts_dict = {str(k): int(v) for k, v in counts.items()}

    # Consider balanced if the majority class is <60%
    max_ratio = max(ratios.values()) if ratios else 0
    balanced = max_ratio < 0.60

    result = {"counts": counts_dict, "ratios": ratios, "balanced": balanced}

    if not balanced:
        logger.warning("Class imbalance detected: %s", ratios)
    else:
        logger.info("Class balance check passed: %s", ratios)

    return result


# ---------------------------------------------------------------------------
# Main Validation Function
# ---------------------------------------------------------------------------


def validate_features(df: pd.DataFrame, target_col: str = "target") -> dict:
    """Run all validation checks and return a comprehensive report.

    Args:
        df: Feature matrix DataFrame.
        target_col: Name of the target column.

    Returns:
        Dict containing results from all validation checks.
    """
    logger.info("Starting feature validation on DataFrame with shape %s", df.shape)

    report: dict[str, Any] = {
        "shape": {"rows": df.shape[0], "cols": df.shape[1]},
        "target_col": target_col,
    }

    # Data Integrity Checks
    logger.info("Running data integrity checks...")
    report["null_audit"] = null_audit(df)
    report["non_numeric_columns"] = dtype_check(df)
    report["range_violations"] = {col: list(vals) for col, vals in range_validation(df).items()}
    report["duplicate_rows"] = duplicate_check(df)
    report["missing_seasons"] = season_coverage(df)

    # Statistical Validation
    logger.info("Running statistical validation...")
    report["skewed_features"] = distribution_analysis(df)
    report["outliers"] = outlier_detection(df)
    report["high_correlations"] = [
        {"col1": c1, "col2": c2, "correlation": r} for c1, c2, r in correlation_matrix(df)
    ]
    report["zero_variance_features"] = variance_check(df)
    report["target_leakage"] = target_leakage_check(df, target_col)

    # Cross-Feature Validation
    logger.info("Running cross-feature validation...")
    report["weak_target_features"] = feature_target_correlation(df, target_col)
    report["high_vif_features"] = vif_multicollinearity(
        df.select_dtypes(include=[np.number]).drop(columns=[target_col], errors="ignore")
    )
    report["class_balance"] = class_balance(df, target_col)

    # Summary
    n_issues = sum(
        [
            len(report["null_audit"]),
            len(report["non_numeric_columns"]),
            len(report["range_violations"]),
            report["duplicate_rows"],
            len(report["missing_seasons"]),
            len(report["skewed_features"]),
            len(report["zero_variance_features"]),
            len(report["target_leakage"]),
        ]
    )
    report["total_issues"] = n_issues
    report["status"] = "PASS" if n_issues == 0 else "WARN"

    logger.info("Validation complete. Status: %s (%d issues).", report["status"], n_issues)

    return report


# ---------------------------------------------------------------------------
# Auto-Clean
# ---------------------------------------------------------------------------


def auto_clean(df: pd.DataFrame, report: dict) -> pd.DataFrame:
    """Auto-drop features that fail critical checks.

    Drops:
        - Zero-variance features
        - Features with >50% null
        - Confirmed target leakage features

    Args:
        df: Original DataFrame.
        report: Validation report from validate_features().

    Returns:
        Cleaned DataFrame.
    """
    cols_to_drop: set[str] = set()

    # Zero-variance features
    zero_var = report.get("zero_variance_features", [])
    if zero_var:
        cols_to_drop.update(zero_var)
        logger.info("Dropping zero-variance features: %s", zero_var)

    # Features with >50% null
    null_info = report.get("null_audit", {})
    high_null = [col for col, pct in null_info.items() if pct > 0.50]
    if high_null:
        cols_to_drop.update(high_null)
        logger.info("Dropping features with >50%% missing: %s", high_null)

    # Target leakage features
    leakage = report.get("target_leakage", [])
    if leakage:
        cols_to_drop.update(leakage)
        logger.info("Dropping target leakage features: %s", leakage)

    # Only drop columns that actually exist in the DataFrame
    cols_to_drop = cols_to_drop.intersection(set(df.columns))

    if cols_to_drop:
        logger.info(
            "Auto-clean dropping %d columns total: %s", len(cols_to_drop), sorted(cols_to_drop)
        )
        df = df.drop(columns=list(cols_to_drop))
    else:
        logger.info("Auto-clean: no columns to drop.")

    return df


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_validation_report(report: dict) -> None:
    """Pretty-print the validation report using Rich tables."""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.print()
    console.rule("[bold blue]Feature Validation Report[/bold blue]")
    console.print()

    # Overview
    overview = Table(title="Overview", show_header=True, header_style="bold cyan")
    overview.add_column("Metric", style="dim")
    overview.add_column("Value")
    overview.add_row("Rows", str(report.get("shape", {}).get("rows", "N/A")))
    overview.add_row("Columns", str(report.get("shape", {}).get("cols", "N/A")))
    overview.add_row("Target Column", str(report.get("target_col", "N/A")))
    status = report.get("status", "N/A")
    status_style = "[green]PASS[/green]" if status == "PASS" else "[yellow]WARN[/yellow]"
    overview.add_row("Status", status_style)
    overview.add_row("Total Issues", str(report.get("total_issues", 0)))
    console.print(overview)
    console.print()

    # Null Audit
    null_info = report.get("null_audit", {})
    if null_info:
        t = Table(title="Null Audit (>5% missing)", show_header=True, header_style="bold red")
        t.add_column("Column")
        t.add_column("% Missing", justify="right")
        for col, pct in sorted(null_info.items(), key=lambda x: x[1], reverse=True):
            t.add_row(col, f"{pct:.2%}")
        console.print(t)
        console.print()
    else:
        console.print("[green]Null Audit: PASS[/green]")

    # Non-numeric columns
    non_numeric = report.get("non_numeric_columns", [])
    if non_numeric:
        console.print(f"[yellow]Non-numeric columns: {non_numeric}[/yellow]")
    else:
        console.print("[green]Dtype Check: PASS[/green]")

    # Range violations
    range_v = report.get("range_violations", {})
    if range_v:
        t = Table(title="Range Violations", show_header=True, header_style="bold red")
        t.add_column("Column")
        t.add_column("Actual Min", justify="right")
        t.add_column("Actual Max", justify="right")
        t.add_column("Expected Min", justify="right")
        t.add_column("Expected Max", justify="right")
        for col, vals in range_v.items():
            t.add_row(col, f"{vals[0]:.4f}", f"{vals[1]:.4f}", f"{vals[2]:.4f}", f"{vals[3]:.4f}")
        console.print(t)
        console.print()
    else:
        console.print("[green]Range Validation: PASS[/green]")

    # Duplicates
    n_dupes = report.get("duplicate_rows", 0)
    if n_dupes > 0:
        console.print(f"[yellow]Duplicate rows: {n_dupes}[/yellow]")
    else:
        console.print("[green]Duplicate Check: PASS[/green]")

    # Season coverage
    missing_seasons = report.get("missing_seasons", [])
    if missing_seasons:
        console.print(f"[yellow]Missing seasons: {missing_seasons}[/yellow]")
    else:
        console.print("[green]Season Coverage: PASS[/green]")

    console.print()

    # Skewed features
    skewed = report.get("skewed_features", {})
    if skewed:
        t = Table(
            title="Highly Skewed Features (|skew| > 2.0)",
            show_header=True,
            header_style="bold yellow",
        )
        t.add_column("Column")
        t.add_column("Skewness", justify="right")
        for col, val in sorted(skewed.items(), key=lambda x: abs(x[1]), reverse=True):
            t.add_row(col, f"{val:.4f}")
        console.print(t)
        console.print()

    # Outliers
    outliers = report.get("outliers", {})
    if outliers:
        t = Table(title="Outlier Detection (IQR)", show_header=True, header_style="bold yellow")
        t.add_column("Column")
        t.add_column("# Outliers", justify="right")
        for col, n in sorted(outliers.items(), key=lambda x: x[1], reverse=True):
            t.add_row(col, str(n))
        console.print(t)
        console.print()

    # High correlations
    high_corr = report.get("high_correlations", [])
    if high_corr:
        t = Table(
            title="Highly Correlated Pairs (|r| > 0.90)",
            show_header=True,
            header_style="bold yellow",
        )
        t.add_column("Feature 1")
        t.add_column("Feature 2")
        t.add_column("Correlation", justify="right")
        for item in high_corr:
            t.add_row(item["col1"], item["col2"], f"{item['correlation']:.4f}")
        console.print(t)
        console.print()

    # Zero variance
    zero_var = report.get("zero_variance_features", [])
    if zero_var:
        console.print(f"[red]Zero-variance features: {zero_var}[/red]")
    else:
        console.print("[green]Variance Check: PASS[/green]")

    # Target leakage
    leakage = report.get("target_leakage", [])
    if leakage:
        console.print(f"[bold red]TARGET LEAKAGE DETECTED: {leakage}[/bold red]")
    else:
        console.print("[green]Target Leakage Check: PASS[/green]")

    console.print()

    # Class balance
    cb = report.get("class_balance", {})
    if cb:
        balanced_str = "[green]Yes[/green]" if cb.get("balanced") else "[yellow]No[/yellow]"
        console.print(f"Class Balance: {balanced_str}  |  Ratios: {cb.get('ratios', {})}")

    # VIF
    vif = report.get("high_vif_features", {})
    if vif:
        t = Table(title="High VIF Features (>10)", show_header=True, header_style="bold yellow")
        t.add_column("Column")
        t.add_column("VIF", justify="right")
        for col, val in sorted(vif.items(), key=lambda x: x[1], reverse=True):
            t.add_row(col, f"{val:.2f}")
        console.print(t)
        console.print()

    # Weak features
    weak = report.get("weak_target_features", {})
    if weak:
        t = Table(
            title="Weak Target Correlation (|r| < 0.01)", show_header=True, header_style="dim"
        )
        t.add_column("Column")
        t.add_column("Correlation", justify="right")
        for col, val in weak.items():
            t.add_row(col, f"{val:.6f}")
        console.print(t)

    console.print()
    console.rule("[bold blue]End of Report[/bold blue]")
    console.print()


def save_validation_report(
    report: dict, path: str = "data/processed/validation_report.json"
) -> None:
    """Save the validation report as JSON.

    Args:
        report: Validation report dict from validate_features().
        path: Output file path. Defaults to data/processed/validation_report.json.
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert any non-serializable types
    def _serialize(obj: Any) -> Any:
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, set):
            return list(obj)
        return obj

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=_serialize)

    logger.info("Validation report saved to %s", output_path)
