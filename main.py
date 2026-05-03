"""
FluxAudit FastAPI Backend
REST API for IoT Dataset Validation System
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json
import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Optional

from validation_engine import run_validation_pipeline
from hdfs_integration import HDFSClient, move_to_hdfs
from fastapi import FastAPI, UploadFile, File, Query

app = FastAPI(
    title="FluxAudit API",
    description="IoT Dataset Validation Engine",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for demo (replace with DB in production)
validation_store: dict = {}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "FluxAudit", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/validate")
async def validate_dataset(
    file: UploadFile = File(...),  # <--- This 'File(...)' is the magic part!
    sensor_id: str = Query(None),
    expected_interval: int = Query(60)
):
    # ... rest of your code
    """
    Upload a CSV or JSON IoT dataset.
    Returns full validation report including health score, drift, cross-sensor flags.
    """
    content = await file.read()
    filename = file.filename or "unknown"
    sid = sensor_id or filename.replace(".csv", "").replace(".json", "")

    try:
        records = _parse_file(content, filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Parse error: {e}")

    if not records:
        raise HTTPException(status_code=422, detail="No valid records found in file.")

    result = run_validation_pipeline(records, sensor_id=sid, expected_interval_seconds=expected_interval)
    result["job_id"] = str(uuid.uuid4())
    result["filename"] = filename
    validation_store[result["job_id"]] = result

    return JSONResponse(result)


@app.get("/validations")
async def list_validations():
    """List all past validation jobs."""
    summary = [
        {
            "job_id": v["job_id"],
            "sensor_id": v["sensor_id"],
            "filename": v.get("filename"),
            "health_score": v["health_score"],
            "record_count": v["record_count"],
            "validated_at": v["validated_at"],
        }
        for v in validation_store.values()
    ]
    return sorted(summary, key=lambda x: x["validated_at"], reverse=True)


@app.get("/validations/{job_id}")
async def get_validation(job_id: str):
    if job_id not in validation_store:
        raise HTTPException(status_code=404, detail="Job not found")
    return validation_store[job_id]


@app.post("/validations/{job_id}/push-hdfs")
async def push_to_hdfs(job_id: str):
    """Move validated data to HDFS cluster."""
    if job_id not in validation_store:
        raise HTTPException(status_code=404, detail="Job not found")

    result = validation_store[job_id]
    if result["health_score"] < 60:
        raise HTTPException(
            status_code=409,
            detail=f"Health score {result['health_score']} below threshold (60). Fix issues before pushing to HDFS."
        )

    hdfs_result = move_to_hdfs(result)
    return {"status": "pushed", "hdfs_path": hdfs_result["path"], "job_id": job_id}


# ─────────────────────────────────────────────
# HELPER: File Parser
# ─────────────────────────────────────────────

def _parse_file(content: bytes, filename: str) -> list[dict]:
    text = content.decode("utf-8-sig")

    if filename.endswith(".json"):
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "records" in data:
            return data["records"]
        raise ValueError("JSON must be a list of records or {records: [...]}")

    # CSV fallback
    reader = csv.DictReader(io.StringIO(text))
    records = []
    for row in reader:
        # Coerce numeric strings
        coerced = {}
        for k, v in row.items():
            if v is None or v.strip() == "":
                coerced[k] = None
            else:
                try:
                    coerced[k] = float(v)
                except ValueError:
                    coerced[k] = v
        records.append(coerced)
    return records


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
