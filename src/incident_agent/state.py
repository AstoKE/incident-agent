from __future__ import annotations
from typing import TypedDict, List, Dict,Any, Optional

class AgentState(TypedDict, total=False):
    log_path: str
    window_lines: int

    recent_logs: List[Dict[str, Any]]
    error_count: int
    services: List[str]
    top_events: List[str]

    is_incident: bool
    severity: str

    summary: str
    likely_root_causes: List[str]
    immediate_actions: List[str]          
    questions_for_human: List[str]

    # dedupe fields
    incident_fingerprint: str
    last_incident_fingerprint: str
    should_notify: bool

    last_n_raw: List[str]
    note: Optional[str]
