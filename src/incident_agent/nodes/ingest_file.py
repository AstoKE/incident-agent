import json
import re
from collections import deque
from pathlib import Path
from typing import Dict, Any, List

from ..state import AgentState

SYSLOG_RE = re.compile(
    r"^(?P<ts>\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+"
    r"(?P<proc>[^\[:]+)(?:\[\d+\])?:\s*"
    r"(?P<msg>.*)$"
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
    if "out of memory" in m or "oom-killer" in m or "oom killer" in m:
        return "oom_killer"
    if "segfault" in m:
        return "segfault"
    if ("i/o error" in m) or ("disk" in m and "error" in m):
        return "disk_io_error"
    if "connection refused" in m:
        return "connection_refused"
    if "timeout" in m or "timed out" in m:
        return "timeout"
    return "generic_issue"


def _resolve_log_path(path_str: str) -> Path:
    p = Path(path_str)
    if p.is_absolute():
        return p

    # incident-agent/
    project_root = Path(__file__).resolve().parents[3]
    return (project_root / p).resolve()


def _tail_lines(path: Path, n: int) -> List[str]:
    """Read last n lines without loading entire file into memory."""
    dq: deque[str] = deque(maxlen=n)
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            dq.append(line.rstrip("\n"))
    return list(dq)


def _parse_syslog_line(line: str) -> Dict[str, Any] | None:
    m = SYSLOG_RE.match(line)
    if not m:
        return None

    ts = m.group("ts")
    host = m.group("host")
    proc = m.group("proc")
    msg = m.group("msg")

    level = infer_level(msg)
    event = infer_event(msg)

    return {
        "ts": ts,
        "host": host,
        "service": proc,
        "level": level,
        "event": event,
        "message": msg,
    }


def ingest_file(state: AgentState) -> AgentState:
    path_str = (state.get("log_path") or "data/sample.log.jsonl").strip()
    n = int(state.get("window_lines") or 200)

    p = _resolve_log_path(path_str)

    if not p.exists():
        raise FileNotFoundError(
            f"Log file not found: {p}\n"
            f"Hint: set state['log_path'] to an absolute path or run from project root."
        )

    raw_lines: List[str] = []
    logs: List[Dict[str, Any]] = []

    lines = _tail_lines(p, n)

    for line in lines:
        line = line.strip()
        if not line:
            continue

        raw_lines.append(line)

        # 1) Prefer JSONL if parseable
        try:
            obj = json.loads(line)
            # normalize common keys if they exist, keep everything else
            logs.append({
                "ts": obj.get("ts"),
                "service": obj.get("service", "unknown"),
                "level": str(obj.get("level", "INFO")).upper(),
                "event": obj.get("event", "unknown"),
                "message": obj.get("message", ""),
                **{k: v for k, v in obj.items() if k not in {"ts", "service", "level", "event", "message"}},
            })
            continue
        except Exception:
            pass

        # 2) Try syslog parse (Linux.log etc.)
        parsed = _parse_syslog_line(line)
        if parsed is not None:
            logs.append(parsed)
            continue

        # 3) Fallback raw line
        logs.append({
            "ts": None,
            "service": "unknown",
            "level": infer_level(line),
            "event": infer_event(line),
            "message": line,
            "raw": True,
        })

    return {
        **state,
        "recent_logs": logs,
        "last_n_raw": raw_lines,
        "note": f"Read last {len(raw_lines)} lines from {str(p)}",
    }