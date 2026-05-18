"""
Web dashboard for the Incident Agent.

Run alongside the agent daemon:
  Terminal 1: PYTHONPATH=src python -m incident_agent.app
  Terminal 2: PYTHONPATH=src python -m incident_agent.api

Then open: http://localhost:8080
"""
from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from .store import load_incidents

app = FastAPI(title="Incident Agent Dashboard", docs_url=None, redoc_url=None)

# ---------------------------------------------------------------------------
# Dashboard HTML (single-file, no external dependencies)
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Incident Agent</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      min-height: 100vh;
    }

    header {
      position: sticky;
      top: 0;
      z-index: 10;
      background: #1e293b;
      border-bottom: 1px solid #334155;
      padding: 14px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    header h1 { font-size: 1.1rem; font-weight: 700; letter-spacing: -0.01em; }
    header h1 span { color: #f87171; }

    .controls { display: flex; align-items: center; gap: 12px; }
    .status-dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      background: #22c55e;
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.4; }
    }
    .status-text { font-size: 0.75rem; color: #94a3b8; }
    .btn {
      background: #334155;
      border: none;
      color: #e2e8f0;
      padding: 6px 14px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.8rem;
      transition: background 0.15s;
    }
    .btn:hover { background: #475569; }

    main { max-width: 860px; margin: 0 auto; padding: 28px 16px; }

    .empty {
      text-align: center;
      padding: 80px 0;
      color: #475569;
    }
    .empty .icon { font-size: 2.5rem; margin-bottom: 12px; }
    .empty p { font-size: 0.9rem; }

    .card {
      background: #1e293b;
      border-radius: 10px;
      margin-bottom: 14px;
      border-left: 4px solid #334155;
      overflow: hidden;
      transition: box-shadow 0.2s;
    }
    .card:hover { box-shadow: 0 4px 24px rgba(0,0,0,0.4); }
    .card.HIGH  { border-left-color: #ef4444; }
    .card.MEDIUM { border-left-color: #f59e0b; }

    .card-header {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      padding: 16px;
    }

    .badge {
      flex-shrink: 0;
      font-size: 0.65rem;
      font-weight: 800;
      padding: 3px 9px;
      border-radius: 4px;
      letter-spacing: 0.07em;
      margin-top: 2px;
    }
    .badge.HIGH   { background: #7f1d1d; color: #fca5a5; }
    .badge.MEDIUM { background: #78350f; color: #fde68a; }

    .card-title { flex: 1; }
    .card-title .events {
      font-size: 0.9rem;
      font-weight: 600;
      color: #f1f5f9;
      word-break: break-word;
    }
    .card-title .meta {
      font-size: 0.72rem;
      color: #64748b;
      margin-top: 4px;
    }

    .card-body { padding: 0 16px 16px; }

    .tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
    .tag {
      font-size: 0.68rem;
      background: #0f172a;
      color: #94a3b8;
      padding: 2px 9px;
      border-radius: 20px;
      border: 1px solid #334155;
    }

    .summary {
      font-size: 0.83rem;
      color: #cbd5e1;
      line-height: 1.6;
      margin-bottom: 14px;
    }

    details { margin-bottom: 6px; }
    details[open] { margin-bottom: 10px; }

    summary {
      list-style: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 0.72rem;
      font-weight: 700;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      padding: 5px 0;
      user-select: none;
      transition: color 0.15s;
    }
    summary::-webkit-details-marker { display: none; }
    summary::before {
      content: "▶";
      font-size: 0.6rem;
      transition: transform 0.2s;
    }
    details[open] summary::before { transform: rotate(90deg); }
    summary:hover { color: #94a3b8; }

    ul { padding-left: 8px; margin-top: 8px; }
    ul li {
      font-size: 0.8rem;
      color: #cbd5e1;
      padding: 5px 0 5px 12px;
      border-left: 2px solid #334155;
      margin-bottom: 5px;
      line-height: 1.4;
    }
    ul li::marker { display: none; }
  </style>
</head>
<body>
  <header>
    <h1>⚡ Incident <span>Agent</span></h1>
    <div class="controls">
      <div class="status-dot"></div>
      <span class="status-text" id="status">Connecting…</span>
      <button class="btn" onclick="load()">↻ Refresh</button>
    </div>
  </header>

  <main id="root">
    <div class="empty"><div class="icon">⏳</div><p>Loading…</p></div>
  </main>

  <script>
    const SEV = { HIGH: "🔴", MEDIUM: "🟡" };

    function fmtDate(ts) {
      if (!ts) return "—";
      try {
        return new Date(ts).toLocaleString(undefined, {
          month: "short", day: "numeric",
          hour: "2-digit", minute: "2-digit", second: "2-digit"
        });
      } catch { return ts; }
    }

    function listBlock(title, items) {
      if (!items || !items.length) return "";
      const lis = items.map(i => `<li>${i}</li>`).join("");
      return `<details open><summary>${title}</summary><ul>${lis}</ul></details>`;
    }

    function card(inc) {
      const sev = inc.severity || "MEDIUM";
      const events = (inc.top_events || []).join(", ") || "unknown event";
      const services = inc.services || [];
      const tags = services.map(s => `<span class="tag">${s}</span>`).join("");
      return `
        <div class="card ${sev}">
          <div class="card-header">
            <span class="badge ${sev}">${sev}</span>
            <div class="card-title">
              <div class="events">${events}</div>
              <div class="meta">${fmtDate(inc.timestamp)} &nbsp;·&nbsp; ${inc.error_count ?? 0} errors</div>
            </div>
          </div>
          <div class="card-body">
            ${tags ? `<div class="tags">${tags}</div>` : ""}
            <p class="summary">${inc.summary || ""}</p>
            ${listBlock("Root Causes", inc.root_causes)}
            ${listBlock("Immediate Actions", inc.actions)}
            ${listBlock("Questions for Team", inc.questions)}
          </div>
        </div>`;
    }

    async function load() {
      const statusEl = document.getElementById("status");
      try {
        const res = await fetch("/api/incidents");
        if (!res.ok) throw new Error(res.statusText);
        const data = await res.json();
        const root = document.getElementById("root");
        statusEl.textContent = "Updated " + new Date().toLocaleTimeString();
        if (!data.length) {
          root.innerHTML = `
            <div class="empty">
              <div class="icon">🟢</div>
              <p>No incidents recorded yet.</p>
              <p style="margin-top:8px;font-size:0.75rem;color:#334155;">The agent is running and watching your logs.</p>
            </div>`;
          return;
        }
        root.innerHTML = data.map(card).join("");
      } catch (e) {
        statusEl.textContent = "Error — retrying in 30 s";
      }
    }

    load();
    setInterval(load, 30000);
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return _DASHBOARD_HTML


@app.get("/api/incidents")
def get_incidents():
    return load_incidents()


@app.get("/api/incidents/latest")
def get_latest():
    incidents = load_incidents(limit=1)
    return incidents[0] if incidents else {}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "incident_agent.api:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="info",
    )
