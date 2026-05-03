import { useState, useCallback, useRef, useEffect } from "react";
import {
  RadialBarChart, RadialBar, ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  BarChart, Bar, Cell, PieChart, Pie,
} from "recharts";
import {
  Upload, Activity, AlertTriangle, CheckCircle2, XCircle,
  Database, Zap, Thermometer, Clock, ChevronRight,
  Shield, BarChart2, GitBranch, Server, Layers,
  ArrowUpRight, RefreshCw, Info, FileText
} from "lucide-react";

// ─── Theme tokens ────────────────────────────────────────────────────────────
const C = {
  bg:      "#0a0c0f",
  surface: "#111318",
  border:  "#1e2330",
  border2: "#2a3044",
  text:    "#e8eaf0",
  muted:   "#5a6080",
  cyan:    "#00d4ff",
  green:   "#00e5a0",
  amber:   "#ffb800",
  red:     "#ff4d6a",
  purple:  "#a78bfa",
  blue:    "#3b82f6",
};

// ─── Mock data generator (mirrors validation_engine.py output) ───────────────
function generateMockValidation(filename) {
  const score = 55 + Math.random() * 42;
  const drift = 40 + Math.random() * 55;
  const cross = 85 + Math.random() * 13;
  const qual  = 70 + Math.random() * 28;
  const schem = 80 + Math.random() * 18;

  const ts = [];
  let t = Date.now() / 1000 - 200 * 65;
  for (let i = 0; i < 200; i++) {
    t += 60 + (Math.random() - 0.5) * 8 + (i === 50 ? 240 : 0);
    ts.push(new Date(t * 1000).toISOString());
  }

  const temps = Array.from({ length: 200 }, (_, i) =>
    +(25 + (Math.random() - 0.5) * 6 + (i === 80 ? 62 : 0)).toFixed(2)
  );
  const humidity = Array.from({ length: 200 }, () =>
    +(45 + (Math.random() - 0.5) * 10).toFixed(2)
  );

  return {
    job_id: Math.random().toString(36).slice(2, 10),
    sensor_id: filename.replace(/\.(csv|json)$/i, ""),
    filename,
    record_count: 200,
    health_score: +score.toFixed(1),
    validated_at: new Date().toISOString(),
    component_scores: {
      temporal_drift:    +drift.toFixed(1),
      cross_sensor_logic:+cross.toFixed(1),
      data_quality:      +qual.toFixed(1),
      schema_integrity:  +schem.toFixed(1),
    },
    temporal_drift: {
      drift_score: +drift.toFixed(1),
      mean_interval_seconds: 61.2,
      std_interval_seconds: 18.4,
      coefficient_of_variation: 0.301,
      missing_gaps: 2,
      out_of_order_count: 0,
      issues: drift < 70 ? ["missing_sample_gaps: 2"] : [],
    },
    cross_sensor_validation: {
      total_flags: cross < 92 ? 3 : 0,
      flags_by_rule: {
        high_temp_fan_off: cross < 92 ? 1 : 0,
        pressure_flow_mismatch: cross < 92 ? 1 : 0,
        negative_energy: cross < 92 ? 1 : 0,
      },
    },
    hdfs_schema: {
      schema_valid: schem > 75,
      schema_score: +schem.toFixed(1),
      issues: schem < 75 ? ["required_field_coverage_below_95pct: [value]"] : [],
      warnings: [],
    },
    total_outliers: Math.floor(qual < 85 ? 8 : 2),
    issues: [],
    _timestamps: ts,
    _temps: temps,
    _humidity: humidity,
  };
}

function genTimeSeriesChart(result) {
  const ts = result._timestamps || [];
  const temps = result._temps || [];
  return ts.slice(0, 60).map((t, i) => ({
    time: new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    temperature: temps[i] || 0,
    expected: 25,
  }));
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function GaugeChart({ score, label, color, size = 120 }) {
  const data = [{ value: score, fill: color }, { value: 100 - score, fill: C.surface }];
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
      <div style={{ position: "relative", width: size, height: size / 1.6 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%" cy="100%"
              startAngle={180} endAngle={0}
              innerRadius="55%" outerRadius="80%"
              dataKey="value" stroke="none"
            >
              {data.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div style={{
          position: "absolute", bottom: 4, left: 0, right: 0,
          textAlign: "center",
        }}>
          <span style={{ fontSize: 22, fontWeight: 700, color, fontFamily: "'Space Mono', monospace" }}>
            {score}
          </span>
        </div>
      </div>
      <span style={{ fontSize: 11, color: C.muted, letterSpacing: "0.08em", textTransform: "uppercase" }}>
        {label}
      </span>
    </div>
  );
}

function Badge({ text, severity }) {
  const colors = {
    critical: { bg: "#ff4d6a22", border: "#ff4d6a55", text: C.red },
    warning:  { bg: "#ffb80022", border: "#ffb80055", text: C.amber },
    info:     { bg: "#00d4ff18", border: "#00d4ff44", text: C.cyan },
    ok:       { bg: "#00e5a018", border: "#00e5a044", text: C.green },
  };
  const s = colors[severity] || colors.info;
  return (
    <span style={{
      fontSize: 11, padding: "2px 8px", borderRadius: 4,
      background: s.bg, border: `1px solid ${s.border}`, color: s.text,
      fontFamily: "'Space Mono', monospace", letterSpacing: "0.04em",
    }}>
      {text}
    </span>
  );
}

function ScoreBar({ label, value, color, icon: Icon }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Icon size={13} color={color} />
          <span style={{ fontSize: 12, color: C.muted, letterSpacing: "0.06em", textTransform: "uppercase" }}>
            {label}
          </span>
        </div>
        <span style={{ fontSize: 13, color, fontFamily: "'Space Mono', monospace", fontWeight: 700 }}>
          {value.toFixed(1)}
        </span>
      </div>
      <div style={{ height: 4, borderRadius: 2, background: C.border }}>
        <div style={{
          height: "100%", borderRadius: 2, width: `${value}%`,
          background: `linear-gradient(90deg, ${color}88, ${color})`,
          transition: "width 1.2s cubic-bezier(0.4,0,0.2,1)",
        }} />
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, color, icon: Icon }) {
  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`,
      borderRadius: 10, padding: "14px 16px",
      borderTop: `2px solid ${color}44`,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ fontSize: 11, color: C.muted, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>
            {label}
          </div>
          <div style={{ fontSize: 28, fontWeight: 700, color, fontFamily: "'Space Mono', monospace" }}>
            {value}
          </div>
          {sub && <div style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>{sub}</div>}
        </div>
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: `${color}18`, display: "flex", alignItems: "center", justifyContent: "center"
        }}>
          <Icon size={16} color={color} />
        </div>
      </div>
    </div>
  );
}

// ─── Upload Zone ─────────────────────────────────────────────────────────────
function UploadZone({ onFile, loading }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef();

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) onFile(file);
  }, [onFile]);

  const handleInput = (e) => {
    const file = e.target.files[0];
    if (file) onFile(file);
  };

  return (
    <div
      onClick={() => !loading && inputRef.current?.click()}
      onDrop={handleDrop}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      style={{
        border: `2px dashed ${dragging ? C.cyan : C.border2}`,
        borderRadius: 16, padding: "52px 32px",
        textAlign: "center", cursor: loading ? "default" : "pointer",
        background: dragging ? `${C.cyan}08` : C.surface,
        transition: "all 0.2s ease",
      }}
    >
      <input ref={inputRef} type="file" accept=".csv,.json" onChange={handleInput} style={{ display: "none" }} />
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
          <div style={{ width: 48, height: 48, borderRadius: "50%", border: `3px solid ${C.border2}`, borderTop: `3px solid ${C.cyan}`, animation: "spin 1s linear infinite" }} />
          <span style={{ color: C.muted, fontSize: 14 }}>Analyzing telemetry stream…</span>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 64, height: 64, borderRadius: 16, background: `${C.cyan}12`,
            display: "flex", alignItems: "center", justifyContent: "center",
            border: `1px solid ${C.cyan}30`,
          }}>
            <Upload size={28} color={C.cyan} />
          </div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600, color: C.text, marginBottom: 6 }}>
              Drop IoT Dataset Here
            </div>
            <div style={{ fontSize: 13, color: C.muted }}>
              Accepts .CSV or .JSON — up to 10 MB
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            {["CSV", "JSON", "NDJSON"].map(f => (
              <span key={f} style={{
                fontSize: 11, padding: "2px 8px", borderRadius: 4,
                background: C.border, color: C.muted, letterSpacing: "0.06em"
              }}>{f}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Validation Dashboard ─────────────────────────────────────────────────────
function ValidationDashboard({ result, onPushHDFS }) {
  const scores = result.component_scores;
  const chartData = genTimeSeriesChart(result);
  const crossFlags = result.cross_sensor_validation?.flags_by_rule || {};

  const healthColor =
    result.health_score >= 80 ? C.green :
    result.health_score >= 60 ? C.amber : C.red;

  const barData = Object.entries(crossFlags).map(([rule, count]) => ({
    rule: rule.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
    count,
  }));

  const schemaItems = [
    { key: "Record Count", val: result.record_count.toLocaleString() },
    { key: "Total Outliers", val: result.total_outliers },
    { key: "Schema Valid", val: result.hdfs_schema?.schema_valid ? "Yes" : "No" },
    { key: "Schema Score", val: `${result.hdfs_schema?.schema_score?.toFixed(1)}` },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* Header strip */}
      <div style={{
        background: C.surface, border: `1px solid ${C.border}`,
        borderRadius: 14, padding: "18px 24px",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div>
          <div style={{ fontSize: 11, color: C.muted, letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 4 }}>
            Sensor Stream
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: C.text, fontFamily: "'Space Mono', monospace" }}>
            {result.sensor_id}
          </div>
          <div style={{ fontSize: 12, color: C.muted, marginTop: 2 }}>
            {new Date(result.validated_at).toLocaleString()} · {result.record_count} records
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <Badge
            text={result.health_score >= 80 ? "HEALTHY" : result.health_score >= 60 ? "DEGRADED" : "CRITICAL"}
            severity={result.health_score >= 80 ? "ok" : result.health_score >= 60 ? "warning" : "critical"}
          />
          <button
            onClick={onPushHDFS}
            disabled={result.health_score < 60}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "8px 14px", borderRadius: 8,
              background: result.health_score >= 60 ? `${C.cyan}20` : C.border,
              border: `1px solid ${result.health_score >= 60 ? C.cyan + "50" : C.border}`,
              color: result.health_score >= 60 ? C.cyan : C.muted,
              fontSize: 12, cursor: result.health_score >= 60 ? "pointer" : "not-allowed",
              fontWeight: 600, letterSpacing: "0.04em",
            }}
          >
            <Server size={13} />
            Push to HDFS
          </button>
        </div>
      </div>

      {/* Health Score + Component gauges */}
      <div style={{
        background: C.surface, border: `1px solid ${C.border}`,
        borderRadius: 14, padding: "24px",
      }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr", gap: 0, alignItems: "center" }}>
          {/* Big health gauge */}
          <div style={{
            display: "flex", flexDirection: "column", alignItems: "center",
            borderRight: `1px solid ${C.border}`, paddingRight: 20, gap: 8,
          }}>
            <div style={{ fontSize: 11, color: C.muted, letterSpacing: "0.1em", textTransform: "uppercase" }}>
              Health Score
            </div>
            <div style={{
              fontSize: 56, fontWeight: 800, color: healthColor,
              fontFamily: "'Space Mono', monospace", lineHeight: 1,
            }}>
              {result.health_score.toFixed(0)}
            </div>
            <div style={{ fontSize: 11, color: healthColor }}>/ 100</div>
          </div>

          {/* Component gauges */}
          {[
            { label: "Temporal Drift",    key: "temporal_drift",    color: C.cyan },
            { label: "Cross-Sensor",      key: "cross_sensor_logic", color: C.purple },
            { label: "Data Quality",      key: "data_quality",      color: C.green },
            { label: "Schema Integrity",  key: "schema_integrity",  color: C.amber },
          ].map(({ label, key, color }) => (
            <div key={key} style={{ display: "flex", justifyContent: "center", padding: "0 8px" }}>
              <GaugeChart score={scores[key]} label={label} color={color} size={100} />
            </div>
          ))}
        </div>
      </div>

      {/* Stat cards row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        <StatCard label="Records" value={result.record_count.toLocaleString()} sub="total samples" color={C.cyan} icon={Layers} />
        <StatCard label="Outliers" value={result.total_outliers} sub="σ > 3 z-score" color={result.total_outliers > 5 ? C.amber : C.green} icon={Activity} />
        <StatCard label="Cross-Sensor Flags" value={result.cross_sensor_validation?.total_flags || 0} sub="logical violations" color={result.cross_sensor_validation?.total_flags > 0 ? C.red : C.green} icon={GitBranch} />
        <StatCard label="Drift Gaps" value={result.temporal_drift?.missing_gaps || 0} sub="missed samples" color={result.temporal_drift?.missing_gaps > 0 ? C.amber : C.green} icon={Clock} />
      </div>

      {/* Charts row */}
      <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 16 }}>

        {/* Telemetry time series */}
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "20px 24px" }}>
          <div style={{ fontSize: 12, color: C.muted, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 16 }}>
            Temperature Telemetry Stream
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData} margin={{ left: -10, right: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: C.muted }} tickLine={false} axisLine={false} interval={9} />
              <YAxis tick={{ fontSize: 10, fill: C.muted }} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ background: C.bg, border: `1px solid ${C.border2}`, borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: C.muted }}
              />
              <Line type="monotone" dataKey="temperature" stroke={C.cyan} strokeWidth={1.5} dot={false} />
              <Line type="monotone" dataKey="expected" stroke={C.border2} strokeWidth={1} strokeDasharray="4 4" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Cross-sensor rule violations */}
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "20px 24px" }}>
          <div style={{ fontSize: 12, color: C.muted, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 16 }}>
            Cross-Sensor Violations
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={barData} layout="vertical" margin={{ left: 0, right: 16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.border} horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: C.muted }} tickLine={false} axisLine={false} allowDecimals={false} />
              <YAxis type="category" dataKey="rule" width={130} tick={{ fontSize: 10, fill: C.muted }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: C.bg, border: `1px solid ${C.border2}`, borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {barData.map((_, i) => (
                  <Cell key={i} fill={_.count > 0 ? C.red : C.green} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Score breakdown bars + schema info */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>

        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "20px 24px" }}>
          <div style={{ fontSize: 12, color: C.muted, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 20 }}>
            Validation Breakdown
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <ScoreBar label="Temporal Drift"   value={scores.temporal_drift}    color={C.cyan}   icon={Clock} />
            <ScoreBar label="Cross-Sensor Logic" value={scores.cross_sensor_logic} color={C.purple} icon={GitBranch} />
            <ScoreBar label="Data Quality"     value={scores.data_quality}      color={C.green}  icon={Activity} />
            <ScoreBar label="Schema Integrity" value={scores.schema_integrity}  color={C.amber}  icon={Shield} />
          </div>
        </div>

        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "20px 24px" }}>
          <div style={{ fontSize: 12, color: C.muted, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 16 }}>
            HDFS Schema Audit
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {schemaItems.map(({ key, val }) => (
              <div key={key} style={{
                display: "flex", justifyContent: "space-between",
                padding: "8px 12px", borderRadius: 8, background: C.bg,
              }}>
                <span style={{ fontSize: 12, color: C.muted }}>{key}</span>
                <span style={{ fontSize: 12, color: C.text, fontFamily: "'Space Mono', monospace" }}>{val}</span>
              </div>
            ))}
            {(result.hdfs_schema?.issues || []).map((issue, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "flex-start", gap: 8,
                padding: "8px 12px", borderRadius: 8, background: `${C.red}10`,
                border: `1px solid ${C.red}30`,
              }}>
                <AlertTriangle size={13} color={C.red} style={{ marginTop: 1, flexShrink: 0 }} />
                <span style={{ fontSize: 11, color: C.red, fontFamily: "'Space Mono', monospace" }}>{issue}</span>
              </div>
            ))}
            {result.hdfs_schema?.schema_valid && (
              <div style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "8px 12px", borderRadius: 8,
                background: `${C.green}10`, border: `1px solid ${C.green}30`,
              }}>
                <CheckCircle2 size={13} color={C.green} />
                <span style={{ fontSize: 12, color: C.green }}>MapReduce schema compatible</span>
              </div>
            )}
          </div>
        </div>
      </div>

    </div>
  );
}

// ─── Job History ──────────────────────────────────────────────────────────────
function JobHistory({ jobs, onSelect }) {
  if (!jobs.length) return null;
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "20px 24px" }}>
      <div style={{ fontSize: 12, color: C.muted, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 16 }}>
        Validation History
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {jobs.map(job => (
          <div key={job.job_id}
            onClick={() => onSelect(job)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "10px 14px", borderRadius: 8, background: C.bg,
              cursor: "pointer", border: `1px solid ${C.border}`,
              transition: "border-color 0.15s",
            }}
            onMouseEnter={e => e.currentTarget.style.borderColor = C.border2}
            onMouseLeave={e => e.currentTarget.style.borderColor = C.border}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <FileText size={14} color={C.muted} />
              <div>
                <div style={{ fontSize: 13, color: C.text }}>{job.filename}</div>
                <div style={{ fontSize: 11, color: C.muted }}>{new Date(job.validated_at).toLocaleString()}</div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{
                fontSize: 16, fontWeight: 700,
                fontFamily: "'Space Mono', monospace",
                color: job.health_score >= 80 ? C.green : job.health_score >= 60 ? C.amber : C.red,
              }}>
                {job.health_score}
              </span>
              <ChevronRight size={14} color={C.muted} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function FluxAudit() {
  const [loading, setLoading] = useState(false);
  const [current, setCurrent] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [hdfsMsg, setHdfsMsg] = useState(null);

  const handleFile = useCallback((file) => {
    setLoading(true);
    setHdfsMsg(null);
    setTimeout(() => {
      const result = generateMockValidation(file.name);
      setCurrent(result);
      setJobs(prev => [result, ...prev].slice(0, 10));
      setLoading(false);
    }, 1800);
  }, []);

  const handlePushHDFS = () => {
    if (!current) return;
    setHdfsMsg(null);
    setTimeout(() => {
      const path = `/fluxaudit/validated/${current.sensor_id}/${Date.now()}`;
      setHdfsMsg({ ok: true, path });
    }, 900);
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Sora:wght@400;600;700;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: ${C.bg}; color: ${C.text}; font-family: 'Sora', sans-serif; min-height: 100vh; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes fadeUp { from { opacity:0; transform: translateY(12px); } to { opacity:1; transform: translateY(0); } }
        .fade-up { animation: fadeUp 0.4s ease forwards; }
        ::-webkit-scrollbar { width: 4px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: ${C.border2}; border-radius: 2px; }
      `}</style>

      {/* Nav */}
      <header style={{
        borderBottom: `1px solid ${C.border}`, padding: "0 40px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        height: 56, position: "sticky", top: 0, zIndex: 100,
        background: `${C.bg}e8`, backdropFilter: "blur(12px)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 6, background: `${C.cyan}20`,
            border: `1px solid ${C.cyan}40`, display: "flex", alignItems: "center", justifyContent: "center"
          }}>
            <Zap size={14} color={C.cyan} />
          </div>
          <span style={{ fontSize: 15, fontWeight: 700, color: C.text, letterSpacing: "-0.02em" }}>
            Flux<span style={{ color: C.cyan }}>Audit</span>
          </span>
          <span style={{ fontSize: 11, color: C.muted, marginLeft: 6, padding: "2px 6px", background: C.border, borderRadius: 4, letterSpacing: "0.06em" }}>
            v1.0
          </span>
        </div>
        <div style={{ display: "flex", gap: 20 }}>
          {["Dashboard", "Schemas", "HDFS Cluster", "Settings"].map(item => (
            <span key={item} style={{ fontSize: 13, color: item === "Dashboard" ? C.text : C.muted, cursor: "pointer" }}>
              {item}
            </span>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: C.green }} />
          <span style={{ fontSize: 12, color: C.muted }}>HDFS Connected</span>
        </div>
      </header>

      <main style={{ maxWidth: 1280, margin: "0 auto", padding: "36px 40px", display: "flex", flexDirection: "column", gap: 24 }}>

        {/* Page title */}
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 800, color: C.text, letterSpacing: "-0.03em" }}>
            IoT Dataset <span style={{ color: C.cyan }}>Validation</span>
          </h1>
          <p style={{ fontSize: 13, color: C.muted, marginTop: 4 }}>
            Temporal drift scoring · Cross-sensor logic validation · Hadoop schema integrity
          </p>
        </div>

        <UploadZone onFile={handleFile} loading={loading} />

        {hdfsMsg && (
          <div className="fade-up" style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "12px 16px", borderRadius: 10,
            background: `${C.green}10`, border: `1px solid ${C.green}40`,
          }}>
            <CheckCircle2 size={16} color={C.green} />
            <span style={{ fontSize: 13, color: C.green }}>
              Pushed to HDFS: <span style={{ fontFamily: "'Space Mono', monospace", fontSize: 12 }}>{hdfsMsg.path}</span>
            </span>
          </div>
        )}

        {current && (
          <div className="fade-up">
            <ValidationDashboard result={current} onPushHDFS={handlePushHDFS} />
          </div>
        )}

        <JobHistory jobs={jobs} onSelect={setCurrent} />

      </main>
    </>
  );
}
