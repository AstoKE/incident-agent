from __future__ import annotations

import logging
from ..state import AgentState
from ..rag import store_incident
from ..store import save_incident

logger = logging.getLogger(__name__)


def rag_store(state: AgentState) -> AgentState:
    """Persist a newly-notified incident in ChromaDB (RAG) and the JSONL store (dashboard).

    Skips deduped incidents (should_notify=False).
    """
    if state.get("should_notify"):
        store_incident(state)   # ChromaDB — for future RAG retrieval
        save_incident(state)    # JSONL file — for the web dashboard
    return state
