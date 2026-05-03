"""
FluxAudit Validation Engine
IoT Dataset Validation with Temporal Drift, Cross-Sensor Logic, and Statistical Analysis
"""

import json
import math
import statistics
from datetime import datetime, timezone
from typing import Any

# ─────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────

def make_result(sensor_id, score, drift, issues, outliers, cross_sensor_flags, schema_ok, stats):
    return {
        "sensor_id": sensor_id,
        "health_score": round(score, 2),
        "temporal_drift_score": round(drift, 2),
        "issues": issues,
        "outlier_count": outliers,
        "cross_sensor_flags": cross_sensor_flags,
        "schema_valid": schema_ok,
        "statistics": stats,
    }


# ─────────────────────────────────────────────
# MODULE 1: TEMPORAL DRIFT SCORING
# ─────────────────────────────────────────────

def compute_temporal_drift(timestamps: list[str], expected_interval_seconds: float = 60.0) -> dict:
    """
    Calculates a Temporal Drift Score based on:
    - Timestamp gap consistency (std dev of intervals vs expected)
    - Missing samples (gaps > 2x expected interval)
    - Out-of-order timestamps
    """
    if len(timestamps) < 2:
        return {"drift_score": 0.0, "issues": ["insufficient_data"], "gaps": []}

    parsed = []
    issues = []
    for ts in timestamps:
        try:
            # Accept ISO format or epoch
            if isinstance(ts, (int, float)):
                parsed.append(float(ts))
            else:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                parsed.append(dt.timestamp())
        except (ValueError, AttributeError):
            issues.append(f"unparseable_timestamp: {ts}")

    if len(parsed) < 2:
        return {"drift_score": 0.0, "issues": issues + ["all_timestamps_invalid"], "gaps": []}

    intervals = [parsed[i + 1] - parsed[i] for i in range(len(parsed) - 1)]
    out_of_order = sum(1 for iv in intervals if iv < 0)
    if out_of_order:
        issues.append(f"out_of_order_timestamps: {out_of_order}")

    positive_intervals = [abs(iv) for iv in intervals]
    mean_interval = statistics.mean(positive_intervals)
    std_interval = statistics.pstdev(positive_intervals) if len(positive_intervals) > 1 else 0.0

    # Coefficient of variation — lower is better
    cv = (std_interval / mean_interval) if mean_interval > 0 else 1.0

    # Missing sample detection: gap > 2x expected
    missing_gaps = [iv for iv in positive_intervals if iv > 2 * expected_interval_seconds]
    if missing_gaps:
        issues.append(f"missing_sample_gaps: {len(missing_gaps)}")

    # Drift score: 100 = perfect, decreases with CV and missing gaps
    drift_penalty = min(cv * 40, 60)  # max -60 for CV
    gap_penalty = min(len(missing_gaps) * 5, 30)  # max -30 for gaps
    order_penalty = min(out_of_order * 3, 10)
    drift_score = max(0.0, 100.0 - drift_penalty - gap_penalty - order_penalty)

    return {
        "drift_score": round(drift_score, 2),
        "mean_interval_seconds": round(mean_interval, 2),
        "std_interval_seconds": round(std_interval, 2),
        "coefficient_of_variation": round(cv, 4),
        "missing_gaps": len(missing_gaps),
        "out_of_order_count": out_of_order,
        "issues": issues,
    }


# ─────────────────────────────────────────────
# MODULE 2: CROSS-SENSOR LOGIC VALIDATION
# ─────────────────────────────────────────────

# Rule schema: list of (condition_fn, message)
CROSS_SENSOR_RULES = [
    {
        "id": "high_temp_fan_off",
        "description": "High temperature sensor with cooling fan OFF",
        "check": lambda row: (
            row.get("temperature", 0) > 80
            and str(row.get("fan_status", "ON")).upper() in ("OFF", "0", "FALSE")
        ),
        "severity": "critical",
    },
    {
        "id": "pressure_flow_mismatch",
        "description": "High pressure with zero flow rate — valve may be closed",
        "check": lambda row: (
            row.get("pressure", 0) > 150
            and row.get("flow_rate", 1) == 0
        ),
        "severity": "warning",
    },
    {
        "id": "humidity_temp_impossible",
        "description": "Humidity > 100% is physically impossible",
        "check": lambda row: row.get("humidity", 0) > 100,
        "severity": "critical",
    },
    {
        "id": "voltage_zero_current",
        "description": "Voltage present but zero current while device is 'active'",
        "check": lambda row: (
            row.get("voltage", 0) > 5
            and row.get("current", 1) == 0
            and str(row.get("device_status", "OFF")).upper() in ("ON", "1", "TRUE", "ACTIVE")
        ),
        "severity": "warning",
    },
    {
        "id": "negative_energy",
        "description": "Negative power/energy reading",
        "check": lambda row: row.get("power", 0) < 0 or row.get("energy", 0) < 0,
        "severity": "error",
    },
]


def validate_cross_sensor(records: list[dict]) -> dict:
    """Apply logical consistency rules across sensor fields per record."""
    flags = []
    rule_counts = {rule["id"]: 0 for rule in CROSS_SENSOR_RULES}

    for idx, record in enumerate(records):
        for rule in CROSS_SENSOR_RULES:
            try:
                if rule["check"](record):
                    rule_counts[rule["id"]] += 1
                    flags.append({
                        "record_index": idx,
                        "rule_id": rule["id"],
                        "severity": rule["severity"],
                        "description": rule["description"],
                        "snapshot": {k: record[k] for k in record if k in (
                            "temperature", "fan_status", "pressure", "flow_rate",
                            "humidity", "voltage", "current", "device_status",
                            "power", "energy"
                        )},
                    })
            except Exception:
                pass  # field absent — rule doesn't apply

    return {
        "total_flags": len(flags),
        "flags_by_rule": rule_counts,
        "flags": flags[:50],  # cap output for large datasets
    }


# ─────────────────────────────────────────────
# MODULE 3: STATISTICAL NOISE & OUTLIER DETECTION
# ─────────────────────────────────────────────

def detect_outliers_zscore(values: list[float], threshold: float = 3.0) -> dict:
    """Z-score based outlier detection. |z| > threshold → outlier."""
    if len(values) < 3:
        return {"outlier_indices": [], "outlier_count": 0}

    clean = [v for v in values if v is not None and not math.isnan(v)]
    if len(clean) < 3:
        return {"outlier_indices": [], "outlier_count": 0}

    mean = statistics.mean(clean)
    std = statistics.pstdev(clean)
    if std == 0:
        return {"outlier_indices": [], "outlier_count": 0, "note": "zero_variance"}

    outlier_indices = [
        i for i, v in enumerate(values)
        if v is not None and not math.isnan(v) and abs((v - mean) / std) > threshold
    ]

    return {
        "mean": round(mean, 4),
        "std": round(std, 4),
        "outlier_indices": outlier_indices,
        "outlier_count": len(outlier_indices),
        "outlier_pct": round(len(outlier_indices) / len(values) * 100, 2),
    }


def compute_field_stats(values: list[float]) -> dict:
    clean = [v for v in values if v is not None and not math.isnan(float(v))]
    if not clean:
        return {"error": "no_valid_values"}
    return {
        "count": len(clean),
        "null_count": len(values) - len(clean),
        "null_pct": round((len(values) - len(clean)) / len(values) * 100, 2),
        "min": round(min(clean), 4),
        "max": round(max(clean), 4),
        "mean": round(statistics.mean(clean), 4),
        "median": round(statistics.median(clean), 4),
        "std": round(statistics.pstdev(clean), 4) if len(clean) > 1 else 0.0,
    }


# ─────────────────────────────────────────────
# MODULE 4: HADOOP SCHEMA INTEGRITY VALIDATOR
# ─────────────────────────────────────────────

HDFS_MAPREDUCE_SCHEMA = {
    "required_fields": ["sensor_id", "timestamp", "value"],
    "numeric_fields": ["value", "temperature", "humidity", "pressure",
                       "voltage", "current", "power", "flow_rate"],
    "string_fields": ["sensor_id", "location", "unit", "fan_status", "device_status"],
    "timestamp_fields": ["timestamp"],
    "max_record_size_bytes": 4096,
    "min_records": 1,
}


def validate_hdfs_schema(records: list[dict], schema: dict = None) -> dict:
    """Validate that the dataset conforms to the HDFS MapReduce job schema."""
    schema = schema or HDFS_MAPREDUCE_SCHEMA
    issues = []
    warnings = []

    if len(records) < schema["min_records"]:
        issues.append(f"insufficient_records: {len(records)} < {schema['min_records']}")

    missing_required = []
    for field in schema["required_fields"]:
        present_in = sum(1 for r in records if field in r and r[field] is not None)
        coverage = present_in / len(records) if records else 0
        if coverage < 0.95:
            missing_required.append({"field": field, "coverage_pct": round(coverage * 100, 1)})

    if missing_required:
        issues.append(f"required_field_coverage_below_95pct: {[m['field'] for m in missing_required]}")

    # Type coercibility checks for numeric fields
    type_violations = []
    for field in schema["numeric_fields"]:
        for i, record in enumerate(records[:100]):  # sample first 100
            val = record.get(field)
            if val is not None:
                try:
                    float(val)
                except (ValueError, TypeError):
                    type_violations.append({"record": i, "field": field, "value": str(val)[:50]})

    if type_violations:
        warnings.append(f"non_numeric_values_in_numeric_fields: {len(type_violations)} violations")

    # Record size check
    oversized = [
        i for i, r in enumerate(records)
        if len(json.dumps(r).encode("utf-8")) > schema["max_record_size_bytes"]
    ]
    if oversized:
        warnings.append(f"oversized_records: {len(oversized)} records exceed {schema['max_record_size_bytes']} bytes")

    schema_score = 100.0
    schema_score -= len(issues) * 25
    schema_score -= len(warnings) * 10
    schema_score = max(0.0, schema_score)

    return {
        "schema_valid": len(issues) == 0,
        "schema_score": round(schema_score, 2),
        "issues": issues,
        "warnings": warnings,
        "type_violations": type_violations[:10],
        "missing_required_fields": missing_required,
    }


# ─────────────────────────────────────────────
# ORCHESTRATOR: Full Validation Pipeline
# ─────────────────────────────────────────────

def run_validation_pipeline(records: list[dict], sensor_id: str = "unknown",
                             expected_interval_seconds: float = 60.0) -> dict:
    """
    Full FluxAudit validation pipeline.
    Returns a comprehensive result dict suitable for API response or HDFS tagging.
    """
    issues = []

    # 1. Temporal Drift
    timestamps = [r.get("timestamp") for r in records if r.get("timestamp")]
    temporal = compute_temporal_drift(timestamps, expected_interval_seconds)
    issues.extend(temporal.get("issues", []))

    # 2. Cross-Sensor Logic
    cross = validate_cross_sensor(records)

    # 3. Statistical Analysis per numeric field
    numeric_fields = ["value", "temperature", "humidity", "pressure",
                      "voltage", "current", "power", "flow_rate"]
    field_stats = {}
    total_outliers = 0
    for field in numeric_fields:
        values = []
        for r in records:
            v = r.get(field)
            if v is not None:
                try:
                    values.append(float(v))
                except (ValueError, TypeError):
                    values.append(float("nan"))
        if values:
            stats = compute_field_stats(values)
            outlier_info = detect_outliers_zscore(values)
            total_outliers += outlier_info.get("outlier_count", 0)
            field_stats[field] = {**stats, "outliers": outlier_info}

    # 4. HDFS Schema Validation
    schema_result = validate_hdfs_schema(records)

    # 5. Composite Health Score
    drift_weight = 0.30
    cross_weight = 0.25
    outlier_weight = 0.20
    schema_weight = 0.25

    drift_score = temporal.get("drift_score", 100)
    cross_penalty = min(cross["total_flags"] * 2, 100)
    cross_score = max(0.0, 100 - cross_penalty)
    outlier_penalty = min(total_outliers * 1.5, 100)
    outlier_score = max(0.0, 100 - outlier_penalty)
    schema_score = schema_result["schema_score"]

    health_score = (
        drift_score * drift_weight
        + cross_score * cross_weight
        + outlier_score * outlier_weight
        + schema_score * schema_weight
    )

    return {
        "sensor_id": sensor_id,
        "record_count": len(records),
        "health_score": round(health_score, 2),
        "temporal_drift": temporal,
        "cross_sensor_validation": cross,
        "field_statistics": field_stats,
        "hdfs_schema": schema_result,
        "total_outliers": total_outliers,
        "issues": issues,
        "component_scores": {
            "temporal_drift": round(drift_score, 2),
            "cross_sensor_logic": round(cross_score, 2),
            "data_quality": round(outlier_score, 2),
            "schema_integrity": round(schema_score, 2),
        },
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────
# CLI / DEMO
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import random

    random.seed(42)
    base_time = 1700000000.0

    sample_records = []
    for i in range(200):
        gap = 60 + random.gauss(0, 5) + (300 if i == 50 else 0)  # inject drift at i=50
        base_time += gap
        record = {
            "sensor_id": "SENSOR_ALPHA_01",
            "timestamp": datetime.fromtimestamp(base_time, tz=timezone.utc).isoformat(),
            "value": round(20 + random.gauss(0, 2) + (50 if i == 120 else 0), 3),
            "temperature": round(25 + random.gauss(0, 3) + (85 if i == 80 else 0), 2),
            "fan_status": "OFF" if i == 80 else "ON",
            "humidity": round(45 + random.gauss(0, 5), 2),
            "pressure": round(100 + random.gauss(0, 2), 2),
            "voltage": round(220 + random.gauss(0, 1), 2),
            "current": round(5 + random.gauss(0, 0.3), 3),
        }
        sample_records.append(record)

    result = run_validation_pipeline(sample_records, sensor_id="SENSOR_ALPHA_01")
    print(json.dumps(result, indent=2, default=str))
