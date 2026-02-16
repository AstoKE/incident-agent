import json
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
    path = state.get("log_path") or ""
    n = int(state.get("window_lines") or 200)

    raw_lines: List[str] = []
    logs:List[Dict[str, any]] = []

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f.readlines()[-n:]:
            line = line.strip()
            if not line:
                continue
            raw_lines.append(line)
            try:
                logs.append(json.loads(line))
            except Exception:
                m = SYSLOG_RE.match(line)
                if m:
                    msg = m.group("msg")
                    proc = m.group("proc")
                    logs.append({
                        "ts": m.group("ts"),
                        "service": proc,
                        "level": infer_level(msg),
                        "event": infer_event(msg),
                        "message": msg,
                    })
                else:
                    logs.append({
                        "level": infer_level(line),
                        "message": line,
                        "service": "unknown",
                        "event": infer_event(line),
                    })

    state["recent_logs"] = logs
    state["last_n_raw"] = raw_lines
    state["note"] = f"Read last {len(raw_lines)} lines from {path}"
    return state