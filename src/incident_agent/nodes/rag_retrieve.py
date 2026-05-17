from __future__ import annotations

import logging
from ..state import AgentState
from ..rag import retrieve_similar_incidents

logger = logging.getLogger(__name__)


def rag_retrieve(state: AgentState) -> AgentState:
    """Query ChromaDB for incidents similar to the current one.

    Runs only when an incident is detected; injects results into state so
    rca_with_llm can include them as context.
    """
    if not state.get("is_incident"):
        return {**state, "similar_past_incidents": []}

    query = (
        f"{state.get('severity', '')} "
        f"{' '.join(state.get('top_events', []))} "
        f"{' '.join(state.get('services', []))}"
    ).strip()

    similar = retrieve_similar_incidents(query, n_results=3)
    if similar:
        logger.info("RAG: retrieved %d similar past incident(s)", len(similar))
    else:
        logger.debug("RAG: no similar past incidents found")

    return {**state, "similar_past_incidents": similar}
