CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT, phone TEXT, date_of_birth TEXT, city TEXT,
    kyc_status TEXT, employment_type TEXT,
    monthly_income REAL, credit_score INTEGER
);
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    account_type TEXT, balance REAL, branch TEXT, status TEXT, opened_on TEXT
);
CREATE TABLE IF NOT EXISTS credit_cards (
    card_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    card_name TEXT, last4 TEXT, credit_limit REAL, outstanding REAL,
    minimum_due REAL, due_date TEXT, reward_points INTEGER, status TEXT
);
CREATE TABLE IF NOT EXISTS transactions (
    txn_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    account_id TEXT, card_id TEXT,            -- exactly one of these is set
    txn_date TEXT, description TEXT, merchant TEXT, category TEXT,
    amount REAL, txn_type TEXT,               -- 'debit' | 'credit'
    channel TEXT, city TEXT
);
CREATE TABLE IF NOT EXISTS fixed_deposits (
    fd_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    principal REAL, interest_rate REAL, tenure_months INTEGER,
    start_date TEXT, maturity_date TEXT, maturity_amount REAL, status TEXT
);
CREATE TABLE IF NOT EXISTS recurring_deposits (
    rd_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    monthly_installment REAL, interest_rate REAL, tenure_months INTEGER,
    installments_paid INTEGER, start_date TEXT, maturity_date TEXT,
    maturity_amount REAL, status TEXT
);
CREATE TABLE IF NOT EXISTS loans (
    loan_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    loan_type TEXT, principal REAL, interest_rate REAL, tenure_months INTEGER,
    emi REAL, outstanding REAL, start_date TEXT, next_due_date TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS insurance_policies (
    policy_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    policy_type TEXT, plan_name TEXT, sum_assured REAL, premium REAL,
    premium_frequency TEXT, start_date TEXT, next_premium_date TEXT,
    nominee TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS support_tickets (
    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    category TEXT, subject TEXT, description TEXT, status TEXT, created_at TEXT
);
-- Writes proposed by agents. Nothing here takes effect until the customer
-- confirms it through the API (never through the LLM).
CREATE TABLE IF NOT EXISTS pending_actions (
    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    action_type TEXT, payload TEXT, summary TEXT,
    status TEXT, created_at TEXT, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS fd_rates (
    min_months INTEGER, max_months INTEGER, regular_rate REAL, senior_rate REAL
);
CREATE TABLE IF NOT EXISTS loan_products (
    loan_type TEXT PRIMARY KEY, interest_rate REAL, max_tenure_months INTEGER,
    min_credit_score INTEGER, max_amount REAL
);
CREATE INDEX IF NOT EXISTS idx_txn_customer ON transactions(customer_id, txn_date);
