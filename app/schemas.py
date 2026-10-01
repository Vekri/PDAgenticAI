"""Application and decision records."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LoanApplication(BaseModel):
    """One business loan file assembled from the five source systems."""

    model_config = ConfigDict(extra="forbid")

    business_name: str
    industry: str
    years_in_business: int = Field(ge=0, le=200)
    loan_amount: float = Field(gt=0)
    loan_purpose: str
    loan_term_years: int = Field(ge=1, le=30)
    interest_rate_pct: float = Field(ge=0, le=40)
    revenue: float
    ebitda: float
    interest_expense: float = 0
    net_income: float = 0
    current_assets: float
    current_liabilities: float
    cash: float = 0
    receivables: float = 0
    total_assets: float
    existing_debt: float = Field(ge=0)
    equity: float
    existing_annual_debt_service: float = Field(ge=0)
    credit_score: int
    delinquencies_12m: int = Field(ge=0)
    bankruptcy: bool = False
    relationship_years: int = Field(ge=0)
    deposit_balance: float = 0
    prior_loans_current: bool = True
    revenue_growth: float = Field(description="Decimal growth. 0.05 means 5 percent.")
    industry_outlook: str = "Stable"
    analyst_request: str = "Analyze this business loan application and assess the risk."


class PolicyCheck(BaseModel):
    code: str
    level: str
    passed: bool
    section: str
    message: str


class Evidence(BaseModel):
    source: str
    section: str
    title: str
    excerpt: str
    score: float | None = None
    origin: str


class DecisionResult(BaseModel):
    run_id: str
    created_at: str
    recommendation: str
    pd_score: float | None
    pd_display: str
    risk_grade: str | None
    key_ratios: dict
    why: list[str]
    explanation: str
    explanation_source: str
    metrics: dict
    drivers: list[dict]
    policy_checks: list[dict]
    policy_evidence: list[dict]
    agents: list[dict]
    audit: list[dict]
    ml_pd: float | None
    ml_backend: str
    warnings: list[str]
    errors: list[str]
    application: dict
    elapsed_ms: int
    path: list[str]
    application_id: str | None = None
    deployment_id: str | None = None
    app_version: str = ""
    pipeline_version: str = ""
    policy_version: str = ""
    scorecard_version: str = ""
    ml_model_version: str = ""
    rag_corpus_version: str = ""
