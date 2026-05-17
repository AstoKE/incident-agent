from __future__ import annotations

import logging
from ..state import AgentState
from ..rag import store_incident

logger = logging.getLogger(__name__)


def rag_store(state: AgentState) -> AgentState:
    """Persist a newly-notified incident in ChromaDB for future RAG lookups.

    Skips deduped incidents (should_notify=False) to avoid polluting the
    history with repeated entries.
    """
    if state.get("should_notify"):
        store_incident(state)
    return state
