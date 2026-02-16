from langgraph.graph import StateGraph, END
from .state import AgentState

from .nodes.ingest_file import ingest_file
from .nodes.detect import detect_incident
from .nodes.rca_llm import rca_with_llm
from .nodes.notify_stdout import notify_stdout
from .nodes.dedup import dedupe_incident


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("ingest", ingest_file)
    g.add_node("detect", detect_incident)
    g.add_node("rca", rca_with_llm)
    g.add_node("dedupe", dedupe_incident)
    g.add_node("notify", notify_stdout)

    g.set_entry_point("ingest")

    g.add_edge("ingest", "detect")

    # If no incident -> notify; if incident -> rca
    def route_after_detect(state: AgentState):
        return "rca" if state.get("is_incident") else "notify"

    g.add_conditional_edges(
        "detect",
        route_after_detect,
        {"rca": "rca", "notify": "notify"},
    )

    # Always run dedupe after RCA (so RCA outputs exist), then notify
    g.add_edge("rca", "dedupe")
    g.add_edge("dedupe", "notify")
    g.add_edge("notify", END)

    return g.compile()
