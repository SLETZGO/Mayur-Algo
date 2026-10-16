"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Row = Record<string, string | number | boolean | null>;
type Snapshot = {
  execution_mode: string;
  live_trading_enabled: boolean;
  manual_live_armed: boolean;
  database_healthy: boolean;
  database_error: string | null;
  signals: Row[];
  orders: Row[];
  executions: Row[];
  positions: Row[];
  audit_events: Row[];
  shadow_runs: Row[];
  shadow_events: Row[];
  settings: {
    webhook_secret_configured: boolean;
    webhook_max_payload_bytes: number;
    risk_limits: Record<string, string | number | null>;
  };
};
type FyersConnection = { connected: boolean; mode: string; message: string };

const sections = [
  { id: "overview", label: "Overview", icon: "◫" },
  { id: "signals", label: "Signals", icon: "⌁" },
  { id: "orders", label: "Orders & fills", icon: "▤" },
  { id: "history", label: "History & backtest", icon: "◷" },
  { id: "shadow", label: "Shadow runs", icon: "◎" },
  { id: "health", label: "Health & audit", icon: "⌘" },
  { id: "settings", label: "Risk & settings", icon: "⚙" },
] as const;
type Section = (typeof sections)[number]["id"];

function formatLabel(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function DataTable({ rows, empty, limit }: { rows: Row[]; empty: string; limit?: number }) {
  const visible = limit ? rows.slice(0, limit) : rows;
  const columns = useMemo(() => visible.length ? Object.keys(visible[0]) : [], [visible]);
  if (!visible.length) return <div className="empty-state"><span className="empty-icon">⌁</span><p>{empty}</p></div>;
  return <div className="table-scroll"><table><thead><tr>{columns.map((column) => <th key={column}>{formatLabel(column)}</th>)}</tr></thead>
    <tbody>{visible.map((row, index) => <tr key={String(row.signal_id ?? row.client_order_id ?? row.execution_id ?? row.run_id ?? `${index}`)}>
      {columns.map((column) => <td key={column}>{row[column] == null || row[column] === "" ? <span className="muted">—</span> :
        column === "status" || column === "state" || column === "queue_status" || column === "outcome" ?
          <span className={`pill ${String(row[column]).toLowerCase().includes("fail") ? "pill-red" : "pill-green"}`}>{String(row[column])}</span> : String(row[column])}</td>)}
    </tr>)}</tbody></table></div>;
}

function Panel({ title, subtitle, children, action }: { title: string; subtitle?: string; children: React.ReactNode; action?: React.ReactNode }) {
  return <section className="panel"><div className="panel-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>{children}</section>;
}

export default function Dashboard() {
  const [section, setSection] = useState<Section>("overview");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [checkingFyers, setCheckingFyers] = useState(false);
  const [fyersConnection, setFyersConnection] = useState<FyersConnection | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const base = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
      const response = await fetch(`${base}/dashboard/snapshot`, { cache: "no-store" });
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      setSnapshot(await response.json() as Snapshot);
      setUpdatedAt(new Date());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not reach the Python API.");
    } finally {
      setLoading(false);
    }
  }, []);

  const checkFyersConnection = useCallback(async () => {
    setCheckingFyers(true);
    const base = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
    try {
      const response = await fetch(`${base}/fyers/connect`, { method: "POST", cache: "no-store" });
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      setFyersConnection(await response.json() as FyersConnection);
    } catch (cause) {
      setFyersConnection({
        connected: false,
        mode: "UNAVAILABLE",
        message: cause instanceof Error ? cause.message : "Could not reach the Python API.",
      });
    } finally {
      setCheckingFyers(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const current = sections.find((item) => item.id === section)!;
  const title = current.label;
  const timeText = updatedAt ? updatedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—";

  return <main className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">M<span>.</span></div><div><strong>mayur algo</strong><small>OPERATIONS CONSOLE</small></div></div>
      <div className="environment"><span className="environment-dot" /> {snapshot?.database_healthy ? "SYSTEM ONLINE" : snapshot ? "DB UNAVAILABLE" : "CONNECTING"} <span className="environment-mode">{snapshot?.execution_mode ?? "—"}</span></div>
      <div className="nav-label">WORKSPACE</div>
      <nav aria-label="Dashboard sections">{sections.map((item) => <button key={item.id} className={`nav-item ${section === item.id ? "active" : ""}`} onClick={() => setSection(item.id)}>
        <span className="nav-icon">{item.icon}</span><span>{item.label}</span>{section === item.id && <span className="nav-active-mark" />}
      </button>)}</nav>
      <div className="sidebar-footer"><span className="avatar">MA</span><div><strong>Local instance</strong><small>Read-only access</small></div><span className="footer-menu">···</span></div>
    </aside>

    <div className="main-area">
      <header className="topbar"><div className="breadcrumb"><span>Workspace</span><span className="crumb-sep">/</span><strong>{title}</strong></div>
        <div className="topbar-right"><span className="last-refresh"><i /> {loading ? "Updating" : `Updated ${timeText}`}</span><button className="refresh-button" onClick={() => void refresh()} disabled={loading}><span className={loading ? "spin" : ""}>↻</span> Refresh</button><span className="top-avatar">M</span></div>
      </header>
      <div className="content">
        <div className="page-heading"><div><div className="eyebrow">MAYUR ALGO <span>·</span> OPERATIONS</div><h1>{title}</h1><p>Monitor persisted system activity and safety status.</p></div><div className="read-only-badge"><span>◉</span> READ-ONLY MODE</div></div>
        {error && <div className="error-banner"><strong>API connection unavailable</strong><span>{error}. Start FastAPI at the configured API URL and refresh.</span></div>}
        {!snapshot && !error && <div className="loading-panel">Loading the latest persisted snapshot…</div>}
        {snapshot && <>
          <div className="status-strip"><div className="status-left"><span className={`status-dot ${snapshot.database_healthy ? "" : "offline"}`} /><strong>{snapshot.database_healthy ? "All systems operational" : "Database unavailable"}</strong><span className="status-divider" /><span>Execution mode <b>{snapshot.execution_mode}</b></span></div><span className="status-right">LIVE EXECUTION DISABLED</span></div>
          {section === "overview" && <>
            <div className="metric-grid">
              <Metric label="Execution mode" value={snapshot.execution_mode} note="Configured application mode" tone="blue" icon="◉" />
              <Metric label="Live trading" value={snapshot.live_trading_enabled ? "Enabled" : "Disabled"} note="Fail-closed safety gate" tone="green" icon="⌁" />
              <Metric label="Manual live arm" value={snapshot.manual_live_armed ? "Armed" : "Off"} note="Operator activation" tone="amber" icon="⚿" />
              <Metric label="Database" value={snapshot.database_healthy ? "Connected" : "Unavailable"} note="Read-only connection" tone="violet" icon="▤" />
            </div>
            <div className="two-column"><Panel title="Current positions" subtitle="Persisted broker instrument positions"><DataTable rows={snapshot.positions} empty="No persisted positions." /></Panel>
              <Panel title="Recent alerts" subtitle="Latest TradingView signal intake" action={<button className="text-button" onClick={() => setSection("signals")}>View all →</button>}><DataTable rows={snapshot.signals} limit={5} empty="No persisted signal alerts." /></Panel></div>
            <Panel title="System activity" subtitle="Latest persisted audit events"><DataTable rows={snapshot.audit_events} limit={5} empty="No audit events recorded yet." /></Panel>
          </>}
          {section === "signals" && <Panel title="TradingView signal intake" subtitle="Entry and stop values are in the Pine chart symbol’s price units (for an index, index points)."><DataTable rows={snapshot.signals} empty="No persisted signal alerts." /></Panel>}
          {section === "orders" && <><Panel title="Orders" subtitle="Order and broker acknowledgement state. Prices are per listed broker instrument."><DataTable rows={snapshot.orders} empty="No persisted orders." /></Panel><Panel title="Executions / fills" subtitle="Broker acknowledgements are not fills; only persisted executions appear here."><DataTable rows={snapshot.executions} empty="No persisted executions." /></Panel></>}
          {section === "history" && <><Panel title="Persisted event history" subtitle="Audit trail from the application database."><DataTable rows={snapshot.audit_events} empty="No persisted audit events." /></Panel><Panel title="Backtest reports" subtitle="Replay status"><div className="notice"><span>ⓘ</span><p>No backtest report is persisted yet. CSV replay currently emits in-memory signal events only; no CSV or options dataset is configured, so no P&amp;L result is available.</p></div></Panel></>}
          {section === "shadow" && <><Panel title="Shadow observation runs" subtitle="Observation windows do not place orders."><DataTable rows={snapshot.shadow_runs} empty="No shadow run has been started." /></Panel><Panel title="Observation tape" subtitle="Fill estimates are observations, not actual executions."><DataTable rows={snapshot.shadow_events} empty="No shadow observations have been recorded." /></Panel></>}
          {section === "health" && <><div className="metric-grid two-metrics"><Metric label="Dashboard" value="Running" note="Read-only web client" tone="green" icon="◉" /><Metric label="Database" value={snapshot.database_healthy ? "Connected" : "Unavailable"} note={snapshot.database_error ? `Read failed (${snapshot.database_error})` : "Connection healthy"} tone="violet" icon="▤" /></div><Panel title="Recent audit events" subtitle="Persisted audit history; this is not host or web-server logging."><DataTable rows={snapshot.audit_events} empty="No audit events." /></Panel></>}
          {section === "settings" && <><Panel title="FYERS API connection" subtitle="Explicit profile check using local credentials. Read-only access only." action={<button className="refresh-button" onClick={() => void checkFyersConnection()} disabled={checkingFyers}>{checkingFyers ? "Checking…" : "Check connection"}</button>}>
            <div className="connection-row"><span className={`connection-indicator ${fyersConnection?.connected ? "connected" : ""}`} /><div><strong>{fyersConnection?.mode ?? "NOT CHECKED"}</strong><p>{fyersConnection?.message ?? "Credentials are read from the Python process environment and never returned to the browser."}</p></div></div>
            <p className="settings-footnote">This check reads the FYERS profile only. It does not place, modify, or cancel orders. Live trading remains disabled.</p>
          </Panel><Panel title="Risk limits" subtitle="Current in-memory configuration"><div className="settings-grid">{Object.entries(snapshot.settings.risk_limits).map(([key, value]) => <div className="setting-row" key={key}><span>{formatLabel(key)}</span><strong>{value ?? "Not configured"}</strong></div>)}</div></Panel><Panel title="Execution and intake settings" subtitle="View-only safety configuration"><div className="settings-grid"><Setting name="Execution mode" value={snapshot.execution_mode} /><Setting name="Live trading enabled" value={snapshot.live_trading_enabled ? "Yes" : "No"} /><Setting name="Manual live arm" value={snapshot.manual_live_armed ? "Armed" : "Off"} /><Setting name="Webhook secret" value={snapshot.settings.webhook_secret_configured ? "Configured · value hidden" : "Not configured"} /><Setting name="Webhook max payload" value={`${snapshot.settings.webhook_max_payload_bytes} bytes`} /><Setting name="Database URL" value="Configured · value hidden" /></div><p className="settings-footnote">Secrets and database connection strings are never displayed. Settings cannot be changed from this dashboard.</p></Panel></>}
          <footer className="page-footer"><span>Mayur Algo Operations <b>·</b> Read-only dashboard</span><span>Snapshot source: Python API <b>·</b> Last refresh {timeText}</span></footer>
        </>}
      </div>
    </div>
  </main>;
}

function Metric({ label, value, note, tone, icon }: { label: string; value: string; note: string; tone: string; icon: string }) {
  return <section className="metric-card"><div className="metric-top"><span>{label}</span><span className={`metric-icon ${tone}`}>{icon}</span></div><strong>{value}</strong><small><i className={`mini-dot ${tone}`} />{note}</small></section>;
}

function Setting({ name, value }: { name: string; value: string }) {
  return <div className="setting-row"><span>{name}</span><strong>{value}</strong></div>;
}
