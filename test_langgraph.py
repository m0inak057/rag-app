import sys
from langgraph.graph import StateGraph, START, END
from typing import TypedDict, List

class AgentState(TypedDict, total=False):
    my_val: str
    trace: List[str]

def my_node(state: AgentState):
    state["trace"].append("in my_node")
    state["my_val"] = "updated"
    return "next_node"

def generate(state: AgentState):
    state["trace"].append("in generate")
    return END

graph = StateGraph(AgentState)
graph.add_node("my_node", my_node)
graph.add_node("generate", generate)
graph.add_edge(START, "my_node")
graph.add_edge("my_node", "generate")
graph.add_edge("generate", END)

app = graph.compile()
try:
    res = app.invoke({"trace": ["start"], "my_val": "initial"})
    print("SUCCESS", res)
except Exception as e:
    print("EXCEPTION", type(e), str(e))
