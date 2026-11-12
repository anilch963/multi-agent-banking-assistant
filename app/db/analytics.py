"""Sandboxed text-to-SQL for the analytics agent.

The LLM writes SQL, so the query never touches the real database. We copy only
the calling customer's rows into a throw-away in-memory SQLite database and run
the query there: other customers' data is not merely filtered out, it is absent.
"""
from __future__ import annotations

import sqlite3

from app.db.database import connect

TABLES = [
    "accounts", "credit_cards", "transactions", "fixed_deposits",
    "recurring_deposits", "loans", "insurance_policies",
]
MAX_ROWS = 50
MAX_VM_STEPS = 2_000_000

SCHEMA_HINT = """\
accounts(account_id, account_type, balance, branch, status, opened_on)
credit_cards(card_id, card_name, last4, credit_limit, outstanding, minimum_due, due_date, reward_points, status)
transactions(txn_id, account_id, card_id, txn_date 'YYYY-MM-DD', description, merchant,
             category [groceries|dining|shopping|fuel|utilities|entertainment|transport|health|travel|income|investment],
             amount, txn_type ['debit'|'credit'], channel, city)
fixed_deposits(fd_id, principal, interest_rate, tenure_months, start_date, maturity_date, maturity_amount, status)
recurring_deposits(rd_id, monthly_installment, interest_rate, tenure_months, installments_paid, start_date, maturity_date, maturity_amount, status)
loans(loan_id, loan_type, principal, interest_rate, tenure_months, emi, outstanding, start_date, next_due_date, status)
insurance_policies(policy_id, policy_type, plan_name, sum_assured, premium, premium_frequency, start_date, next_premium_date, nominee, status)"""


def run_sandboxed(customer_id: str, sql: str) -> dict:
    statement = sql.strip().rstrip(";").strip()
    if ";" in statement:
        raise ValueError("only a single statement is allowed")
    if not statement.lower().startswith(("select", "with")):
        raise ValueError("only SELECT queries are allowed")

    sandbox = sqlite3.connect(":memory:")
    try:
        with connect() as src:
            for table in TABLES:
                rows = src.execute(f"SELECT * FROM {table} WHERE customer_id = ?", (customer_id,)).fetchall()
                cols = [c[1] for c in src.execute(f"PRAGMA table_info({table})")]
                sandbox.execute(f"CREATE TABLE {table} ({', '.join(cols)})")
                if rows:
                    sandbox.executemany(
                        f"INSERT INTO {table} VALUES ({', '.join('?' * len(cols))})", [tuple(r) for r in rows]
                    )
        sandbox.commit()
        steps = {"n": 0}

        def guard() -> int:  # abort runaway queries
            steps["n"] += 1000
            return 1 if steps["n"] > MAX_VM_STEPS else 0

        sandbox.set_progress_handler(guard, 1000)
        cur = sandbox.execute(statement)
        columns = [c[0] for c in cur.description or []]
        rows = cur.fetchmany(MAX_ROWS + 1)
        return {
            "columns": columns,
            "rows": [list(r) for r in rows[:MAX_ROWS]],
            "truncated": len(rows) > MAX_ROWS,
        }
    finally:
        sandbox.close()
