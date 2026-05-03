Objective: To implement a Data Governance layer for IoT telemetry, ensuring high-integrity data ingestion into Hadoop HDFS.

Unique Features:

Spatio-Temporal Drift Scoring: Detects missing telemetry samples and transmission gaps.

Cross-Sensor Logic Validation: Verifies physical-world consistency (e.g., high temperature vs. fan status).

HDFS Gateway: Automated quarantining of low-health datasets (Score < 60).

Tech Stack: Python (FastAPI/Streamlit), Hadoop HDFS, and Plotly for industrial-grade visualizations.

Final Checklist
main.py: Your backend API.

app.py: Your Streamlit dashboard.

validation_engine.py: The core logic for drift and logic checks.

hdfs_integration.py: The script managing the Hadoop storage layer.
