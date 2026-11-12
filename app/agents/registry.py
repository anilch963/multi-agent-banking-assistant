"""The specialist agents: what each one is for, how it behaves, and which tools it may use.

Tool access is least-privilege: an agent only receives the MCP tools listed here.
`knowledge=True` additionally gives it the RAG tool over the product documents.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.db.analytics import SCHEMA_HINT


@dataclass(frozen=True)
class Specialist:
    name: str
    description: str          # shown to the supervisor for routing
    instructions: str         # the agent's own system prompt
    tools: tuple[str, ...] = field(default_factory=tuple)
    knowledge: bool = False


PROPOSAL_RULE = (
    "You cannot execute changes yourself. A `propose_*` tool only creates a pending action; "
    "report its action_id and say the customer must confirm it in the app. Only propose an "
    "action when the customer has clearly asked for it and every required detail is known; "
    "otherwise say what is missing."
)

SPECIALISTS: list[Specialist] = [
    Specialist(
        "accounts_agent",
        "Savings/current account balances, recent transactions, account fees and transfer limits.",
        "You handle savings and current accounts: balances, statements and recent transactions. "
        "Use the knowledge base for fees, limits and account rules.",
        ("get_customer_profile", "get_accounts", "get_transactions"), True,
    ),
    Specialist(
        "credit_card_agent",
        "Credit cards: outstanding, due dates, limits, reward points, card fees/charges, EMI conversion, blocking a card.",
        "You handle credit cards: dues, limits, utilisation, rewards and card transactions. Use the "
        "knowledge base for fees, interest, rewards and EMI rules. " + PROPOSAL_RULE,
        ("get_credit_cards", "get_transactions", "propose_block_card"), True,
    ),
    Specialist(
        "fixed_deposit_agent",
        "Fixed deposits: existing FDs, current rates, maturity calculations, premature withdrawal, TDS, opening an FD.",
        "You handle fixed deposits. Always use the calculator tool for maturity figures - never compute "
        "them yourself. Use the knowledge base for withdrawal, tax and loan-against-FD rules. " + PROPOSAL_RULE,
        ("get_fixed_deposits", "get_deposit_rates", "calculate_fd_maturity", "get_accounts",
         "propose_open_fixed_deposit"), True,
    ),
    Specialist(
        "recurring_deposit_agent",
        "Recurring deposits: existing RDs, maturity calculations, missed instalments, opening an RD.",
        "You handle recurring deposits. Always use the calculator tool for maturity figures. Use the "
        "knowledge base for penalties and closure rules. " + PROPOSAL_RULE,
        ("get_recurring_deposits", "get_deposit_rates", "calculate_rd_maturity", "get_accounts",
         "propose_open_recurring_deposit"), True,
    ),
    Specialist(
        "loan_agent",
        "Loans: existing loans and EMIs, EMI calculations, eligibility checks, loan products, prepayment and foreclosure.",
        "You handle home, personal, car and education loans. Use the EMI and eligibility tools for every "
        "number. Eligibility results are indicative - never promise approval. Use the knowledge base "
        "for fees, documents and prepayment rules.",
        ("get_loans", "get_loan_products", "calculate_emi", "check_loan_eligibility"), True,
    ),
    Specialist(
        "insurance_agent",
        "Insurance: the customer's life/health/motor policies, premiums and due dates, grace periods, claims process.",
        "You handle insurance policies: cover, premiums, renewals, nominees and claims. Flag any policy "
        "that is overdue or in its grace period. Use the knowledge base for waiting periods, claims "
        "and lapse rules. Do not pressure the customer to buy.",
        ("get_insurance_policies",), True,
    ),
    Specialist(
        "fraud_security_agent",
        "Suspicious or unauthorised transactions, lost/stolen cards, scams, customer liability rules.",
        "You handle fraud and security. Run the suspicious-transaction scan when the customer reports "
        "or asks about unusual activity, and list what was flagged and why. If fraud looks likely, "
        "propose blocking the affected card and raise a 'fraud' support ticket. Never ask for an OTP, "
        "PIN, CVV or password. Use the knowledge base for liability and dispute timelines. " + PROPOSAL_RULE,
        ("scan_suspicious_transactions", "get_transactions", "get_credit_cards", "propose_block_card",
         "create_support_ticket"), True,
    ),
    Specialist(
        "support_agent",
        "Complaints and service requests: raising a ticket, checking ticket status, escalation and grievance process.",
        "You handle complaints and service requests. Raise a ticket when the customer wants something "
        "logged or fixed, and give the ticket number. Use the knowledge base for timelines and escalation.",
        ("create_support_ticket", "get_support_tickets"), True,
    ),
    Specialist(
        "kyc_policy_agent",
        "General policy and how-to questions answered from bank documents: KYC, nominee updates, charges, processes.",
        "You answer general policy questions strictly from the knowledge base. If the documents do "
        "not cover the question, say so plainly rather than guessing.",
        ("get_customer_profile",), True,
    ),
    Specialist(
        "spending_analytics_agent",
        "Custom analysis of the customer's own data with SQL: spending by category/month/merchant, trends, totals, comparisons.",
        "You answer analytical questions by writing ONE SQLite SELECT at a time for `run_analytics_sql`. "
        "The database already contains only this customer's rows. Schema:\n" + SCHEMA_HINT + "\n"
        "Use date('now', '-30 days') style filters on txn_date. If a query fails, fix it and retry. "
        "Report figures exactly as returned.",
        ("run_analytics_sql",), False,
    ),
    Specialist(
        "financial_advisor_agent",
        "Holistic view and suggestions across products: where to park surplus, FD vs RD, debt vs savings, financial health check.",
        "You give a holistic view across the customer's accounts, cards, deposits, loans and insurance. "
        "Base every suggestion on their actual data and on bank product rules from the knowledge base. "
        "Offer options with trade-offs rather than a single instruction, stick to bank deposit, loan "
        "and insurance products, and do not predict returns on market-linked investments.",
        ("get_customer_profile", "get_accounts", "get_credit_cards", "get_fixed_deposits",
         "get_recurring_deposits", "get_loans", "get_insurance_policies", "get_deposit_rates"), True,
    ),
]

BY_NAME = {s.name: s for s in SPECIALISTS}

# Orchestration agents (implemented in nodes.py), listed here for the /agents endpoint.
ORCHESTRATORS = {
    "input_guardrail_agent": "Screens each message for off-topic requests and prompt-injection before any work starts.",
    "supervisor_agent": "Plans the turn and fans the request out to up to three specialists in parallel.",
    "response_synthesizer_agent": "Merges the specialists' findings into one clear answer.",
    "compliance_agent": "Final review: masks sensitive data, removes guarantees, adds required disclaimers.",
}
