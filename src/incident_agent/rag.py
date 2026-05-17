"""
ChromaDB helper for incident history (RAG).

Stores resolved incidents as embeddings so the RCA node can retrieve
similar past incidents for better-contextualised analysis.

Uses ChromaDB's built-in OllamaEmbeddingFunction — same model already
configured, no extra dependencies needed. Falls back gracefully when
Ollama or ChromaDB are unavailable.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

from .config import (
    CHROMA_DATA_DIR,
    CHROMA_HOST,
    CHROMA_PORT,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)

logger = logging.getLogger(__name__)

_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None


def _get_collection() -> chromadb.Collection | None:
    global _client, _collection
    if _collection is not None:
        return _collection
    try:
        if CHROMA_HOST:
            _client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        else:
            _client = chromadb.PersistentClient(path=CHROMA_DATA_DIR)

        ef = OllamaEmbeddingFunction(
            url=f"{OLLAMA_BASE_URL}/api/embeddings",
            model_name=OLLAMA_MODEL,
        )
        _collection = _client.get_or_create_collection(
            name="incident_history",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB collection 'incident_history' ready")
        return _collection
    except Exception as exc:
        logger.warning("ChromaDB unavailable, RAG disabled: %s", exc)
        return None


def store_incident(state: Dict[str, Any]) -> None:
    """Persist a notified incident so future runs can retrieve it."""
    if not state.get("should_notify") or not state.get("incident_fingerprint"):
        return
    col = _get_collection()
    if col is None:
        return
    try:
        doc = (
            f"Severity: {state.get('severity')} | "
            f"Services: {', '.join(state.get('services', []))} | "
            f"Events: {', '.join(state.get('top_events', []))} | "
            f"Summary: {state.get('summary', '')}"
        )
        metadata = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": state.get("severity", ""),
            "services": json.dumps(state.get("services", [])),
            "top_events": json.dumps(state.get("top_events", [])),
            "summary": (state.get("summary") or "")[:500],
            "root_causes": json.dumps(state.get("likely_root_causes", [])),
            "actions": json.dumps(state.get("immediate_actions", [])),
        }
        col.upsert(
            documents=[doc],
            metadatas=[metadata],
            ids=[state["incident_fingerprint"]],
        )
        logger.info("Stored incident %s in ChromaDB", state["incident_fingerprint"])
    except Exception as exc:
        logger.warning("Failed to store incident in ChromaDB: %s", exc)


def retrieve_similar_incidents(query: str, n_results: int = 3) -> List[Dict[str, Any]]:
    """Return up to n_results incidents whose embedding is closest to query."""
    col = _get_collection()
    if col is None:
        return []
    try:
        count = col.count()
        if count == 0:
            return []
        results = col.query(
            query_texts=[query],
            n_results=min(n_results, count),
        )
        incidents: List[Dict[str, Any]] = []
        for meta in (results.get("metadatas") or [[]])[0]:
            incidents.append(
                {
                    "timestamp": meta.get("timestamp", ""),
                    "severity": meta.get("severity", ""),
                    "services": json.loads(meta.get("services", "[]")),
                    "top_events": json.loads(meta.get("top_events", "[]")),
                    "summary": meta.get("summary", ""),
                    "root_causes": json.loads(meta.get("root_causes", "[]")),
                    "actions": json.loads(meta.get("actions", "[]")),
                }
            )
        return incidents
    except Exception as exc:
        logger.warning("Failed to retrieve from ChromaDB: %s", exc)
        return []
