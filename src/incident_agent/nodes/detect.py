from collections import Counter
from ..state import AgentState
from ..config import ERROR_THRESHOLD

def detect_incident(state: AgentState) -> AgentState:
    logs = state.get("recent_logs", [])
    errors = [x for x in logs if str(x.get("level", "")).upper() in ("ERROR", "CRITICAL")]
    state["error_count"] =len(errors)

    services = [str(x.get("service", "unknown")) for x in errors]
    state["services"] = sorted(set(services))

    events= [str(x.get("event", "unknown")) for x in errors]
    top = [e for e, _ in Counter(events).most_common(5)]
    state["top_events"] = top

    is_incident = state["error_count"] >= ERROR_THRESHOLD
    state["is_incident"] = is_incident

    if not is_incident:
        state["severity"] = "NONE"
    elif state["error_count"] >= ERROR_THRESHOLD *3:
        state["severity"] = "HIGH"
    else: 
        state["severity"] = "MEDIUM"

    return state