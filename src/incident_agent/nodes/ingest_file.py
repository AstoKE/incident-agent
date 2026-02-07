import json
from typing import Dict, Any, List
from ..state import AgentSate

def ingest_file(state: AgentSate) -> AgentSate:
    path = state.get("log_path") or ""
    n = int(state.get("window_lines") or 200)

    raw_lines: List[str] = []
    logs:List[Dict[str, any]] = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f.readlines()[-n:]:
            line = line.strip()
            if not line:
                continue
            raw_lines.append(line)
            try:
                logs.append(json.loads(line))
            except Exception:
                # allow non-json lines
                logs.append({"level": "INFO", "message": line, "service": "unknown", "event": "raw_line"})

    state["recent_logs"] = logs
    state["last_n_raw"] = raw_lines
    state["note"] = f"Read last {len(raw_lines)} lines from {path}"
    return state