import hashlib
from ..state import AgentState

def _make_fingerprint(state: AgentState) -> str:

    severity= state.get("severity", "NONE")
    services= ",".join(state.get("services", []))
    events =",".join(state.get("top_events", []))
    key= f"{severity}|{services}|{events}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def dedupe_incident(state: AgentState) -> AgentState:
    print("DEBUG in dedupe immediate_actions:", state.get("immediate_actions"))

    if not state.get("is_incident"):
        return {
            **state,
            "should_notify": False,
        }

    fingerprint = f"{state.get('severity')}-{state.get('top_events')}"
    last = state.get("last_incident_fingerprint")

    if fingerprint == last:
        return {
            **state,
            "incident_fingerprint": fingerprint,
            "should_notify": False,
        }

    return {
        **state,
        "incident_fingerprint": fingerprint,
        "last_incident_fingerprint": fingerprint,
        "should_notify": True,
    }