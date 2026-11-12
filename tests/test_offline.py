import json

import pytest
from fastapi.testclient import TestClient

from app import finance
from app.db import actions, analytics
from app.db.database import query_one


def test_emi_and_inverse():
    result = finance.emi(1_000_000, 9.0, 120)
    assert result["emi"] == pytest.approx(12667.58, abs=0.01)
    assert finance.max_principal_for_emi(result["emi"], 9.0, 120) == pytest.approx(1_000_000, abs=5)
    assert finance.emi(120_000, 0, 12)["emi"] == 10_000


def test_deposit_maturity():
    assert finance.fd_maturity(100_000, 8.0, 12)["maturity_amount"] == pytest.approx(108_243.22, abs=0.01)
    rd = finance.rd_maturity(5_000, 7.0, 12)
    assert rd["total_deposited"] == 60_000 and 2_200 < rd["interest_earned"] < 2_400


def test_sql_sandbox_is_scoped_and_read_only():
    own = analytics.run_sandboxed("C001", "SELECT COUNT(*) FROM accounts")
    assert own["rows"] == [[2]]
    leak = analytics.run_sandboxed("C001", "SELECT COUNT(*) FROM accounts WHERE customer_id <> 'C001'")
    assert leak["rows"] == [[0]]
    for bad in ("DROP TABLE loans", "SELECT 1; DELETE FROM loans", "UPDATE accounts SET balance = 0"):
        with pytest.raises(ValueError):
            analytics.run_sandboxed("C001", bad)


def test_action_needs_confirmation_and_ownership():
    before = query_one("SELECT balance FROM accounts WHERE account_id = 'SB1001'")["balance"]
    proposal = actions.propose("C001", "open_fd", {"principal": 50_000, "tenure_months": 12,
                               "interest_rate": 6.75, "source_account_id": "SB1001"}, "Open FD")
    assert query_one("SELECT balance FROM accounts WHERE account_id = 'SB1001'")["balance"] == before
    with pytest.raises(LookupError):  # another customer cannot confirm it
        actions.resolve("C002", proposal["action_id"], True)
    done = actions.resolve("C001", proposal["action_id"], True)
    assert done["status"] == "executed" and done["result"]["created"].startswith("FD")
    assert query_one("SELECT balance FROM accounts WHERE account_id = 'SB1001'")["balance"] == before - 50_000
    with pytest.raises(ValueError):  # cannot be replayed
        actions.resolve("C001", proposal["action_id"], True)


def test_chat_end_to_end_with_stub_llm(stub_llm, monkeypatch):
    """Real graph + real MCP subprocess + real FastAPI app; only the LLM and embeddings are stubbed."""
    monkeypatch.setattr("app.rag.store.ingest", lambda *a, **k: 0)
    stub = stub_llm([{"agent": "accounts_agent", "task": "list balances"},
                     {"agent": "credit_card_agent", "task": "list cards"}])
    from app.main import app

    with TestClient(app) as client:
        health = client.get("/health").json()
        assert health["agents"] == 15 and health["mcp_tools"] >= 20

        r = client.post("/chat", json={"customer_id": "C001", "message": "balances and card dues?"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["agents_used"] == ["accounts_agent", "credit_card_agent"]
        # both specialists ran in parallel and their tool output reached the final answer
        assert "accounts_agent" in body["answer"] and "credit_card_agent" in body["answer"]
        assert "SB2001" not in body["answer"] and "CC2001" not in body["answer"]  # no other customer's data
        tool_calls = [t for t in body["trace"] if t.get("tool_calls")]
        assert len(tool_calls) == 2 and all(c["ok"] for t in tool_calls for c in t["tool_calls"])

        # the LLM is never shown the customer_id argument
        assert stub.seen_specs and all(
            "customer_id" not in json.dumps(s["function"]["parameters"]) for s in stub.seen_specs)

        # second turn on the same thread starts with clean findings
        r2 = client.post("/chat", json={"customer_id": "C001", "message": "again", "thread_id": body["thread_id"]})
        assert r2.json()["answer"].count("### accounts_agent") == 1

        assert client.post("/chat", json={"customer_id": "C999", "message": "hi"}).status_code == 404
        assert client.post("/actions/9999/resolve", json={"customer_id": "C001"}).status_code == 404
