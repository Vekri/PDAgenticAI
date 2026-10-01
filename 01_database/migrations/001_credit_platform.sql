CREATE SCHEMA IF NOT EXISTS credit;

CREATE TABLE IF NOT EXISTS credit.schema_migration (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS credit.deployment (
    deployment_id TEXT PRIMARY KEY,
    environment TEXT NOT NULL,
    app_version TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    scorecard_version TEXT NOT NULL,
    ml_model_version TEXT NOT NULL,
    rag_corpus_version TEXT NOT NULL,
    deployed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS credit.loan_application (
    application_id TEXT PRIMARY KEY,
    business_name TEXT NOT NULL,
    industry TEXT NOT NULL,
    years_in_business INTEGER NOT NULL,
    loan_amount NUMERIC(18, 2) NOT NULL,
    loan_purpose TEXT NOT NULL,
    loan_term_years INTEGER NOT NULL,
    interest_rate_pct NUMERIC(8, 4) NOT NULL,
    analyst_request TEXT NOT NULL,
    source_system TEXT NOT NULL DEFAULT 'origination',
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS credit.financial_statement (
    application_id TEXT PRIMARY KEY REFERENCES credit.loan_application (application_id) ON DELETE CASCADE,
    revenue NUMERIC(18, 2) NOT NULL,
    ebitda NUMERIC(18, 2) NOT NULL,
    interest_expense NUMERIC(18, 2) NOT NULL,
    net_income NUMERIC(18, 2) NOT NULL,
    current_assets NUMERIC(18, 2) NOT NULL,
    current_liabilities NUMERIC(18, 2) NOT NULL,
    cash NUMERIC(18, 2) NOT NULL,
    receivables NUMERIC(18, 2) NOT NULL,
    total_assets NUMERIC(18, 2) NOT NULL,
    existing_debt NUMERIC(18, 2) NOT NULL,
    equity NUMERIC(18, 2) NOT NULL,
    existing_annual_debt_service NUMERIC(18, 2) NOT NULL,
    statement_period TEXT NOT NULL DEFAULT 'FY-latest'
);

CREATE TABLE IF NOT EXISTS credit.credit_bureau (
    application_id TEXT PRIMARY KEY REFERENCES credit.loan_application (application_id) ON DELETE CASCADE,
    credit_score INTEGER NOT NULL,
    delinquencies_12m INTEGER NOT NULL,
    bankruptcy BOOLEAN NOT NULL,
    bureau_name TEXT NOT NULL DEFAULT 'commercial-bureau',
    pulled_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS credit.bank_relationship (
    application_id TEXT PRIMARY KEY REFERENCES credit.loan_application (application_id) ON DELETE CASCADE,
    relationship_years INTEGER NOT NULL,
    deposit_balance NUMERIC(18, 2) NOT NULL,
    prior_loans_current BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS credit.market_observation (
    application_id TEXT PRIMARY KEY REFERENCES credit.loan_application (application_id) ON DELETE CASCADE,
    revenue_growth NUMERIC(8, 4) NOT NULL,
    industry_outlook TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS credit.feature_record (
    run_id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES credit.loan_application (application_id),
    deployment_id TEXT NOT NULL REFERENCES credit.deployment (deployment_id),
    built_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS credit.decision (
    run_id TEXT PRIMARY KEY REFERENCES credit.feature_record (run_id),
    application_id TEXT NOT NULL REFERENCES credit.loan_application (application_id),
    deployment_id TEXT NOT NULL REFERENCES credit.deployment (deployment_id),
    recommendation TEXT NOT NULL CHECK (recommendation IN ('APPROVE', 'REVIEW', 'REJECT')),
    pd_score NUMERIC(12, 8),
    pd_display TEXT NOT NULL,
    risk_grade TEXT,
    ml_pd NUMERIC(12, 8),
    ml_backend TEXT NOT NULL,
    debt_to_ebitda NUMERIC(12, 6),
    dscr NUMERIC(12, 6),
    credit_score INTEGER,
    explanation TEXT NOT NULL,
    explanation_source TEXT NOT NULL,
    why_json JSONB NOT NULL,
    metrics_json JSONB NOT NULL,
    drivers_json JSONB NOT NULL,
    elapsed_ms INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS credit.decision_check (
    run_id TEXT NOT NULL REFERENCES credit.decision (run_id) ON DELETE CASCADE,
    check_order INTEGER NOT NULL,
    code TEXT NOT NULL,
    level TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    section TEXT NOT NULL,
    message TEXT NOT NULL,
    PRIMARY KEY (run_id, check_order)
);

CREATE TABLE IF NOT EXISTS credit.decision_evidence (
    run_id TEXT NOT NULL REFERENCES credit.decision (run_id) ON DELETE CASCADE,
    evidence_order INTEGER NOT NULL,
    source TEXT NOT NULL,
    section TEXT NOT NULL,
    title TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    score NUMERIC(8, 4),
    origin TEXT NOT NULL,
    PRIMARY KEY (run_id, evidence_order)
);

CREATE TABLE IF NOT EXISTS credit.decision_audit (
    run_id TEXT NOT NULL REFERENCES credit.decision (run_id) ON DELETE CASCADE,
    step INTEGER NOT NULL,
    name TEXT NOT NULL,
    short_name TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (run_id, step)
);

CREATE INDEX IF NOT EXISTS decision_application_idx ON credit.decision (application_id, created_at DESC);

CREATE OR REPLACE VIEW credit.latest_decision AS
SELECT DISTINCT ON (application_id)
    run_id,
    application_id,
    deployment_id,
    recommendation,
    pd_score,
    pd_display,
    risk_grade,
    debt_to_ebitda,
    dscr,
    credit_score,
    created_at
FROM credit.decision
ORDER BY application_id, created_at DESC;
