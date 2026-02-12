
from __future__ import annotations
from typing import List, Dict, Any, Optional
from ..state import AgentState
from ..config import OLLAMA_MODEL

import json
import re
from pydantic import BaseModel, Field, ValidationError


from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage


#output schema
class RCAResult(BaseModel):
    summary: str=Field(..., description="One Short paragraph summary of the incident.")
    root_causes: List[str] =Field(default_factory=list, description="Up to 3 likely root causes.")
    actions: List[str]=Field(default_factory=list, description="Up to 3 immediate, executable actions.")
    questions: List[str]= Field(default_factory=list, description="Up to 3 questions to ask humans for clarification.")

def _compress(logs: List[Dict[str, Any]], limit: int = 40) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for x in logs[-limit:]:
        out.append(
            {
                "ts": x.get("ts"),
                "service": x.get("service"),
                "level": x.get("level"),
                "event": x.get("event"),
                "message": x.get("message"),
            }
        )
    return out

def _extract_json_object(text: str) -> Optional[dict]:
    """
    Tries to extract a JSON object from LLM output.
    Supports outputs that wrap JSON inside ```json ... ``` fences or contain extra text.
    """
    fence_match = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            return json.loads(candidate)
        except Exception:
            pass

    brace_match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
    if brace_match:
        candidate = brace_match.group(1).strip()
        try:
            return json.loads(candidate)
        except Exception:
            pass

    return None


def _fallback_from_text(text: str) -> RCAResult:
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # SUMMARY / ROOT_CAUSES / ACTIONS / QUESTIONS
    summary = "Incident detected, but structured RCA could not be generated."
    root_causes: List[str] = []
    actions: List[str] = []
    questions: List[str] = []

    joined = "\n".join(lines)

    if "ROOT_CAUSES:" in joined or "ACTIONS:" in joined or "QUESTIONS:" in joined:
        def section(name: str, next_names: List[str]) -> str:
            start = joined.find(name)
            if start == -1:
                return ""
            start += len(name)
            end = len(joined)
            for nn in next_names:
                idx = joined.find(nn, start)
                if idx != -1:
                    end = min(end, idx)
            return joined[start:end].strip()

        s = section("SUMMARY:", ["ROOT_CAUSES:", "ACTIONS:", "QUESTIONS:"])
        if s:
            summary = s

        rc = section("ROOT_CAUSES:", ["ACTIONS:", "QUESTIONS:"])
        ac = section("ACTIONS:", ["QUESTIONS:"])
        qs = section("QUESTIONS:", [])

        def parse_any_list(block: str) -> List[str]:
            if not block:
                return []
            out: List[str] = []
            for l in [x.strip() for x in block.splitlines() if x.strip()]:
                # bullets "- x", "* x", "1. x"
                if l.startswith(("- ", "* ")):
                    out.append(l[2:].strip())
                elif re.match(r"^\d+[\.\)]\s+", l):
                    out.append(re.sub(r"^\d+[\.\)]\s+", "", l).strip())
                else:
                    # plain line
                    out.append(l)
            return out

        root_causes = parse_any_list(rc)[:3]
        actions = parse_any_list(ac)[:3]
        questions = parse_any_list(qs)[:3]

        return RCAResult(
            summary=summary,
            root_causes=root_causes,
            actions=actions,
            questions=questions,
        )

    if lines:
        summary = lines[0]
    bullets = [l[2:].strip() for l in lines if l.startswith("- ")]
    root_causes = bullets[:3]

    actions = [
        "Check Redis availability and client initialization in affected services.",
        "Verify database connectivity (credentials, network, connection pool).",
        "Check external payment gateway status and retry/backoff configuration.",
    ]

    return RCAResult(
        summary=summary,
        root_causes=root_causes,
        actions=actions,
        questions=[],
    )


def rca_with_llm(state: AgentState) -> AgentState:
    # No incident
    if not state.get("is_incident"):
        return {
            **state,
            "summary": "No incident detected in the current window.",
            "likely_root_causes": [],
            "immediate_actions": [],
            "questions_for_human": [],
        }

    logs = state.get("recent_logs", [])
    evidence = _compress(logs, limit=40)

    sys = SystemMessage(
        content=(
            "You are an SRE incident assistant.\n"
            "Given log evidence, produce a concise incident summary, likely root causes, immediate actions, and questions.\n"
            "Return ONLY valid JSON that matches this schema:\n"
            "{\n"
            '  "summary": string,\n'
            '  "root_causes": [string, ...],\n'
            '  "actions": [string, ...],\n'
            '  "questions": [string, ...]\n'
            "}\n"
            "Rules:\n"
            "- Keep each list item short and actionable.\n"
            "- Provide up to 3 items for each list.\n"
            "- The \"actions\" list MUST contain exactly 3 items.\n"
            "- Use imperative verbs (Check/Verify/Restart/Inspect).\n"
            "- Do NOT include markdown or extra text, ONLY JSON.\n"
        )
    )

    human = HumanMessage(
        content=(
            f"Severity: {state.get('severity')}\n"
            f"Error count (window): {state.get('error_count')}\n"
            f"Affected services: {state.get('services')}\n"
            f"Top events: {state.get('top_events')}\n"
            f"Evidence (recent logs): {evidence}\n"
        )
    )

    llm = ChatOllama(model=OLLAMA_MODEL, temperature=0.2)

    # Default result
    result = RCAResult(
        summary="Incident detected. (RCA not generated yet.)",
        root_causes=[],
        actions=[],
        questions=[],
    )
    raw = ""

    try:
        raw = llm.invoke([sys, human]).content or ""
        data = _extract_json_object(raw)
        if data is None:
            result = _fallback_from_text(raw)
        else:
            result = RCAResult.model_validate(data)

    except ValidationError as ve:
        result = RCAResult(
            summary="Incident detected. (Invalid structured RCA output.)",
            root_causes=[],
            actions=[],
            questions=[f"Schema validation failed: {ve.__class__.__name__}"],
        )
    except Exception as e:
        result = RCAResult(
            summary="Incident detected. (LLM unavailable or failed.)",
            root_causes=[],
            actions=[],
            questions=[f"LLM error: {type(e).__name__}"],
        )

    # Guardrail: actions must not be empty
    actions = result.actions or [
        "Check Redis service health and verify client initialization order in affected services.",
        "Verify database connectivity (network, credentials, connection pool) and inspect DB logs for refused connections.",
        "Check payment gateway status and enable retries with backoff / failover if available.",
    ]

    return {
        **state,
        "rca_raw": raw,  # debug; remove later if you want
        "summary": result.summary,
        "likely_root_causes": result.root_causes[:3],
        "immediate_actions": actions[:3],
        "questions_for_human": result.questions[:3],
    }
