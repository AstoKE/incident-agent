from langgraph.graph import StateGraph, END
from .state import AgentState

from .nodes.ingest_file import ingest_file
from .nodes.detect import detect_incident
from .nodes.rca_llm import rca_with_llm
from .nodes.notify_stdout import notify_stdout
from .nodes.dedup import dedupe_incident


def build_graph():
    g = StateGraph(AgentState)

    # nodes
    g.add_node("ingest", ingest_file)
    g.add_node("detect",detect_incident)
    g.add_node("rca",rca_with_llm)
    g.add_node("notify", notify_stdout)
    g.add_node("dedupe", dedupe_incident)

    g.set_entry_point("ingest")

    g.add_edge("ingest", "detect")
    g.add_edge("detect", "dedupe")
    
    def route_after_dedupe(state: AgentState):
        if not state.get("is_incident"):
            return "notify"
        return "rca" if state.get("should_notify") else "notify"
    

    g.add_conditional_edges(
        "dedupe",
        route_after_dedupe,
        {"rca": "rca", "notify": "notify"}
    )

    g.add_edge("rca","notify")
    g.add_edge("notify", END)

    return g.compile()