"""
Mini LangGraph örneği — LLM gerektirmez, anında çalışır.

Çalıştır:  .\.venv\Scripts\python.exe docs\ornek_mini_graph.py

Projedeki graph.py ile aynı yapı: State → Node'lar → (koşullu) Edge'ler → compile → invoke
"""
from typing import List, TypedDict

from langgraph.graph import END, StateGraph


# 1) STATE: node'ların paylaştığı ortak sözlük
class MiniState(TypedDict, total=False):
    logs: List[str]
    error_count: int
    is_incident: bool
    message: str


# 2) NODE'LAR: state alır, değişen alanları döndürür (LangGraph birleştirir)
def count_errors(state: MiniState) -> MiniState:
    n = sum(1 for line in state["logs"] if "ERROR" in line)
    print(f"[count_errors] {n} hata bulundu")
    return {"error_count": n, "is_incident": n >= 2}


def alert(state: MiniState) -> MiniState:
    print("[alert] Olay var! Burada gerçek projede LLM çağrılırdı.")
    return {"message": f"ALARM: {state['error_count']} hata"}


def all_good(state: MiniState) -> MiniState:
    print("[all_good] Sorun yok.")
    return {"message": "Her şey yolunda"}


# 3) ROUTER: koşullu kenar için bir sonraki node'un adını döndürür
def route(state: MiniState) -> str:
    return "alert" if state["is_incident"] else "all_good"


# 4) GRAFI KUR
g = StateGraph(MiniState)
g.add_node("count_errors", count_errors)
g.add_node("alert", alert)
g.add_node("all_good", all_good)

g.set_entry_point("count_errors")
g.add_conditional_edges("count_errors", route, {"alert": "alert", "all_good": "all_good"})
g.add_edge("alert", END)
g.add_edge("all_good", END)

graph = g.compile()


if __name__ == "__main__":
    print("=== Senaryo 1: hatalı loglar ===")
    out = graph.invoke({"logs": ["INFO ok", "ERROR db down", "ERROR timeout"]})
    print("Son state:", out, "\n")

    print("=== Senaryo 2: temiz loglar ===")
    out = graph.invoke({"logs": ["INFO ok", "INFO ok"]})
    print("Son state:", out, "\n")

    print("=== Grafın Mermaid diyagramı (mermaid.live'a yapıştır) ===")
    print(graph.get_graph().draw_mermaid())
