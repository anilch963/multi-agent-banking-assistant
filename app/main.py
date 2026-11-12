"""FastAPI entry point.

    uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging
import os
import sys
import uuid
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, HTTPException
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from pydantic import BaseModel, Field

from app import config
from app.agents.graph import build_graph
from app.agents.registry import ORCHESTRATORS, SPECIALISTS
from app.db import actions
from app.db.database import customer_exists, query
from app.db.seed import init_db
from app.rag import store

log = logging.getLogger("banking")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.llm_ready = bool(os.getenv("OPENAI_API_KEY"))
    if app.state.llm_ready:
        try:
            log.info("knowledge base ready: %s chunks", store.ingest())
        except Exception:
            log.exception("knowledge-base ingestion failed; RAG answers will be unavailable")
    else:
        log.warning("OPENAI_API_KEY is not set - /chat will return 503")

    # One long-lived MCP session: the banking server runs as a stdio subprocess.
    client = MultiServerMCPClient({
        "banking": {
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-m", "app.mcp_server.server"],
            "cwd": str(config.BASE_DIR),
            "env": dict(os.environ),
        }
    })
    async with AsyncExitStack() as stack:
        session = await stack.enter_async_context(client.session("banking"))
        mcp_tools = await load_mcp_tools(session)
        app.state.graph = build_graph(mcp_tools)
        app.state.mcp_tools = [t.name for t in mcp_tools]
        yield


app = FastAPI(title=f"{config.BANK_NAME} multi-agent assistant", version="1.0.0", lifespan=lifespan)


class ChatRequest(BaseModel):
    # In production this comes from the verified auth token, never from the request body.
    customer_id: str = Field(examples=["C001"])
    message: str = Field(min_length=1, max_length=4000, examples=["What is my credit card outstanding?"])
    thread_id: str | None = Field(default=None, description="Send the same id to continue a conversation")


class ChatResponse(BaseModel):
    thread_id: str
    answer: str
    agents_used: list[str]
    pending_actions: list[dict]
    trace: list[dict]


class ActionDecision(BaseModel):
    customer_id: str
    approve: bool = True


def _require_customer(customer_id: str) -> None:
    if not customer_exists(customer_id):
        raise HTTPException(404, "unknown customer")


@app.get("/health")
async def health():
    return {"status": "ok", "llm_configured": app.state.llm_ready, "model": config.OPENAI_MODEL,
            "mcp_tools": len(app.state.mcp_tools), "agents": len(SPECIALISTS) + len(ORCHESTRATORS)}


@app.get("/agents")
async def agents():
    return {
        "orchestrators": ORCHESTRATORS,
        "specialists": [{"name": s.name, "description": s.description,
                         "tools": list(s.tools) + (["search_bank_knowledge"] if s.knowledge else [])}
                        for s in SPECIALISTS],
    }


@app.get("/customers")
async def customers():
    """Demo helper: the seeded customers you can chat as."""
    return query("SELECT customer_id, name, city, kyc_status FROM customers")


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    _require_customer(req.customer_id)
    if not app.state.llm_ready:
        raise HTTPException(503, "OPENAI_API_KEY is not configured")
    thread_id = req.thread_id or uuid.uuid4().hex
    # Namespacing by customer stops one customer resuming another's thread.
    cfg = {"configurable": {"thread_id": f"{req.customer_id}:{thread_id}"}, "recursion_limit": 25}
    try:
        state = await app.state.graph.ainvoke(
            {"messages": [HumanMessage(req.message)], "customer_id": req.customer_id}, cfg
        )
    except Exception as exc:
        log.exception("chat failed")
        raise HTTPException(502, f"assistant error: {type(exc).__name__}") from exc
    return ChatResponse(
        thread_id=thread_id,
        answer=str(state["messages"][-1].content),
        agents_used=[a["agent"] for a in state.get("plan", [])],
        pending_actions=actions.list_pending(req.customer_id),
        trace=state.get("trace", []),
    )


@app.get("/actions")
async def pending_actions(customer_id: str):
    _require_customer(customer_id)
    return actions.list_pending(customer_id)


@app.post("/actions/{action_id}/resolve")
async def resolve_action(action_id: int, decision: ActionDecision):
    """The customer's explicit confirmation (approve=true) or cancellation of a proposed action."""
    _require_customer(decision.customer_id)
    try:
        return actions.resolve(decision.customer_id, action_id, decision.approve)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
