from ..state import AgentState

def notify_stdout(state: AgentState) -> AgentState:
    if not state.get("is_incident"):
        print("No Incident Detected")
        if state.get("note"):
            print(f"Note: {state['note']}")
        return state
    
    print("\n !! INCIDENT DETECTED")
    if state.get("is_incident") and not state.get("should_notify", True):
        print("\nℹ️ Incident detected but deduped (no new notification).")

    print(f"Severity: {state.get('severity')}")
    print(f"Error Count: {state.get('error_count')}")
    
    services = state.get("services") or []
    events = state.get("top_events") or []

    print(f"Affected Services: {', '.join(services) if services else 'None'}")
    print(f"Top Events: {', '.join(events) if events else 'None'}")

    print("\n--- Summary ---")
    print(state.get("summary", ""))

    print("\n--- Root Causes ---")
    for cause in state.get("likely_root_causes", []):
        print(f"- {cause}")

    print("\n--- ACTIONS ---")
    actions = state.get("immediate_actions", [])
    # If no actions were produced by the RCA step, show sensible defaults
    if not actions:
        print("(none)")
    else:
        for action in actions:
            print(f"- {action}")
    
    print("\n--- QUESTIONS ---")
    for q in state.get("questions_for_human", []):
        print(f"- {q}")


    return state