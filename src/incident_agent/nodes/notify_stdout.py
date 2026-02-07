from ..state import AgentState

def notify_stdout(state: AgentState) -> AgentState:
    if not state.get("is_incident"):
        print("No Incident Detected")
        if state.get("note"):
            print(f"Note: {state['note']}")
        return state
    
    print("\n !! INCIDENT DETECTED")
    print(f"Severity: {state.get("severity")}")
    print(f"Error Count: {state.get("error_count")}")
    print(f"Affected Services: {state.get("services")}")
    print(f"Top Events: {state.get("top_events")}")

    print("\n--- Summary ---")
    print(state.get("summary", ""))

    print("\n--- Root Causes ---")
    for cause in state.get("likely_root_causes", []):
        print(f"- {cause}")

    print("\n--- ACTIONS ---")
    for action in state.get("immediate_action", []):
        print(f"- {action}")
    
    print("\n--- QUESTIONS ---")
    for q in state.get("questions_for_human", []):
        print(f"- {q}")

    
    return state