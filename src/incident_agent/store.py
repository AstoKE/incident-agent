"""
Persistent JSONL store for detected incidents.

The agent appends one JSON line per notified incident.
The API server reads this file to power the dashboard.
"""
from __future__ import annotations

import fcntl
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_INCIDENTS_FILE = Path("data/incidents.jsonl")


def _incidents_path() -> Path:
    """Resolve path relative to project root regardless of cwd.

    store.py lives at src/incident_agent/store.py, so parents[2] = project root.
    """
    root = Path(__file__).resolve().parents[2]
    return root / "data" / "incidents.jsonl"


def save_incident(state: Dict[str, Any]) -> None:
    """Append a notified incident to the JSONL store (file-lock safe)."""
    if not state.get("should_notify"):
        return
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": state.get("severity", ""),
        "services": state.get("services", []),
        "top_events": state.get("top_events", []),
        "error_count": state.get("error_count", 0),
        "summary": state.get("summary", ""),
        "root_causes": state.get("likely_root_causes", []),
        "actions": state.get("immediate_actions", []),
        "questions": state.get("questions_for_human", []),
        "fingerprint": state.get("incident_fingerprint", ""),
    }
    path = _incidents_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(json.dumps(record) + "\n")
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as exc:
        logger.warning("Failed to persist incident: %s", exc)


def load_incidents(limit: int = 100) -> List[Dict[str, Any]]:
    """Return incidents from the JSONL store, most recent first."""
    path = _incidents_path()
    if not path.exists():
        return []
    records: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
    except Exception as exc:
        logger.warning("Failed to load incidents: %s", exc)
    return list(reversed(records[-limit:]))
