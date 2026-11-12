# Anil Bank - multi-agent banking assistant

A 15-agent banking assistant covering accounts, credit cards, fixed deposits, recurring
deposits, loans, insurance, fraud, complaints, spending analytics and financial guidance.
Anil Bank is fictional; all customers and figures are seeded demo data.

**Stack:** LangGraph (orchestration) - MCP (banking tools) - ChromaDB + OpenAI embeddings (RAG) -
SQLite (SQL) - FastAPI - OpenAI chat model.

## Architecture

```
POST /chat
   |
input_guardrail_agent ----(off-topic / unsafe)----> polite refusal
   |
supervisor_agent            plans the turn, picks up to 3 specialists
   |  LangGraph Send (parallel fan-out)
   +-- accounts_agent            +-- insurance_agent
   +-- credit_card_agent         +-- fraud_security_agent
   +-- fixed_deposit_agent       +-- support_agent
   +-- recurring_deposit_agent   +-- kyc_policy_agent
   +-- loan_agent                +-- spending_analytics_agent (text-to-SQL)
   +-- financial_advisor_agent
   |
response_synthesizer_agent  merges findings into one reply
   |
compliance_agent            masks sensitive data, removes guarantees, adds disclaimers
   |
answer + agents_used + pending_actions + trace
```

Each specialist is a tool-calling (ReAct) loop with **only the tools it needs**:

| Source | What it provides |
|---|---|
| MCP server (`app/mcp_server/server.py`, 21 tools, stdio) | customer data, calculators, eligibility, fraud scan, tickets, SQL sandbox, action proposals |
| RAG (`app/rag/store.py`) | `search_bank_knowledge` over `knowledge_base/*.md` (50 chunks, one per section) |

## Safety design (the parts worth reading)

- **Customer scoping** - `customer_id` is stripped from every tool schema before the LLM sees it
  and injected from the session on each call (`app/agents/react.py`). The model cannot ask for
  another customer's data.
- **Confirmation-gated writes** - agents can only *propose* opening an FD/RD or blocking a card.
  The proposal sits in `pending_actions` until the customer calls
  `POST /actions/{id}/resolve`. The LLM is never in the confirmation path.
- **Sandboxed text-to-SQL** - the analytics agent's SQL runs on a throw-away in-memory copy that
  holds only that customer's rows (`app/db/analytics.py`).
- **No LLM arithmetic** - EMI, FD and RD figures come from `app/finance.py`.
- **Two guardrails** - input screening before any work, compliance review before any reply.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add your OPENAI_API_KEY
python -m app.db.seed           # optional: the app seeds on first start
python -m app.rag.store         # optional: the app ingests on first start
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs, or:

```bash
curl -s localhost:8000/chat -H 'content-type: application/json' -d '{
  "customer_id": "C001",
  "message": "What do I owe on my cards, and is anything suspicious on them?"
}'
```

Things to try (customers: `C001`, `C002`, `C003`):

- "If I put 2 lakh in an FD for 24 months, what do I get? And what is the penalty for breaking it early?"
- "Open an RD of 5000 a month for 2 years from SB1001" -> then `GET /actions?customer_id=C001`
  and `POST /actions/{id}/resolve` with `{"customer_id": "C001", "approve": true}`
- "Am I eligible for a 5 lakh personal loan over 3 years?" (try as `C003`: pending KYC, low score)
- "How much did I spend on dining vs groceries in the last 60 days?"
- "My health insurance premium is overdue - what happens now?" (as `C003`)
- "I have about 3 lakh idle. Prepay my home loan or open an FD?"

Send the returned `thread_id` back to continue a conversation.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | status, model, tool and agent counts |
| GET | `/agents` | every agent with its description and tools |
| GET | `/customers` | seeded demo customers |
| POST | `/chat` | `{customer_id, message, thread_id?}` |
| GET | `/actions?customer_id=` | actions awaiting confirmation |
| POST | `/actions/{id}/resolve` | `{customer_id, approve}` |

## Tests

```bash
pytest -q
```

Runs offline: calculators, SQL sandbox, confirmation flow, and a full `/chat` round trip through
the real graph, real MCP server and real FastAPI app with a stub LLM.

## Layout

```
app/
  main.py            FastAPI app, MCP session lifecycle
  config.py  finance.py
  agents/            state, registry (agent definitions), react loop, nodes, graph
  mcp_server/        MCP banking tools
  rag/               ChromaDB ingest + search
  db/                schema, seed data, pending actions, SQL sandbox
knowledge_base/      product and policy documents
tests/
```

## Before this goes anywhere near production

- Take `customer_id` from a verified auth token, not the request body.
- Replace `InMemorySaver` with a persistent checkpointer and SQLite with PostgreSQL.
- Add rate limiting, audit logging of every tool call, PII redaction in logs, and LangSmith/OTel tracing.
- Evaluate routing and answer quality (e.g. RAGAS on the knowledge agent) before trusting it.
