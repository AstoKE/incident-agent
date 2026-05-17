from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from ..state import AgentState
from ..config import OLLAMA_MODEL, OLLAMA_BASE_URL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

class RCAResult(BaseModel):
    summary: str = Field(..., description="One short paragraph summary of the incident.")
    root_causes: List[str] = Field(default_factory=list, description="Up to 3 likely root causes.")
    actions: List[str] = Field(default_factory=list, description="Up to 3 immediate, executable actions.")
    questions: List[str] = Field(default_factory=list, description="Up to 3 questions to ask humans for clarification.")


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert Site Reliability Engineer (SRE) performing incident root cause analysis.

ANALYSIS APPROACH (think step-by-step before writing JSON):
1. Identify the dominant error pattern and affected components from the log evidence.
2. Correlate top events with known failure modes (network, storage, auth, memory, etc.).
3. Determine the most specific root cause supported by the evidence.
4. Propose immediate, concrete actions an on-call engineer can run right now.
5. Flag anything unclear as a question for the team.

OUTPUT: Respond ONLY with valid JSON — no markdown fences, no prose outside the object.

Schema:
{
  "summary": "<one paragraph: what happened, which services, estimated impact>",
  "root_causes": ["<specific cause 1>", "<specific cause 2>", "<specific cause 3>"],
  "actions": ["<imperative action 1>", "<imperative action 2>", "<imperative action 3>"],
  "questions": ["<clarifying question 1>", "<clarifying question 2>", "<clarifying question 3>"]
}

RULES:
- Each item MUST be under 120 characters.
- actions MUST start with an imperative verb: Restart / Check / Inspect / Scale / Rollback / Verify / Drain / Rotate.
- actions must be specific and immediately runnable by an on-call engineer.
- root_causes must reference specific components or log events, not generic statements.
- If similar past incidents are provided, use them to sharpen root cause and action recommendations.

EXAMPLE (format only — do not copy content):
{
  "summary": "Payment service DB connections exhausted causing 503 errors on checkout for ~8 min.",
  "root_causes": [
    "Connection pool limit (max=100) reached due to slow queries > 5 s",
    "Missing connection timeout caused leaked connections to accumulate"
  ],
  "actions": [
    "Restart payment service pods to flush leaked DB connections",
    "Increase DB connection pool limit to 200 in payments-config.yaml",
    "Check slow query log for queries exceeding 5 s and add indexes"
  ],
  "questions": [
    "Was there a deployment to payment service in the last 2 hours?",
    "Did DB CPU spike correlate with the first 503 errors?"
  ]
}
"""


def _build_past_incidents_block(past: List[Dict[str, Any]]) -> str:
    if not past:
        return ""
    lines = ["SIMILAR PAST INCIDENTS (use to sharpen your analysis):"]
    for i, inc in enumerate(past, 1):
        ts = inc.get("timestamp", "unknown")[:19].replace("T", " ")
        sev = inc.get("severity", "?")
        svcs = ", ".join(inc.get("services") or []) or "unknown"
        evts = ", ".join(inc.get("top_events") or []) or "unknown"
        summary = inc.get("summary", "")[:200]
        causes = "; ".join(inc.get("root_causes") or [])
        actions = "; ".join(inc.get("actions") or [])
        lines.append(
            f"\n[{i}] {ts} | Severity: {sev} | Services: {svcs} | Events: {evts}\n"
            f"    Summary: {summary}\n"
            f"    Root causes: {causes}\n"
            f"    Actions taken: {actions}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

def _extract_json_object(text: str) -> Optional[dict]:
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass
    brace = re.search(r"(\{.*\})", text, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(1))
        except Exception:
            pass
    return None


def _fallback_from_text(text: str) -> RCAResult:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    summary = "Incident detected, but structured RCA could not be generated."
    root_causes: List[str] = []
    actions: List[str] = []
    questions: List[str] = []
    joined = "\n".join(lines)

    if any(k in joined for k in ("ROOT_CAUSES:", "ACTIONS:", "QUESTIONS:")):
        def _section(name: str, stops: List[str]) -> str:
            start = joined.find(name)
            if start == -1:
                return ""
            start += len(name)
            end = len(joined)
            for s in stops:
                idx = joined.find(s, start)
                if idx != -1:
                    end = min(end, idx)
            return joined[start:end].strip()

        def _parse_list(block: str) -> List[str]:
            out = []
            for ln in [x.strip() for x in block.splitlines() if x.strip()]:
                if ln.startswith(("- ", "* ")):
                    out.append(ln[2:].strip())
                elif re.match(r"^\d+[\.\)]\s+", ln):
                    out.append(re.sub(r"^\d+[\.\)]\s+", "", ln).strip())
                else:
                    out.append(ln)
            return out

        s = _section("SUMMARY:", ["ROOT_CAUSES:", "ACTIONS:", "QUESTIONS:"])
        if s:
            summary = s
        root_causes = _parse_list(_section("ROOT_CAUSES:", ["ACTIONS:", "QUESTIONS:"]))[:3]
        actions = _parse_list(_section("ACTIONS:", ["QUESTIONS:"]))[:3]
        questions = _parse_list(_section("QUESTIONS:", []))[:3]
    elif lines:
        summary = lines[0]
        root_causes = [ln[2:].strip() for ln in lines if ln.startswith("- ")][:3]

    return RCAResult(summary=summary, root_causes=root_causes, actions=actions, questions=questions)


# ---------------------------------------------------------------------------
# Default guardrail actions keyed by event keyword
# ---------------------------------------------------------------------------

_EVENT_ACTIONS: Dict[str, List[str]] = {
    "authentication_failed": [
        "Inspect auth service logs for repeated failures and identify source IPs.",
        "Verify fail2ban (or equivalent) is active and blocking suspicious IPs.",
        "Rotate service credentials and enforce key-based authentication.",
    ],
    "redis": [
        "Check Redis connection pool usage and restart stale client connections.",
        "Verify Redis memory usage and eviction policy (maxmemory-policy).",
        "Inspect Redis slow log for commands exceeding 10 ms.",
    ],
    "disk_io_error": [
        "Run 'iostat -x 1 10' to identify the saturated disk device.",
        "Check dmesg for hardware errors on the affected block device.",
        "Verify available disk space and inode counts with 'df -h' and 'df -i'.",
    ],
    "oom": [
        "Identify the OOM-killed process in /var/log/syslog or 'dmesg | grep -i oom'.",
        "Increase container/VM memory limit or reduce workload on affected node.",
        "Add memory alerts to prevent silent OOM kills in future.",
    ],
}

_GENERIC_ACTIONS = [
    "Investigate affected services and inspect recent configuration changes.",
    "Check infrastructure health (CPU, memory, disk, network) with standard monitoring tools.",
    "Review correlated log entries around the incident window for cascading failures.",
]


def _apply_guardrails(result: RCAResult, top_events: List[str]) -> RCAResult:
    events_str = " ".join(top_events).lower()
    for keyword, actions in _EVENT_ACTIONS.items():
        if keyword in events_str:
            result.actions = actions
            return result
    if not result.actions:
        result.actions = _GENERIC_ACTIONS
    return result


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------

def rca_with_llm(state: AgentState) -> AgentState:
    if not state.get("is_incident"):
        return {
            **state,
            "summary": "No incident detected in the current window.",
            "likely_root_causes": [],
            "immediate_actions": [],
            "questions_for_human": [],
        }

    logs = state.get("recent_logs", [])
    evidence = [
        {k: v for k, v in x.items() if k in ("ts", "service", "level", "event", "message")}
        for x in logs[-40:]
    ]

    past_block = _build_past_incidents_block(state.get("similar_past_incidents") or [])

    human_content = (
        f"PRIMARY EVENT: {(state.get('top_events') or ['unknown'])[0]}\n"
        f"SEVERITY: {state.get('severity')}\n"
        f"ERROR COUNT (window): {state.get('error_count')}\n"
        f"AFFECTED SERVICES: {', '.join(state.get('services') or [])}\n"
        f"ALL TOP EVENTS: {', '.join(state.get('top_events') or [])}\n\n"
        f"LOG EVIDENCE (last {len(evidence)} entries):\n"
        f"{json.dumps(evidence, indent=2)}\n"
    )
    if past_block:
        human_content += f"\n{past_block}\n"

    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.2)

    result = RCAResult(
        summary="Incident detected. (RCA not generated yet.)",
        root_causes=[],
        actions=[],
        questions=[],
    )

    try:
        raw = llm.invoke([SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=human_content)]).content or ""
        data = _extract_json_object(raw)
        if data is None:
            result = _fallback_from_text(raw)
        else:
            result = RCAResult.model_validate(data)
    except ValidationError as ve:
        logger.warning("RCA schema validation failed: %s", ve)
        result = RCAResult(
            summary="Incident detected. (Invalid structured RCA output.)",
            root_causes=[],
            actions=[],
            questions=[f"Schema validation failed: {ve.__class__.__name__}"],
        )
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        result = RCAResult(
            summary="Incident detected. (LLM unavailable or failed.)",
            root_causes=[],
            actions=[],
            questions=[f"LLM error: {type(exc).__name__}"],
        )

    top_events = [e.strip().lower() for e in (state.get("top_events") or [])]
    result = _apply_guardrails(result, top_events)

    return {
        **state,
        "summary": result.summary,
        "likely_root_causes": result.root_causes[:3],
        "immediate_actions": result.actions[:3],
        "questions_for_human": result.questions[:3],
    }
