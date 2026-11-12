"""A small, explicit tool-calling loop (ReAct) shared by every specialist.

Two things happen here that a prebuilt agent would hide:

1. `customer_id` is removed from every tool schema before the LLM sees it, and
   injected from the authenticated session when the tool is called. A prompt
   such as "show me the balance of customer C002" therefore cannot work.
2. Every tool call is recorded in a trace returned to the API.
"""
from __future__ import annotations

import copy
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from app import config

SCOPED_ARG = "customer_id"


def llm_tool_spec(tool: BaseTool) -> dict:
    """OpenAI tool schema with the session-scoped argument hidden."""
    spec = copy.deepcopy(convert_to_openai_tool(tool))
    params = spec["function"].get("parameters", {})
    params.get("properties", {}).pop(SCOPED_ARG, None)
    if SCOPED_ARG in params.get("required", []):
        params["required"] = [r for r in params["required"] if r != SCOPED_ARG]
    return spec


def _takes_customer_id(tool: BaseTool) -> bool:
    schema = tool.args_schema if isinstance(tool.args_schema, dict) else tool.get_input_schema().model_json_schema()
    return SCOPED_ARG in schema.get("properties", {})


def _as_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, list):  # MCP content blocks
        return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in result)
    return str(result)


async def run_react(llm, system_prompt: str, messages: list[BaseMessage], tools: list[BaseTool],
                    customer_id: str) -> tuple[str, list[dict]]:
    """Run the loop until the model answers without tool calls. Returns (answer, tool_trace)."""
    by_name = {t.name: t for t in tools}
    model = llm.bind_tools([llm_tool_spec(t) for t in tools]) if tools else llm
    convo: list[BaseMessage] = [SystemMessage(system_prompt), *messages]
    trace: list[dict] = []

    for _ in range(config.MAX_TOOL_STEPS):
        ai: AIMessage = await model.ainvoke(convo)
        convo.append(ai)
        if not ai.tool_calls:
            return _as_text(ai.content), trace
        for call in ai.tool_calls:
            tool = by_name.get(call["name"])
            args = {k: v for k, v in call["args"].items() if k != SCOPED_ARG}
            if tool is None:
                output = f"Error: unknown tool {call['name']}"
            else:
                try:
                    scoped = {**args, SCOPED_ARG: customer_id} if _takes_customer_id(tool) else args
                    output = _as_text(await tool.ainvoke(scoped))
                except Exception as exc:  # surface the error to the model so it can recover
                    output = f"Error: {exc}"
            trace.append({"tool": call["name"], "args": args, "ok": not output.startswith("Error")})
            convo.append(ToolMessage(content=output, tool_call_id=call["id"]))

    return "I could not complete this within the allowed number of steps.", trace
