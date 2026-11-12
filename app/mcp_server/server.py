"""Anil Bank MCP server - every banking capability the agents can use.

Runs over stdio (the FastAPI app launches it as a subprocess), or standalone:

    python -m app.mcp_server.server

Every tool takes `customer_id`. The agents' LLMs never see or set that argument:
the orchestration layer strips it from the tool schema and injects the
authenticated customer's id on every call (see app/agents/react.py).
"""
from __future__ import annotations

import json
import statistics
from datetime import date, datetime, timedelta

from mcp.server.fastmcp import FastMCP

from app import finance
from app.db import actions, analytics
from app.db.database import execute, query, query_one
from app.db.seed import init_db

mcp = FastMCP("Anil-banking", log_level="WARNING")


def _json(data) -> str:
    return json.dumps(data, default=str)


def _own(table: str, id_col: str, value: str, customer_id: str) -> dict:
    row = query_one(f"SELECT * FROM {table} WHERE {id_col} = ? AND customer_id = ?", (value, customer_id))
    if row is None:
        raise ValueError(f"{value} not found for this customer")
    return row


# ----------------------------------------------------------------- profile / accounts
@mcp.tool()
def get_customer_profile(customer_id: str) -> str:
    """Customer profile: name, city, KYC status, employment type, monthly income, credit score."""
    return _json(query_one(
        "SELECT name, city, date_of_birth, kyc_status, employment_type, monthly_income, credit_score"
        " FROM customers WHERE customer_id = ?", (customer_id,)))


@mcp.tool()
def get_accounts(customer_id: str) -> str:
    """List the customer's savings/current accounts with balances."""
    return _json(query(
        "SELECT account_id, account_type, balance, branch, status FROM accounts WHERE customer_id = ?",
        (customer_id,)))


@mcp.tool()
def get_transactions(customer_id: str, days: int = 30, account_or_card_id: str = "",
                     category: str = "", limit: int = 20) -> str:
    """Recent transactions, newest first. Optionally filter by an account/card id or a
    category (groceries, dining, shopping, fuel, utilities, entertainment, transport, health, travel, income)."""
    sql = "SELECT txn_date, description, category, amount, txn_type, channel, city, account_id, card_id" \
          " FROM transactions WHERE customer_id = ? AND txn_date >= ?"
    params: list = [customer_id, (date.today() - timedelta(days=max(1, days))).isoformat()]
    if account_or_card_id:
        sql += " AND (account_id = ? OR card_id = ?)"
        params += [account_or_card_id, account_or_card_id]
    if category:
        sql += " AND category = ?"
        params.append(category.lower())
    sql += " ORDER BY txn_date DESC, txn_id DESC LIMIT ?"
    params.append(min(max(1, limit), 50))
    return _json(query(sql, tuple(params)))


# ----------------------------------------------------------------- credit cards
@mcp.tool()
def get_credit_cards(customer_id: str) -> str:
    """Credit cards: limit, outstanding, minimum due, due date, reward points, status."""
    cards = query(
        "SELECT card_id, card_name, last4, credit_limit, outstanding, minimum_due, due_date, reward_points, status"
        " FROM credit_cards WHERE customer_id = ?", (customer_id,))
    for c in cards:
        c["available_limit"] = round(c["credit_limit"] - c["outstanding"], 2)
        c["utilisation_pct"] = round(100 * c["outstanding"] / c["credit_limit"], 1)
    return _json(cards)


@mcp.tool()
def propose_block_card(customer_id: str, card_id: str, reason: str) -> str:
    """Propose blocking a credit card (lost, stolen or suspected fraud). Creates a pending
    action that the customer must confirm in the app; the card is NOT blocked yet."""
    card = _own("credit_cards", "card_id", card_id, customer_id)
    if card["status"] == "blocked":
        return _json({"status": "already_blocked", "card_id": card_id})
    return _json(actions.propose(
        customer_id, "block_card", {"card_id": card_id, "reason": reason},
        f"Block {card['card_name']} ending {card['last4']} - {reason}"))


# ----------------------------------------------------------------- fixed deposits
@mcp.tool()
def get_fixed_deposits(customer_id: str) -> str:
    """The customer's fixed deposits with rate, maturity date and maturity amount."""
    return _json(query(
        "SELECT fd_id, principal, interest_rate, tenure_months, start_date, maturity_date, maturity_amount, status"
        " FROM fixed_deposits WHERE customer_id = ?", (customer_id,)))


def _fd_rate(customer_id: str, tenure_months: int) -> float:
    slab = query_one(
        "SELECT regular_rate, senior_rate FROM fd_rates WHERE ? BETWEEN min_months AND max_months", (tenure_months,))
    if slab is None:
        raise ValueError("tenure must be between 1 and 120 months")
    dob = query_one("SELECT date_of_birth FROM customers WHERE customer_id = ?", (customer_id,))["date_of_birth"]
    age = (date.today() - date.fromisoformat(dob)).days // 365
    return slab["senior_rate"] if age >= 60 else slab["regular_rate"]


@mcp.tool()
def get_deposit_rates(customer_id: str) -> str:
    """Current FD/RD interest-rate slabs by tenure (regular and senior-citizen rates)."""
    return _json(query("SELECT min_months, max_months, regular_rate, senior_rate FROM fd_rates ORDER BY min_months"))


@mcp.tool()
def calculate_fd_maturity(customer_id: str, principal: float, tenure_months: int) -> str:
    """Maturity amount and interest for a new FD at the rate this customer is eligible for."""
    rate = _fd_rate(customer_id, tenure_months)
    return _json({"principal": principal, "tenure_months": tenure_months, "interest_rate": rate,
                  **finance.fd_maturity(principal, rate, tenure_months)})


@mcp.tool()
def propose_open_fixed_deposit(customer_id: str, principal: float, tenure_months: int,
                               source_account_id: str) -> str:
    """Propose opening an FD funded from one of the customer's accounts (minimum 5,000).
    Creates a pending action the customer must confirm in the app; no money moves yet."""
    if principal < 5000:
        raise ValueError("minimum FD amount is 5,000")
    acct = _own("accounts", "account_id", source_account_id, customer_id)
    if acct["balance"] < principal:
        raise ValueError(f"insufficient balance: {acct['balance']:.2f} available")
    rate = _fd_rate(customer_id, tenure_months)
    amount = finance.fd_maturity(principal, rate, tenure_months)["maturity_amount"]
    return _json(actions.propose(
        customer_id, "open_fd",
        {"principal": principal, "tenure_months": tenure_months, "interest_rate": rate,
         "source_account_id": source_account_id},
        f"Open FD of {principal:,.0f} for {tenure_months} months at {rate}% from {source_account_id}"
        f" (matures at about {amount:,.0f})"))


# ----------------------------------------------------------------- recurring deposits
@mcp.tool()
def get_recurring_deposits(customer_id: str) -> str:
    """The customer's recurring deposits: instalment, rate, instalments paid, maturity."""
    return _json(query(
        "SELECT rd_id, monthly_installment, interest_rate, tenure_months, installments_paid, start_date,"
        " maturity_date, maturity_amount, status FROM recurring_deposits WHERE customer_id = ?", (customer_id,)))


@mcp.tool()
def calculate_rd_maturity(customer_id: str, monthly_installment: float, tenure_months: int) -> str:
    """Maturity amount and interest for a new RD at the rate this customer is eligible for."""
    rate = _fd_rate(customer_id, tenure_months)
    return _json({"monthly_installment": monthly_installment, "tenure_months": tenure_months,
                  "interest_rate": rate, **finance.rd_maturity(monthly_installment, rate, tenure_months)})


@mcp.tool()
def propose_open_recurring_deposit(customer_id: str, monthly_installment: float, tenure_months: int,
                                   source_account_id: str) -> str:
    """Propose opening an RD (minimum 500/month, 6-120 months) debited from one of the
    customer's accounts. Creates a pending action the customer must confirm in the app."""
    if monthly_installment < 500 or not 6 <= tenure_months <= 120:
        raise ValueError("RD needs at least 500 per month and a tenure of 6-120 months")
    acct = _own("accounts", "account_id", source_account_id, customer_id)
    if acct["balance"] < monthly_installment:
        raise ValueError("insufficient balance for the first instalment")
    rate = _fd_rate(customer_id, tenure_months)
    return _json(actions.propose(
        customer_id, "open_rd",
        {"monthly_installment": monthly_installment, "tenure_months": tenure_months, "interest_rate": rate,
         "source_account_id": source_account_id},
        f"Open RD of {monthly_installment:,.0f}/month for {tenure_months} months at {rate}% from {source_account_id}"))


# ----------------------------------------------------------------- loans
@mcp.tool()
def get_loans(customer_id: str) -> str:
    """The customer's loans: type, EMI, outstanding principal, rate, next due date."""
    return _json(query(
        "SELECT loan_id, loan_type, principal, interest_rate, tenure_months, emi, outstanding, start_date,"
        " next_due_date, status FROM loans WHERE customer_id = ?", (customer_id,)))


@mcp.tool()
def get_loan_products(customer_id: str) -> str:
    """Loan products on offer: indicative rate, maximum tenure, minimum credit score, maximum amount."""
    return _json(query("SELECT * FROM loan_products"))


@mcp.tool()
def calculate_emi(customer_id: str, principal: float, annual_interest_rate: float, tenure_months: int) -> str:
    """EMI, total interest and total repayment for a loan."""
    return _json({"principal": principal, "annual_interest_rate": annual_interest_rate,
                  "tenure_months": tenure_months, **finance.emi(principal, annual_interest_rate, tenure_months)})


@mcp.tool()
def check_loan_eligibility(customer_id: str, loan_type: str, requested_amount: float, tenure_months: int) -> str:
    """Indicative eligibility for a new loan (personal, home, car, education) using income,
    existing EMIs (50% FOIR cap), credit score and KYC status. Not a sanction."""
    product = query_one("SELECT * FROM loan_products WHERE loan_type = ?", (loan_type.lower(),))
    if product is None:
        raise ValueError("loan_type must be one of: personal, home, car, education")
    cust = query_one("SELECT monthly_income, credit_score, kyc_status FROM customers WHERE customer_id = ?",
                     (customer_id,))
    existing = query_one("SELECT COALESCE(SUM(emi), 0) AS total FROM loans WHERE customer_id = ? AND status = 'active'",
                         (customer_id,))["total"]
    tenure = min(tenure_months, product["max_tenure_months"])
    room = 0.5 * cust["monthly_income"] - existing
    max_amount = min(finance.max_principal_for_emi(room, product["interest_rate"], tenure), product["max_amount"])
    reasons = []
    if cust["kyc_status"] != "verified":
        reasons.append("KYC is not verified")
    if cust["credit_score"] < product["min_credit_score"]:
        reasons.append(f"credit score {cust['credit_score']} is below the minimum {product['min_credit_score']}")
    if requested_amount > max_amount:
        reasons.append(f"requested amount exceeds the indicative maximum of {max_amount:,.0f}")
    return _json({
        "loan_type": product["loan_type"], "indicative_rate": product["interest_rate"], "tenure_months": tenure,
        "requested_amount": requested_amount, "existing_monthly_emi": round(existing, 2),
        "emi_capacity_remaining": round(max(room, 0), 2), "max_eligible_amount": max(max_amount, 0),
        "eligible": not reasons, "reasons": reasons,
        "emi_for_requested_amount": finance.emi(requested_amount, product["interest_rate"], tenure)["emi"],
        "disclaimer": "Indicative only; final sanction is subject to underwriting and document verification.",
    })


# ----------------------------------------------------------------- insurance
@mcp.tool()
def get_insurance_policies(customer_id: str) -> str:
    """The customer's insurance policies: type, plan, cover, premium, next premium date, nominee, status."""
    policies = query(
        "SELECT policy_id, policy_type, plan_name, sum_assured, premium, premium_frequency, start_date,"
        " next_premium_date, nominee, status FROM insurance_policies WHERE customer_id = ?", (customer_id,))
    for p in policies:
        p["days_to_next_premium"] = (date.fromisoformat(p["next_premium_date"]) - date.today()).days
    return _json(policies)


# ----------------------------------------------------------------- fraud
@mcp.tool()
def scan_suspicious_transactions(customer_id: str, days: int = 30) -> str:
    """Rule-based fraud scan over recent debits. Flags unusually large amounts, activity
    outside the customer's home city, and duplicate charges on the same day."""
    home = query_one("SELECT city FROM customers WHERE customer_id = ?", (customer_id,))["city"]
    txns = query(
        "SELECT txn_id, txn_date, description, merchant, amount, channel, city, account_id, card_id"
        " FROM transactions WHERE customer_id = ? AND txn_type = 'debit' AND txn_date >= ?",
        (customer_id, (date.today() - timedelta(days=max(1, days))).isoformat()))
    if not txns:
        return _json({"flagged": [], "scanned": 0})
    threshold = 5 * statistics.median(t["amount"] for t in txns)
    seen: dict[tuple, int] = {}
    for t in txns:
        key = (t["txn_date"], t["merchant"], t["amount"])
        seen[key] = seen.get(key, 0) + 1
    flagged = []
    for t in txns:
        reasons = []
        if t["amount"] > threshold:
            reasons.append("amount far above the customer's usual spend")
        if t["city"] and t["city"] != home:
            reasons.append(f"location {t['city']} differs from home city {home}")
        if seen[(t["txn_date"], t["merchant"], t["amount"])] > 1:
            reasons.append("duplicate charge on the same day")
        if reasons:
            flagged.append({**t, "reasons": reasons})
    return _json({"flagged": flagged, "scanned": len(txns)})


# ----------------------------------------------------------------- support
@mcp.tool()
def create_support_ticket(customer_id: str, category: str, subject: str, description: str) -> str:
    """Raise a service request or complaint. category: card, account, deposit, loan, insurance,
    fraud or other. Returns the ticket number."""
    ticket_id = execute(
        "INSERT INTO support_tickets (customer_id, category, subject, description, status, created_at)"
        " VALUES (?,?,?,?, 'open', ?)",
        (customer_id, category.lower(), subject, description, datetime.now().isoformat(timespec="seconds")))
    return _json({"ticket_id": ticket_id, "status": "open", "expected_resolution": "within 7 working days"})


@mcp.tool()
def get_support_tickets(customer_id: str) -> str:
    """The customer's support tickets and their status, newest first."""
    return _json(query(
        "SELECT ticket_id, category, subject, status, created_at FROM support_tickets"
        " WHERE customer_id = ? ORDER BY ticket_id DESC", (customer_id,)))


# ----------------------------------------------------------------- analytics (text-to-SQL)
@mcp.tool()
def run_analytics_sql(customer_id: str, sql: str) -> str:
    """Run one read-only SQLite SELECT over this customer's own data (sandboxed copy).
    Tables: accounts, credit_cards, transactions, fixed_deposits, recurring_deposits,
    loans, insurance_policies. Returns at most 50 rows."""
    return _json(analytics.run_sandboxed(customer_id, sql))


def main() -> None:
    init_db()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
