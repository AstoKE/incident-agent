import hashlib
from ..state import AgentState

def _make_fingerprint(state: AgentState) -> str:

    severity= state.get("severity", "NONE")
    services= ",".join(state.get("services", []))
    events =",".join(state.get("top_events", []))
    key= f"{severity}|{services}|{events}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def dedupe_incident(state: AgentState) -> AgentState:
    if not state.get("is_incident"):
        state["should_notify"]=False
        return state
    
    fp = _make_fingerprint(state)
    state["incident_fingerprint"] =fp

    last_fp = state.get("last_incident_fingerprint")
    if last_fp == fp:
        state["should_notify"]=False
    else:
        state["should_notify"]= True
        state["last_incident_fingerprint"] = fp

    return state