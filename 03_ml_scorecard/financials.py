"""Financial ratios used by policy and the PD scorecard.

DSCR is EBITDA divided by existing annual debt service plus the proposed
facility's annual payment. Debt/EBITDA uses pro forma debt, which includes
the new loan. The new payment is a standard monthly amortization.
"""

from __future__ import annotations

from app.schemas import LoanApplication


def proposed_annual_payment(principal: float, annual_rate_pct: float, term_years: int) -> float:
    if principal <= 0 or term_years <= 0:
        return 0.0
    monthly_rate = (annual_rate_pct / 100.0) / 12.0
    periods = term_years * 12
    if monthly_rate == 0:
        return principal / term_years
    factor = monthly_rate * (1 + monthly_rate) ** periods
    factor = factor / ((1 + monthly_rate) ** periods - 1)
    return factor * principal * 12


def safe_div(numerator: float, denominator: float) -> float | None:
    if denominator is None or denominator == 0:
        return None
    return numerator / denominator


def calculate_metrics(app: LoanApplication) -> dict:
    payment = proposed_annual_payment(app.loan_amount, app.interest_rate_pct, app.loan_term_years)
    pro_forma_debt = app.existing_debt + app.loan_amount
    pro_forma_service = app.existing_annual_debt_service + payment
    ebitda = app.ebitda
    return {
        "revenue": app.revenue,
        "ebitda": ebitda,
        "ebitda_margin": safe_div(ebitda, app.revenue),
        "pro_forma_debt": pro_forma_debt,
        "debt_to_ebitda": safe_div(pro_forma_debt, ebitda) if ebitda > 0 else None,
        "existing_annual_debt_service": app.existing_annual_debt_service,
        "proposed_annual_payment": payment,
        "pro_forma_debt_service": pro_forma_service,
        "dscr": safe_div(ebitda, pro_forma_service) if ebitda > 0 else None,
        "current_ratio": safe_div(app.current_assets, app.current_liabilities),
        "quick_ratio": safe_div(app.cash + app.receivables, app.current_liabilities),
        "interest_coverage": safe_div(ebitda, app.interest_expense) if ebitda > 0 and app.interest_expense > 0 else None,
        "debt_to_equity": safe_div(pro_forma_debt, app.equity) if app.equity > 0 else None,
        "loan_to_ebitda": safe_div(app.loan_amount, ebitda) if ebitda > 0 else None,
        "net_income": app.net_income,
        "credit_score": app.credit_score,
    }
