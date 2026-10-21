"""LangGraph workflow that routes Finnie requests to their agent nodes."""

from langgraph.graph import END, START, StateGraph

from src.agents.clarify import clarify
from src.agents.finance_qa import finance_qa
from src.agents.goals import goals
from src.agents.market import market
from src.agents.out_of_scope import out_of_scope
from src.agents.portfolio import portfolio
from src.core.intent_classifier import classify_intent
from src.core.router import route_intent
from src.core.state import CoreState


workflow = StateGraph(CoreState)

workflow.add_node("classify_intent", classify_intent)
workflow.add_node("finance_qa", finance_qa)
workflow.add_node("portfolio", portfolio)
workflow.add_node("market", market)
workflow.add_node("goals", goals)
workflow.add_node("clarify", clarify)
workflow.add_node("out_of_scope", out_of_scope)

workflow.add_edge(START, "classify_intent")
workflow.add_conditional_edges(
    "classify_intent",
    route_intent,
    {
        "finance_qa": "finance_qa",
        "portfolio": "portfolio",
        "market": "market",
        "goals": "goals",
        "clarify": "clarify",
        "out_of_scope": "out_of_scope",
    },
)

workflow.add_edge("finance_qa", END)
workflow.add_edge("portfolio", END)
workflow.add_edge("market", END)
workflow.add_edge("goals", END)
workflow.add_edge("clarify", END)
workflow.add_edge("out_of_scope", END)

chain = workflow.compile()


if __name__ == "__main__":
    # print(chain.get_graph().draw_mermaid())
    # chain.get_graph().draw_ascii("workflow.txt")
    # chain.get_graph().draw_png("workflow.png")
    res =chain.invoke({"user_input": "What is diversification?"})
    print(res)
