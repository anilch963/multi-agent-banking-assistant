"""Create the schema and load deterministic demo data.

    python -m app.db.seed          # create if missing
    python -m app.db.seed --force  # wipe and recreate
"""
from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

from app import config, finance
from app.db.database import connect

SCHEMA = Path(__file__).with_name("schema.sql")
TODAY = date.today()


def d(days: int) -> str:
    """ISO date offset from today (negative = past)."""
    return (TODAY + timedelta(days=days)).isoformat()


CUSTOMERS = [
    ("C001", "Aarav Mehta", "aarav.mehta@example.com", "+91-90000-00001", "1990-04-12", "Bengaluru", "verified", "salaried", 145000, 782),
    ("C002", "Priya Nair", "priya.nair@example.com", "+91-90000-00002", "1985-11-03", "Kochi", "verified", "self_employed", 210000, 731),
    ("C003", "Rohan Gupta", "rohan.gupta@example.com", "+91-90000-00003", "1998-07-25", "Pune", "pending", "salaried", 62000, 668),
]
ACCOUNTS = [
    ("SB1001", "C001", "savings", 384250.75, "Indiranagar", "active", "2017-06-01"),
    ("CA1002", "C001", "current", 92000.00, "Indiranagar", "active", "2021-02-15"),
    ("SB2001", "C002", "savings", 1275400.10, "MG Road Kochi", "active", "2012-09-20"),
    ("SB3001", "C003", "savings", 41890.40, "Kothrud", "active", "2022-01-10"),
]
CARDS = [
    ("CC1001", "C001", "Anil Platinum Rewards", "4421", 300000, 68450.00, 3422.50, d(9), 18450, "active"),
    ("CC1002", "C001", "Anil Travel Elite", "7730", 500000, 12999.00, 650.00, d(16), 42100, "active"),
    ("CC2001", "C002", "Anil Business Signature", "1188", 800000, 245300.00, 12265.00, d(5), 96500, "active"),
    ("CC3001", "C003", "Anil Starter Cashback", "9056", 60000, 21750.00, 1087.50, d(12), 1320, "active"),
]
FDS = [  # id, customer, principal, rate, tenure, started N days ago
    ("FD1001", "C001", 500000, 7.10, 24, -200),
    ("FD1002", "C001", 200000, 6.75, 12, -320),
    ("FD2001", "C002", 1500000, 7.25, 36, -400),
]
RDS = [  # id, customer, installment, rate, tenure, installments paid
    ("RD1001", "C001", 10000, 6.90, 36, 14),
    ("RD3001", "C003", 3000, 6.75, 12, 5),
]
LOANS = [  # id, customer, type, principal, rate, tenure, months elapsed
    ("LN1001", "C001", "home", 4500000, 8.60, 240, 38),
    ("LN2001", "C002", "car", 1200000, 9.25, 60, 22),
    ("LN3001", "C003", "personal", 250000, 13.50, 36, 9),
]
POLICIES = [
    ("IN1001", "C001", "term_life", "Anil Secure Term", 10000000, 14800, "yearly", "2021-08-01", d(75), "Spouse", "active"),
    ("IN1002", "C001", "health", "Anil Health Shield Family", 1000000, 22400, "yearly", "2022-03-10", d(118), "Spouse", "active"),
    ("IN2001", "C002", "motor", "Anil Drive Protect", 900000, 18650, "yearly", "2025-01-05", d(40), "Self", "active"),
    ("IN3001", "C003", "health", "Anil Health Shield Individual", 500000, 8900, "yearly", "2024-06-18", d(-6), "Mother", "grace_period"),
]
# min_months, max_months, regular %, senior-citizen %
FD_RATES = [(1, 5, 6.00, 6.50), (6, 11, 6.50, 7.00), (12, 23, 6.75, 7.25), (24, 35, 7.10, 7.60), (36, 120, 7.25, 7.75)]
LOAN_PRODUCTS = [
    ("personal", 13.50, 60, 700, 2500000),
    ("home", 8.60, 360, 700, 50000000),
    ("car", 9.25, 84, 680, 5000000),
    ("education", 10.50, 180, 650, 7500000),
]

SPEND = [  # merchant, category, min, max
    ("BigBasket", "groceries", 600, 4500), ("Swiggy", "dining", 250, 1400),
    ("Zomato", "dining", 200, 1600), ("Amazon", "shopping", 400, 9000),
    ("Indian Oil", "fuel", 800, 3500), ("BESCOM", "utilities", 1200, 3800),
    ("Airtel", "utilities", 499, 1499), ("Netflix", "entertainment", 199, 649),
    ("Uber", "transport", 120, 900), ("Apollo Pharmacy", "health", 150, 2600),
    ("MakeMyTrip", "travel", 3500, 28000), ("Myntra", "shopping", 700, 6500),
]


def _add_months(start: date, months: int) -> date:
    y, m = divmod(start.month - 1 + months, 12)
    return date(start.year + y, m + 1, min(start.day, 28))


def _transactions(rng: random.Random) -> list[tuple]:
    rows: list[tuple] = []
    plan = {"C001": ("SB1001", "CC1001", 145000), "C002": ("SB2001", "CC2001", 210000), "C003": ("SB3001", "CC3001", 62000)}
    home = {c[0]: c[5] for c in CUSTOMERS}
    for cid, (acct, card, income) in plan.items():
        for month in range(3):  # salary credits
            rows.append((cid, acct, None, d(-month * 30 - 3), "Salary credit", "Employer", "income", income, "credit", "neft", home[cid]))
        for _ in range(45):
            merchant, category, lo, hi = rng.choice(SPEND)
            on_card = rng.random() < 0.55
            rows.append((
                cid, None if on_card else acct, card if on_card else None, d(-rng.randint(0, 89)),
                f"{merchant} purchase", merchant, category, round(rng.uniform(lo, hi), 2), "debit",
                "card" if on_card else rng.choice(["upi", "netbanking"]), home[cid],
            ))
    # Deliberately suspicious activity on Aarav's Platinum card for the fraud agent.
    rows += [
        ("C001", None, "CC1001", d(-1), "LUXE ELECTRONICS intl purchase", "Luxe Electronics", "shopping", 84999.00, "debit", "card_online", "Singapore"),
        ("C001", None, "CC1001", d(-1), "LUXE ELECTRONICS intl purchase", "Luxe Electronics", "shopping", 84999.00, "debit", "card_online", "Singapore"),
        ("C001", None, "CC1001", d(-2), "GAMEPORT top-up", "Gameport", "entertainment", 49500.00, "debit", "card_online", "Lagos"),
    ]
    return rows


def init_db(force: bool = False) -> bool:
    """Create and seed the database. Returns True if data was (re)loaded."""
    if force and config.DB_PATH.exists():
        config.DB_PATH.unlink()
    with connect() as conn:
        conn.executescript(SCHEMA.read_text())
        if conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]:
            return False
        rng = random.Random(42)
        conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?,?)", CUSTOMERS)
        conn.executemany("INSERT INTO accounts VALUES (?,?,?,?,?,?,?)", ACCOUNTS)
        conn.executemany("INSERT INTO credit_cards VALUES (?,?,?,?,?,?,?,?,?,?)", CARDS)
        conn.executemany(
            "INSERT INTO transactions (customer_id, account_id, card_id, txn_date, description, merchant,"
            " category, amount, txn_type, channel, city) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            _transactions(rng),
        )
        for fd_id, cid, principal, rate, tenure, started in FDS:
            start = TODAY + timedelta(days=started)
            conn.execute(
                "INSERT INTO fixed_deposits VALUES (?,?,?,?,?,?,?,?,?)",
                (fd_id, cid, principal, rate, tenure, start.isoformat(), _add_months(start, tenure).isoformat(),
                 finance.fd_maturity(principal, rate, tenure)["maturity_amount"], "active"),
            )
        for rd_id, cid, inst, rate, tenure, paid in RDS:
            start = _add_months(TODAY, -paid)
            conn.execute(
                "INSERT INTO recurring_deposits VALUES (?,?,?,?,?,?,?,?,?,?)",
                (rd_id, cid, inst, rate, tenure, paid, start.isoformat(), _add_months(start, tenure).isoformat(),
                 finance.rd_maturity(inst, rate, tenure)["maturity_amount"], "active"),
            )
        for loan_id, cid, ltype, principal, rate, tenure, elapsed in LOANS:
            monthly = finance.emi(principal, rate, tenure)["emi"]
            r = rate / 1200
            outstanding = principal * (1 + r) ** elapsed - monthly * ((1 + r) ** elapsed - 1) / r
            conn.execute(
                "INSERT INTO loans VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (loan_id, cid, ltype, principal, rate, tenure, monthly, round(outstanding, 2),
                 _add_months(TODAY, -elapsed).isoformat(), d(7), "active"),
            )
        conn.executemany("INSERT INTO insurance_policies VALUES (?,?,?,?,?,?,?,?,?,?,?)", POLICIES)
        conn.executemany("INSERT INTO fd_rates VALUES (?,?,?,?)", FD_RATES)
        conn.executemany("INSERT INTO loan_products VALUES (?,?,?,?,?)", LOAN_PRODUCTS)
    return True


if __name__ == "__main__":
    loaded = init_db(force="--force" in sys.argv)
    print(f"Database at {config.DB_PATH} - {'seeded' if loaded else 'already populated'}")
