from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

RESET = "__reset__"


def collect(old: list | None, new) -> list:
    """Reducer that lets parallel specialists append, and a new turn start clean."""
    if new == RESET:
        return []
    return (old or []) + list(new or [])


class BankState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]  # customer-facing conversation only
    customer_id: str        # set by the API from the authenticated session, never by an LLM
    blocked: bool           # input guardrail verdict
    plan: list[dict]        # supervisor's assignments for this turn: [{agent, task}]
    findings: Annotated[list[dict], collect]  # specialists' results for this turn
    trace: Annotated[list[dict], collect]     # what happened, for observability
    draft: str              # synthesizer output awaiting compliance review
