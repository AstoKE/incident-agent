from langgraph.graph import StateGraph, END
from .state import AgentState

from .nodes.ingest_file import ingest_file
from .nodes.detect import detect_incident
from .nodes.rag_retrieve import rag_retrieve
from .nodes.rca_llm import rca_with_llm
from .nodes.dedup import dedupe_incident
from .nodes.notify_stdout import notify_stdout
from .nodes.rag_store import rag_store


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("ingest", ingest_file)
    g.add_node("detect", detect_incident)
    g.add_node("rag_retrieve", rag_retrieve)
    g.add_node("rca", rca_with_llm)
    g.add_node("dedupe", dedupe_incident)
    g.add_node("notify", notify_stdout)
    g.add_node("rag_store", rag_store)

    g.set_entry_point("ingest")
    g.add_edge("ingest", "detect")

    def _route(state: AgentState) -> str:
        return "rag_retrieve" if state.get("is_incident") else "notify"

    g.add_conditional_edges(
        "detect",
        _route,
        {"rag_retrieve": "rag_retrieve", "notify": "notify"},
    )

    # Incident path: retrieve context → RCA → dedup → notify → store in history
    g.add_edge("rag_retrieve", "rca")
    g.add_edge("rca", "dedupe")
    g.add_edge("dedupe", "notify")

    # Only store in ChromaDB on the incident path (no-incident path ends at notify)
    def _route_after_notify(state: AgentState) -> str:
        return "rag_store" if state.get("is_incident") else END

    g.add_conditional_edges(
        "notify",
        _route_after_notify,
        {"rag_store": "rag_store", END: END},
    )
    g.add_edge("rag_store", END)

    return g.compile()
