import json
from pathlib import Path
from typing import Dict, Any, List
from ..state import AgentState
import re

SYSLOG_RE = re.compile(
    r"^(?P<ts>\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+(?P<proc>[^\[:]+)(?:\[\d+\])?:\s*(?P<msg>.*)$"
)

def infer_level(msg: str) -> str:
    m = msg.lower()
    if any(x in m for x in ["panic", "fatal", "critical", "segfault", "kernel bug"]):
        return "CRITICAL"
    if any(x in m for x in ["error", "failed", "failure", "cannot", "unable", "denied"]):
        return "ERROR"
    if any(x in m for x in ["warn", "warning", "timeout", "retry"]):
        return "WARN"
    return "INFO"

def infer_event(msg: str) -> str:
    m = msg.lower()
    if "authentication failure" in m or "failed password" in m:
        return "authentication_failed"
    if "out of memory" in m or "oom-killer" in m:
        return "oom_killer"
    if "segfault" in m:
        return "segfault"
    if "i/o error" in m or "disk" in m and "error" in m:
        return "disk_io_error"
    if "connection refused" in m:
        return "connection_refused"
    if "timeout" in m:
        return "timeout"
    return "generic_issue"

def ingest_file(state: AgentState) -> AgentState:
    # 1) default log path
    path_str = (state.get("log_path") or "data/sample.log.jsonl").strip()
    n = int(state.get("window_lines") or 200)

    # 2) resolve path robustly (works no matter where you run from)
    p = Path(path_str)

    if not p.is_absolute():
        # this file: .../src/incident_agent/nodes/ingest_file.py
        # parents[2] -> .../src
        # src.parent -> project root
        project_root = Path(__file__).resolve().parents[3]  # .../incident-agent
        p = (project_root / p).resolve()

    if not p.exists():
        raise FileNotFoundError(
            f"Log file not found: {p}\n"
            f"Hint: set state['log_path'] to an absolute path or run from project root."
        )

    raw_lines: List[str] = []
    logs: List[Dict[str, Any]] = []

    # 3) memory-friendly: don't read whole file if huge (but OK for now)
    with p.open("r", encoding="utf-8") as f:
        lines = f.read().splitlines()[-n:]

    for line in lines:
        line = line.strip()
        if not line:
            continue
        raw_lines.append(line)
        try:
            logs.append(json.loads(line))
        except Exception:
            logs.append({
                "level": "INFO",
                "message": line,
                "service": "unknown",
                "event": "raw_line"
            })

    state["recent_logs"] = logs
    state["last_n_raw"] = raw_lines
    state["note"] = f"Read last {len(raw_lines)} lines from {str(p)}"
    return state