"""
FluxAudit HDFS Integration Layer
Manages validated IoT data transfer to Hadoop HDFS cluster.

Uses the `hdfs` Python client (pip install hdfs).
For pydoop, swap InsecureClient for pydoop.hdfs.open() — see comments.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

# ─── hdfs client (WebHDFS REST API via `hdfs` package) ────────────────────────
# pip install hdfs
try:
    from hdfs import InsecureClient
    HDFS_AVAILABLE = True
except ImportError:
    HDFS_AVAILABLE = False
    print("[FluxAudit] hdfs package not installed — running in MOCK mode")


# ─── Configuration ─────────────────────────────────────────────────────────────
HDFS_CONFIG = {
    "namenode_url": os.getenv("HDFS_NAMENODE", "http://localhost:9870"),
    "user": os.getenv("HDFS_USER", "hdfs"),
    "base_path": "/fluxaudit",
    "validated_path": "/fluxaudit/validated",
    "quarantine_path": "/fluxaudit/quarantine",
    "schema_path": "/fluxaudit/schemas",
    "replication": 3,
}

# MapReduce job directory structure expected by downstream jobs
HDFS_DIR_STRUCTURE = {
    "input": "/fluxaudit/validated/{sensor_id}/input",
    "output": "/fluxaudit/validated/{sensor_id}/output",
    "metadata": "/fluxaudit/validated/{sensor_id}/_metadata",
}


# ─── Client Factory ─────────────────────────────────────────────────────────────

class HDFSClient:
    """
    Thin wrapper around InsecureClient with mock fallback for local dev.
    For Kerberos-secured clusters, swap InsecureClient with:
        from hdfs.ext.kerberos import KerberosClient
        client = KerberosClient(url, mutual_auth='REQUIRED')
    For pydoop:
        import pydoop.hdfs as hdfs
        hdfs.open(path, 'wt').write(data)
    """

    def __init__(self, config: dict = None):
        self.config = config or HDFS_CONFIG
        self.mock = not HDFS_AVAILABLE
        self._client = None

        if not self.mock:
            self._client = InsecureClient(
                url=self.config["namenode_url"],
                user=self.config["user"],
            )

    def makedirs(self, path: str) -> bool:
        if self.mock:
            print(f"[MOCK HDFS] makedirs: {path}")
            return True
        try:
            self._client.makedirs(path)
            return True
        except Exception as e:
            print(f"[HDFS] makedirs failed {path}: {e}")
            return False

    def write(self, path: str, data: str, overwrite: bool = True) -> bool:
        if self.mock:
            print(f"[MOCK HDFS] write: {path} ({len(data)} bytes)")
            return True
        try:
            with self._client.write(path, encoding="utf-8", overwrite=overwrite) as writer:
                writer.write(data)
            return True
        except Exception as e:
            print(f"[HDFS] write failed {path}: {e}")
            return False

    def read(self, path: str) -> Optional[str]:
        if self.mock:
            print(f"[MOCK HDFS] read: {path}")
            return None
        try:
            with self._client.read(path, encoding="utf-8") as reader:
                return reader.read()
        except Exception as e:
            print(f"[HDFS] read failed {path}: {e}")
            return None

    def list_dir(self, path: str) -> list:
        if self.mock:
            print(f"[MOCK HDFS] list: {path}")
            return []
        try:
            return self._client.list(path) or []
        except Exception:
            return []

    def set_replication(self, path: str, replication: int = 3):
        """Set HDFS replication factor for a file (WebHDFS SETSTORAGEPOLICY)."""
        if self.mock:
            print(f"[MOCK HDFS] set_replication: {path} → {replication}x")
            return
        try:
            self._client.set_replication(path, replication)
        except Exception as e:
            print(f"[HDFS] set_replication failed: {e}")


# ─── Core: Move Validated Data to HDFS ─────────────────────────────────────────

def move_to_hdfs(validation_result: dict, client: HDFSClient = None) -> dict:
    """
    Moves a validated IoT dataset to the HDFS cluster.

    Directory layout written:
    /fluxaudit/validated/{sensor_id}/input/   ← raw records (NDJSON)
    /fluxaudit/validated/{sensor_id}/_metadata/ ← validation report + schema

    Low-health datasets (score < 60) are quarantined instead.

    Returns a dict with the HDFS path and status.
    """
    client = client or HDFSClient()
    sensor_id = validation_result.get("sensor_id", "unknown").replace("/", "_")
    health_score = validation_result.get("health_score", 0)
    timestamp_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Route: validated vs quarantine
    if health_score >= 60:
        base = f"{HDFS_CONFIG['validated_path']}/{sensor_id}/{timestamp_tag}"
    else:
        base = f"{HDFS_CONFIG['quarantine_path']}/{sensor_id}/{timestamp_tag}"

    input_path = f"{base}/input"
    metadata_path = f"{base}/_metadata"

    # 1. Create directory structure
    for path in [input_path, metadata_path]:
        client.makedirs(path)

    # 2. Write raw records as NDJSON (Hadoop-friendly: one JSON per line)
    records = validation_result.get("_raw_records", [])  # attach before calling
    if records:
        ndjson = "\n".join(json.dumps(r) for r in records)
        data_file = f"{input_path}/data_{timestamp_tag}.ndjson"
        client.write(data_file, ndjson)
        client.set_replication(data_file, HDFS_CONFIG["replication"])

    # 3. Write validation report
    report_file = f"{metadata_path}/validation_report.json"
    report_data = {k: v for k, v in validation_result.items() if k != "_raw_records"}
    client.write(report_file, json.dumps(report_data, indent=2, default=str))

    # 4. Write _SUCCESS marker (expected by MapReduce jobs)
    client.write(f"{input_path}/_SUCCESS", "")

    # 5. Write schema snapshot for downstream job compatibility
    schema_snapshot = _build_schema_snapshot(validation_result)
    client.write(f"{metadata_path}/schema.json", json.dumps(schema_snapshot, indent=2))

    status = "validated" if health_score >= 60 else "quarantined"
    print(f"[HDFS] {status.upper()} → {base}")

    return {
        "path": base,
        "status": status,
        "sensor_id": sensor_id,
        "health_score": health_score,
        "timestamp": timestamp_tag,
        "mock_mode": client.mock,
    }


def _build_schema_snapshot(validation_result: dict) -> dict:
    """Build a schema descriptor for downstream MapReduce jobs."""
    field_stats = validation_result.get("field_statistics", {})
    return {
        "sensor_id": validation_result.get("sensor_id"),
        "record_count": validation_result.get("record_count", 0),
        "health_score": validation_result.get("health_score"),
        "fields": {
            field: {
                "type": "numeric",
                "mean": stats.get("mean"),
                "std": stats.get("std"),
                "null_pct": stats.get("null_pct"),
            }
            for field, stats in field_stats.items()
        },
        "hdfs_format": "ndjson",
        "mapreduce_ready": validation_result.get("hdfs_schema", {}).get("schema_valid", False),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── Batch Processing ──────────────────────────────────────────────────────────

def batch_push_to_hdfs(validation_results: list[dict], min_health_score: float = 60.0) -> dict:
    """
    Push multiple validation results to HDFS.
    Returns summary of pushed / quarantined / skipped counts.
    """
    client = HDFSClient()
    pushed, quarantined, skipped = [], [], []

    for result in validation_results:
        score = result.get("health_score", 0)
        try:
            hdfs_result = move_to_hdfs(result, client=client)
            if hdfs_result["status"] == "validated":
                pushed.append(hdfs_result)
            else:
                quarantined.append(hdfs_result)
        except Exception as e:
            skipped.append({"sensor_id": result.get("sensor_id"), "error": str(e)})

    return {
        "total": len(validation_results),
        "pushed": len(pushed),
        "quarantined": len(quarantined),
        "skipped": len(skipped),
        "details": {"pushed": pushed, "quarantined": quarantined, "skipped": skipped},
    }


# ─── CLI Demo ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mock_result = {
        "sensor_id": "SENSOR_DEMO_01",
        "health_score": 87.5,
        "record_count": 200,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "component_scores": {
            "temporal_drift": 91.0,
            "cross_sensor_logic": 82.0,
            "data_quality": 88.0,
            "schema_integrity": 89.0,
        },
        "hdfs_schema": {"schema_valid": True},
        "_raw_records": [
            {"sensor_id": "SENSOR_DEMO_01", "timestamp": "2024-01-01T00:00:00Z", "value": 42.1}
        ],
    }

    result = move_to_hdfs(mock_result)
    print(json.dumps(result, indent=2))
