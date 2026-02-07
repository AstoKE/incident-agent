from typing import List, Dict, Any
from ..state import AgentState
from ..config import OLLAMA_MODEL

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage


def _compress(logs: List[Dict[str, Any]], limit: int =30) -> List[Dict[str,Any]]:
    out = []
    for x in logs[-limit:]:
        out.append({
            "ts": x.get("ts"),
            "service": x.get("service"),
            "level": x.get("level"),
            "event": x.get("event"),
            "message": x.get("message"),
        })
    return out

def rca_with_llm(state: AgentState) -> AgentState:
    if not state.get("is_incident"):
        state["summary"] = "No incident detected"
        state["likely_root_causes"]=[]
        state["immediate_action"]=[]
        state["questions_for_human"]=[]
        return state

    logs = state.get("recent_logs",[])
    evidence= _compress(logs, limit=40)

    sys =SystemMessage(content=
                "You are an SRE incident assistant. "
                "Given log evidence, produce concise root cause hypotheses and immediate actions. "
                "Be practical, avoid fluff. "
                "Output MUST be in this exact format:\n"
                "SUMMARY: <one paragraph>\n"
                "ROOT_CAUSES:\n- <cause 1>\n- <cause 2>\n- <cause 3>\n"
                "ACTIONS:\n- <action 1>\n- <action 2>\n- <action 3>\n"
                "QUESTIONS:\n- <question 1>\n- <question 2>\n"
    )

    human = HumanMessage(content=
            f"Severity: {state.get('severity')}\n"
            f"Error count (window): {state.get('error_count')}\n"
            f"Affected services: {state.get('services')}\n"
            f"Top events: {state.get('top_events')}\n"
            f"Evidence (recent logs): {evidence}\n"            
    )

    llm = ChatOllama(model=OLLAMA_MODEL, temperature=0.2)
    txt= llm.invoke([sys, human]).content

    #simple parsing
    def grab_section(prefix: str) -> str:
        idx = txt.find(prefix)
        if idx == -1:
            return ""
        return txt[idx +len(prefix):].strip()
    
    #parse lists
    def parse_bullets(block: str) -> List[str]:
        lines =[l.strip() for l in block.splitlines() if l.strip()]
        return [l[2:].strip() for l in lines if l.startswith("- ")]
    

    # locate blocks
    # naive: spplit with heades

    summary = ""
    root_causes:List[str]=[]
    actions:List[str]=[]
    questions:List[str]=[]

    parts = txt.split("ROOT_CAUSES:")
    if len(parts) >= 2:

        s_part = parts[0].replace("SUMMARY:", "").strip()
        summary =s_part

        rest ="ROOT_CAUSES:" + parts[1]
        parts2 =rest.split("ACTIONS:")
        rc_block =parts2[0].replace("ROOT_CAUSES:", "").strip()
        root_causes = parse_bullets(rc_block)

        if len(parts2) >= 2:

            rest2 = "ACTIONS:" + parts2[1]
            parts3 =rest2.split("QUESTIONS:")

            act_block =parts3[0].replace("ACTIONS:", "").strip()

            actions = parse_bullets(act_block)

            if len(parts3) >= 2:

                q_block = parts3[1].strip()
                questions = parse_bullets(q_block)

    state["summary"] = summary or "Incident detected. (LLM summary parsing failed; see raw output.)"
    state["likely_root_causes"] = root_causes[:3]
    state["immediate_actions"] = actions[:3]
    state["questions_for_human"] = questions[:3]
    return state