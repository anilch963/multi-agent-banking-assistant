"""Local (non-MCP) tools."""
from __future__ import annotations

import json

from langchain_core.tools import tool

from app.rag import store

PRODUCTS = {"accounts", "credit_cards", "fixed_deposits", "recurring_deposits", "loans", "insurance",
            "security_fraud", "kyc_grievance"}


@tool
def search_bank_knowledge(query: str, product: str = "") -> str:
    """Search Anil Bank's product and policy documents (fees, rates, rules, processes).
    `product` optionally narrows the search to one of: accounts, credit_cards, fixed_deposits,
    recurring_deposits, loans, insurance, security_fraud, kyc_grievance."""
    hits = store.search(query, product if product in PRODUCTS else None)
    if not hits:
        return "No relevant documents found."
    return json.dumps([{"source": f"{h['source']} > {h['section']}", "text": h["text"]} for h in hits])
