"""Two-step writes.

Agents can only *propose* money-moving or account-changing operations. A proposal
is stored in `pending_actions`; it executes only when the customer confirms it
through POST /actions/{id}/confirm. The LLM is never in the confirmation path.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from app import finance
from app.db.database import connect, query, query_one


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def propose(customer_id: str, action_type: str, payload: dict, summary: str) -> dict:
    with connect() as conn:
        action_id = conn.execute(
            "INSERT INTO pending_actions (customer_id, action_type, payload, summary, status, created_at)"
            " VALUES (?,?,?,?, 'pending', ?)",
            (customer_id, action_type, json.dumps(payload), summary, _now()),
        ).lastrowid
    return {
        "action_id": action_id,
        "status": "pending_customer_confirmation",
        "summary": summary,
        "note": "Nothing has been executed. The customer must confirm this action in the app.",
    }


def list_pending(customer_id: str) -> list[dict]:
    return query(
        "SELECT action_id, action_type, summary, created_at FROM pending_actions"
        " WHERE customer_id = ? AND status = 'pending' ORDER BY action_id",
        (customer_id,),
    )


def _add_months(start: date, months: int) -> date:
    y, m = divmod(start.month - 1 + months, 12)
    return date(start.year + y, m + 1, min(start.day, 28))


def _next_id(conn, table: str, column: str, prefix: str) -> str:
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    while True:
        n += 1
        candidate = f"{prefix}{9000 + n}"
        if not conn.execute(f"SELECT 1 FROM {table} WHERE {column} = ?", (candidate,)).fetchone():
            return candidate


def resolve(customer_id: str, action_id: int, approve: bool) -> dict:
    """Execute (or cancel) a pending action. Raises LookupError / ValueError."""
    row = query_one(
        "SELECT * FROM pending_actions WHERE action_id = ? AND customer_id = ?", (action_id, customer_id)
    )
    if row is None:
        raise LookupError("action not found for this customer")
    if row["status"] != "pending":
        raise ValueError(f"action already {row['status']}")

    result: dict = {}
    with connect() as conn:  # one transaction: execute + mark resolved
        if approve:
            p = json.loads(row["payload"])
            kind = row["action_type"]
            today = date.today()
            if kind in ("open_fd", "open_rd"):
                first = p["principal"] if kind == "open_fd" else p["monthly_installment"]
                acct = conn.execute(
                    "SELECT balance FROM accounts WHERE account_id = ? AND customer_id = ?",
                    (p["source_account_id"], customer_id),
                ).fetchone()
                if acct is None or acct["balance"] < first:
                    raise ValueError("insufficient balance in the source account")
                conn.execute(
                    "UPDATE accounts SET balance = balance - ? WHERE account_id = ?", (first, p["source_account_id"])
                )
                maturity = _add_months(today, p["tenure_months"]).isoformat()
                if kind == "open_fd":
                    new_id = _next_id(conn, "fixed_deposits", "fd_id", "FD")
                    amount = finance.fd_maturity(first, p["interest_rate"], p["tenure_months"])["maturity_amount"]
                    conn.execute(
                        "INSERT INTO fixed_deposits VALUES (?,?,?,?,?,?,?,?, 'active')",
                        (new_id, customer_id, first, p["interest_rate"], p["tenure_months"], today.isoformat(), maturity, amount),
                    )
                else:
                    new_id = _next_id(conn, "recurring_deposits", "rd_id", "RD")
                    amount = finance.rd_maturity(first, p["interest_rate"], p["tenure_months"])["maturity_amount"]
                    conn.execute(
                        "INSERT INTO recurring_deposits VALUES (?,?,?,?,?,1,?,?,?, 'active')",
                        (new_id, customer_id, first, p["interest_rate"], p["tenure_months"], today.isoformat(), maturity, amount),
                    )
                conn.execute(
                    "INSERT INTO transactions (customer_id, account_id, txn_date, description, merchant, category,"
                    " amount, txn_type, channel, city) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (customer_id, p["source_account_id"], today.isoformat(), f"Transfer to {new_id}", "Anil Bank",
                     "investment", first, "debit", "internal", ""),
                )
                result = {"created": new_id, "maturity_date": maturity, "maturity_amount": amount}
            elif kind == "block_card":
                updated = conn.execute(
                    "UPDATE credit_cards SET status = 'blocked' WHERE card_id = ? AND customer_id = ?",
                    (p["card_id"], customer_id),
                ).rowcount
                if not updated:
                    raise ValueError("card not found")
                result = {"card_id": p["card_id"], "status": "blocked"}
            else:
                raise ValueError(f"unknown action type {kind}")
        conn.execute(
            "UPDATE pending_actions SET status = ?, resolved_at = ? WHERE action_id = ?",
            ("executed" if approve else "cancelled", _now(), action_id),
        )
    return {"action_id": action_id, "status": "executed" if approve else "cancelled", "result": result}
