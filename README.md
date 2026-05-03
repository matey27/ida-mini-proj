🚀 Objective
In industrial settings, sensor data is often "dirty"—plagued by transmission gaps, electrical interference, or hardware malfunctions. The core objective of FluxAudit is to provide a robust Data Governance layer that prevents "data rot" by validating telemetry against physical-world logic before ingestion.

✨ Key Features
1. Spatio-Temporal Drift ScoringUnlike standard validators, FluxAudit treats time as a first-class citizen. It analyzes the inter-arrival time of packets to detect missing samples or transmission delays, assigning a "Drift Score" based on consistency.
2. 2. Cross-Sensor Logic ValidationThe system performs "physical reality" checks by comparing multiple sensors. For example, it flags instances where high temperatures are reported while a cooling fan is registered as OFF.
   3. 3. Hadoop HDFS GatewayHealth-Gated Ingestion: Data is only pushed to the HDFS production path if it achieves a Health Score $\ge 60$.Automated Quarantining: Low-quality datasets are automatically routed to /fluxaudit/quarantine/ for inspection.Big Data Optimized: Converts validated streams into NDJSON (Newline Delimited JSON) for efficient line-by-line processing in MapReduce or Spark.
      4. 4. Hybrid Ingestion EngineFeatures a robust parser capable of handling .csv, .json, and .txt telemetry files with dynamic schema filtering to prevent visualization crashes.

🛠️ Tech StackFrontend: Streamlit (Industrial Mission-Control UI)Analysis: Pandas, NumPy, PlotlyStorage: Hadoop HDFS (Pseudo-Distributed Architecture)Language: Python 3.13+📂 Project StructurePlaintext├── app.py               
# Streamlit Dashboard & Navigation
├── validation_engine.py   # Core Logic (Drift & Logic Checks)
├── hdfs_integration.py    # Hadoop HDFS Connector Logic
├── main.py               # Backend API Service
└── README.md              # Project Documentation
🛠️ Installation & Setup
Clone the repository:Bashgit clone https://github.com/matey27/ida-mini-proj.git
Setup virtual environment:Bashpython -m venv venv
.\venv\Scripts\activate
Install dependencies:Bashpip install -r requirements.txt
Run the application:Bashstreamlit run app.py
