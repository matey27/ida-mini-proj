# FluxAudit — IoT Dataset Validation System

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        BROWSER CLIENT                           │
│  React + Tailwind + Recharts                                    │
│  ┌──────────────┐  ┌────────────────────┐  ┌────────────────┐  │
│  │  Upload Zone │  │ Validation Insight │  │  HDFS Push UI  │  │
│  │  (drag/drop) │  │  (gauges, charts)  │  │  (health gate) │  │
│  └──────┬───────┘  └────────┬───────────┘  └──────┬─────────┘  │
└─────────┼──────────────────┼─────────────────────┼────────────┘
          │  POST /validate  │  GET /validations    │  POST /push
          ▼                  ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI BACKEND  (main.py)                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │               VALIDATION PIPELINE                        │   │
│  │  ┌─────────────────┐  ┌──────────────────────────────┐   │   │
│  │  │ Temporal Drift  │  │  Cross-Sensor Logic Engine   │   │   │
│  │  │  - Gap analysis │  │  - Rule-based flagging        │   │   │
│  │  │  - CV scoring   │  │  - 5 built-in rules           │   │   │
│  │  └────────┬────────┘  └──────────────┬───────────────┘  │   │
│  │           │                          │                   │   │
│  │  ┌────────┴──────────────────────────┴──────────────┐    │   │
│  │  │            Composite Health Score                │    │   │
│  │  │  0.30×Drift + 0.25×CrossSensor + 0.20×Quality   │    │   │
│  │  │                    + 0.25×Schema                 │    │   │
│  │  └───────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                            │                                    │
│                            ▼ (score ≥ 60)                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           HDFS INTEGRATION LAYER (hdfs_integration.py)   │   │
│  │  ┌──────────────┐  ┌─────────────────┐                   │   │
│  │  │ Schema Check │  │  Data Writer    │                   │   │
│  │  │  (MapReduce  │  │  (NDJSON)       │                   │   │
│  │  │  compat.)    │  │                 │                   │   │
│  │  └──────┬───────┘  └───────┬─────────┘                   │   │
│  └─────────┼──────────────────┼──────────────────────────────┘  │
└────────────┼──────────────────┼──────────────────────────────────┘
             │                  │
             ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     HADOOP HDFS CLUSTER                         │
│                                                                 │
│  /fluxaudit/                                                    │
│    validated/{sensor_id}/{timestamp}/                           │
│      input/data_{ts}.ndjson       ← raw records (MapReduce in) │
│      input/_SUCCESS               ← job ready marker           │
│      _metadata/validation_report.json                          │
│      _metadata/schema.json        ← field types + stats        │
│    quarantine/{sensor_id}/...     ← score < 60 datasets        │
│    schemas/                       ← schema snapshots           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Backend

```bash
pip install fastapi uvicorn python-multipart hdfs

# Start API server
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
npx create-react-app fluxaudit-ui
cd fluxaudit-ui
npm install recharts lucide-react
# Copy FluxAudit.jsx → src/App.jsx
npm start
```

### Run validation engine standalone

```bash
python validation_engine.py
```

### Test HDFS integration (mock mode, no cluster needed)

```bash
python hdfs_integration.py
```

---

## File Reference

| File | Purpose |
|---|---|
| `validation_engine.py` | Core scoring logic — temporal drift, cross-sensor rules, outlier detection, HDFS schema validation |
| `main.py` | FastAPI server — file upload, REST API, routing |
| `hdfs_integration.py` | HDFS client wrapper — data transfer, schema snapshotting, quarantine routing |
| `FluxAudit.jsx` | React SPA — drag & drop upload, validation dashboard, health gauges, telemetry charts |

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/validate` | Upload CSV/JSON dataset, returns full validation report |
| `GET` | `/validations` | List all validation jobs |
| `GET` | `/validations/{job_id}` | Get single validation report |
| `POST` | `/validations/{job_id}/push-hdfs` | Push validated data to HDFS (requires score ≥ 60) |
| `GET` | `/health` | Service health check |

---

## Health Score Formula

```
Health = 0.30 × TemporalDrift
       + 0.25 × CrossSensorLogic
       + 0.20 × DataQuality
       + 0.25 × SchemaIntegrity
```

- **Temporal Drift**: Penalizes coefficient-of-variation in sample intervals and missing-gap count
- **Cross-Sensor Logic**: Penalizes rule violations (2 pts each, max -100)
- **Data Quality**: Penalizes z-score outliers (1.5 pts each, max -100)
- **Schema Integrity**: Penalizes missing required fields, type violations, oversized records

---

## Cross-Sensor Rules

| Rule ID | Condition | Severity |
|---|---|---|
| `high_temp_fan_off` | temperature > 80°C AND fan_status = OFF | critical |
| `pressure_flow_mismatch` | pressure > 150 AND flow_rate = 0 | warning |
| `humidity_temp_impossible` | humidity > 100% | critical |
| `voltage_zero_current` | voltage > 5V AND current = 0 AND device = active | warning |
| `negative_energy` | power < 0 OR energy < 0 | error |

Custom rules can be added to the `CROSS_SENSOR_RULES` list in `validation_engine.py`.

---

## HDFS Directory Layout

```
/fluxaudit/validated/{sensor_id}/{YYYYMMDDTHHMMSSZ}/
  input/
    data_{ts}.ndjson    ← one JSON record per line (MapReduce input format)
    _SUCCESS            ← signals job readiness to downstream MR jobs
  _metadata/
    validation_report.json
    schema.json         ← field names, types, statistics, mapreduce_ready flag
```

Datasets with health score < 60 are routed to `/fluxaudit/quarantine/` instead.
