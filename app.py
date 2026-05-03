import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
import io
import json
from datetime import datetime
from validation_engine import run_validation_pipeline
from hdfs_integration import move_to_hdfs

# --- Page Configuration ---
st.set_page_config(
    page_title="FluxAudit | IoT Data Analytics",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom Industrial Dark Theme CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Sora:wght@400;600;700;800&display=swap');
    
    html, body, [class*="st-"] { 
        font-family: 'Sora', sans-serif; 
        background-color: #0a0c0f; 
        color: #e8eaf0; 
    }
    .stApp { background-color: #0a0c0f; }
    
    /* Stat Card styling */
    .stat-card {
        background-color: #111318;
        border: 1px solid #1e2330;
        border-radius: 10px;
        padding: 20px;
        text-align: left;
    }
    .mono-text { font-family: 'Space Mono', monospace; }
    
    /* Custom Button Styling */
    .stButton>button {
        background-color: rgba(0, 212, 255, 0.1);
        color: #00d4ff;
        border: 1px solid rgba(0, 212, 255, 0.3);
        border-radius: 8px;
        font-weight: 600;
        width: 100%;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: rgba(0, 212, 255, 0.2);
        border-color: #00d4ff;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Navigation Sidebar ---
with st.sidebar:
    st.markdown("### ⚡ Flux<span style='color:#00d4ff'>Audit</span>", unsafe_allow_html=True)
    st.divider()
    # Functional Navigation
    page = st.radio("Navigation", ["📊 Dashboard", "🗂️ HDFS Cluster", "📜 Schema Registry", "⚙️ Settings"])
    st.divider()
    st.success("Hadoop Status: Connected")
    st.info("Cluster Node: DJSCE-CL-01")

# ──────────────────────────────────────────────────────────────────────────────
# PAGE 1: DASHBOARD
# ──────────────────────────────────────────────────────────────────────────────
if page == "📊 Dashboard":
    st.markdown("## IoT Dataset <span style='color:#00d4ff'>Validation</span>", unsafe_allow_html=True)
    st.markdown("<p style='color:#5a6080'>Spatio-temporal drift scoring · Cross-sensor logic · Hadoop integrity</p>", unsafe_allow_html=True)
    
    # 1. Hybrid File Uploader
    uploaded_file = st.file_uploader("Upload Telemetry Batch", type=["csv", "json", "txt"])

    if uploaded_file:
        try:
            # Smart Parsing Logic
            content = uploaded_file.getvalue().decode("utf-8-sig")
            file_name = uploaded_file.name.lower()

            if file_name.endswith('.json') or "{" in content[:10]:
                raw_data = json.loads(content)
                df = pd.DataFrame(raw_data if isinstance(raw_data, list) else raw_data.get("records", []))
            else:
                df = pd.read_csv(io.StringIO(content))

            if df.empty:
                st.warning("Uploaded file is empty.")
                st.stop()

            # 2. Run Validation Engine
            with st.status("Analyzing IoT stream...", expanded=False) as status:
                report = run_validation_pipeline(df.to_dict(orient="records"), sensor_id=uploaded_file.name)
                time.sleep(0.5)
                status.update(label="Analysis Complete", state="complete")

            # 3. Top Metric Cards (Using Safe Getters)
            st.divider()
            m1, m2, m3, m4 = st.columns(4)
            
            m1.metric("Health Score", f"{report.get('health_score', 0)}/100")
            m2.metric("Total Records", report.get('record_count', 0))
            
            drift_gaps = report.get('temporal_drift', {}).get('missing_gaps', 0)
            m3.metric("Drift Gaps", drift_gaps)
            
            logic_flags = report.get('cross_sensor_validation', {}).get('total_flags', 0)
            m4.metric("Logic Flags", logic_flags)

            # 4. Visualization Layer
            col_chart, col_breakdown = st.columns([1.6, 1])
            
            with col_chart:
                st.markdown("#### Temporal Telemetry Stream")
                # Dynamic Schema Filter for Plotly
                numeric_df = df.select_dtypes(include=['number'])
                if not numeric_df.empty:
                    target_col = numeric_df.columns[0]
                    fig = px.line(df.head(100), y=target_col, template="plotly_dark", 
                                 color_discrete_sequence=['#00d4ff'])
                    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No numeric data available for time-series plotting.")

            with col_breakdown:
                st.markdown("#### Validation Breakdown")
                comp_scores = report.get('component_scores', {})
                if comp_scores:
                    fig_bar = px.bar(
                        x=list(comp_scores.values()), 
                        y=list(comp_scores.keys()), 
                        orientation='h', 
                        template="plotly_dark",
                        color_discrete_sequence=['#a78bfa']
                    )
                    fig_bar.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_bar, use_container_width=True)

            # 5. HDFS Integration Action
            st.divider()
            if st.button("🚀 Push Validated Data to HDFS Cluster"):
                if report.get('health_score', 0) >= 60:
                    hdfs_res = move_to_hdfs(report)
                    st.balloons()
                    st.success(f"Successfully moved to HDFS: {hdfs_res.get('path')}")
                else:
                    st.error("Action Blocked: Health score below HDFS safety threshold (60).")

        except Exception as e:
            st.error(f"Engine Error: {e}")

    else:
        st.info("Awaiting IoT telemetry batch upload...")

# ──────────────────────────────────────────────────────────────────────────────
# PAGE 2: HDFS CLUSTER (Functional Mock Explorer)
# ──────────────────────────────────────────────────────────────────────────────
elif page == "🗂️ HDFS Cluster":
    st.markdown("## Hadoop <span style='color:#00d4ff'>HDFS Explorer</span>", unsafe_allow_html=True)
    st.markdown("Current Path: `hdfs://namenode:9000/fluxaudit/validated/`")
    
    mock_files = [
        {"File Name": "sensor_99_batch_A.json", "Size": "2.4 MB", "Replication": "3", "Block Size": "128MB"},
        {"File Name": "industrial_telemetry_v2.csv", "Size": "890 KB", "Replication": "3", "Block Size": "128MB"},
        {"File Name": "drift_quarantine_log.txt", "Size": "12 KB", "Replication": "1", "Block Size": "128MB"}
    ]
    st.table(mock_files)
    if st.button("🔄 Sync with NameNode"):
        with st.spinner("Talking to Hadoop..."):
            time.sleep(1)
            st.rerun()

# ──────────────────────────────────────────────────────────────────────────────
# PAGE 3: SCHEMA REGISTRY
# ──────────────────────────────────────────────────────────────────────────────
elif page == "📜 Schema Registry":
    st.markdown("## Master <span style='color:#00d4ff'>Schema Registry</span>", unsafe_allow_html=True)
    st.warning("Datasets failing these constraints will be quarantined by the Hadoop Gateway.")
    
    schema_df = pd.DataFrame({
        "Required Field": ["timestamp", "sensor_id", "temperature", "voltage", "status"],
        "Type": ["ISO-8601", "String", "Float", "Integer", "Enum(ON/OFF)"],
        "Valid Range": ["N/A", "N/A", "-40.0 to 125.0", "0 to 480", "Boolean Logic"]
    })
    st.dataframe(schema_df, use_container_width=True)

# ──────────────────────────────────────────────────────────────────────────────
# PAGE 4: SETTINGS
# ──────────────────────────────────────────────────────────────────────────────
else:
    st.markdown("## System <span style='color:#00d4ff'>Settings</span>", unsafe_allow_html=True)
    st.slider("Minimum HDFS Push Score", 0, 100, 60)
    st.text_input("Hadoop WebHDFS Endpoint", value="http://127.0.0.1:9870/webhdfs/v1")
    st.toggle("Enable Spatio-Temporal Anomaly Detection", value=True)