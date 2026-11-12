"""Tests run fully offline: a temp database, a stub LLM, and the real MCP server."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="bank-test-")
os.environ["BANK_DATA_DIR"] = _tmp
os.environ["BANK_DB_PATH"] = os.path.join(_tmp, "bank.db")
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")

import pytest  # noqa: E402
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402

from app.db.seed import init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    init_db(force=True)


class StubLLM:
    """Deterministic stand-in for ChatOpenAI.

    - structured output: approves the message, returns the scripted plan, passes the draft through
    - with tools bound: calls the first tool that needs no arguments, then reports its output
    - otherwise: echoes the last message (so tool output flows through to the final answer)
    """

    def __init__(self, plan, specs=None, seen_specs=None):
        self.plan, self.specs = plan, specs
        self.seen_specs = seen_specs if seen_specs is not None else []

    def bind_tools(self, specs):
        self.seen_specs.extend(specs)
        return StubLLM(self.plan, specs, self.seen_specs)

    def with_structured_output(self, schema):
        stub = self

        class _Structured:
            async def ainvoke(self, messages):
                name = schema.__name__
                if name == "Verdict":
                    return schema(allowed=True, category="banking", reason="stub")
                if name == "Plan":
                    return schema(reasoning="stub", assignments=stub.plan)
                text = str(messages[-1].content)
                return schema(compliant=True, issues=[], final_answer=text.split("[Draft reply]\n")[-1])

        return _Structured()

    async def ainvoke(self, messages):
        last = messages[-1]
        if self.specs and not isinstance(last, ToolMessage):
            spec = next(s for s in self.specs if not s["function"]["parameters"].get("required"))
            return AIMessage("", tool_calls=[{"name": spec["function"]["name"], "args": {}, "id": "call_1"}])
        return AIMessage(str(last.content))


@pytest.fixture
def stub_llm(monkeypatch):
    def install(plan):
        stub = StubLLM(plan)
        monkeypatch.setattr("app.agents.nodes.get_llm", lambda: stub)
        return stub
    return install
