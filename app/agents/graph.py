"""Assemble the LangGraph workflow.

    START -> input_guardrail --blocked--> END
                   |
               supervisor --(Send x N, parallel)--> specialists --> synthesizer -> compliance -> END
                   '------------(no assignments)-------------------------^
"""
from __future__ import annotations

from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app import config
from app.agents import nodes
from app.agents.registry import SPECIALISTS
from app.agents.state import BankState


def _after_guardrail(state: BankState) -> str:
    return END if state.get("blocked") else "supervisor_agent"


def _dispatch(state: BankState):
    """Fan out: one Send per assignment, each specialist gets only what it needs."""
    plan = state.get("plan") or []
    if not plan:
        return "response_synthesizer_agent"
    history = list(state["messages"])[-config.HISTORY_WINDOW:]
    return [
        Send(a["agent"], {"messages": history, "customer_id": state["customer_id"], "task": a["task"]})
        for a in plan
    ]


def build_graph(mcp_tools: list[BaseTool], checkpointer=None):
    tools_by_name = {t.name: t for t in mcp_tools}
    g = StateGraph(BankState)

    g.add_node("input_guardrail_agent", nodes.input_guardrail)
    g.add_node("supervisor_agent", nodes.supervisor)
    g.add_node("response_synthesizer_agent", nodes.synthesizer)
    g.add_node("compliance_agent", nodes.compliance)
    for spec in SPECIALISTS:
        g.add_node(spec.name, nodes.make_specialist(spec, tools_by_name))
        g.add_edge(spec.name, "response_synthesizer_agent")

    g.add_edge(START, "input_guardrail_agent")
    g.add_conditional_edges("input_guardrail_agent", _after_guardrail, ["supervisor_agent", END])
    g.add_conditional_edges(
        "supervisor_agent", _dispatch, [s.name for s in SPECIALISTS] + ["response_synthesizer_agent"]
    )
    g.add_edge("response_synthesizer_agent", "compliance_agent")
    g.add_edge("compliance_agent", END)

    return g.compile(checkpointer=checkpointer or InMemorySaver())
