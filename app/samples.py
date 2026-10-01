"""Three filed examples: approve, review, and decline.

Existing debt service is back-solved so DSCR lands on the case target after
the new loan payment is added. Pro forma debt is existing debt plus the
proposed loan.
"""

from __future__ import annotations

from app.financials import proposed_annual_payment
from app.schemas import LoanApplication

SAMPLE_CATALOG = [
    {
        "id": "apex",
        "business": "Apex Manufacturing Co.",
        "expectation": "APPROVE",
        "note": "PD 3.8%, Debt/EBITDA 2.0x, DSCR 1.62, score 720",
    },
    {
        "id": "harbor",
        "business": "Harbor Logistics LLC",
        "expectation": "REVIEW",
        "note": "PD above 5%, ratios still inside hard stops",
    },
    {
        "id": "northwind",
        "business": "Northwind Retail Inc.",
        "expectation": "REJECT",
        "note": "Score, leverage, and DSCR breach hard stops",
    },
]


def _service_for_target(ebitda: float, loan: float, rate: float, term: int, target_dscr: float) -> float:
    payment = proposed_annual_payment(loan, rate, term)
    return ebitda / target_dscr - payment


def apex() -> LoanApplication:
    ebitda = 1_200_000.0
    loan = 1_200_000.0
    rate = 8.0
    term = 5
    return LoanApplication(
        business_name="Apex Manufacturing Co.",
        industry="Manufacturing",
        years_in_business=10,
        loan_amount=loan,
        loan_purpose="Equipment and working capital",
        loan_term_years=term,
        interest_rate_pct=rate,
        revenue=8_500_000,
        ebitda=ebitda,
        interest_expense=180_000,
        net_income=640_000,
        current_assets=2_160_000,
        current_liabilities=1_200_000,
        cash=480_000,
        receivables=900_000,
        total_assets=6_500_000,
        existing_debt=1_200_000,
        equity=3_400_000,
        existing_annual_debt_service=_service_for_target(ebitda, loan, rate, term, 1.62),
        credit_score=720,
        delinquencies_12m=0,
        bankruptcy=False,
        relationship_years=6,
        deposit_balance=850_000,
        prior_loans_current=True,
        revenue_growth=0.05,
        industry_outlook="Stable",
        analyst_request="Analyze this business loan application and assess the risk.",
    )


def harbor() -> LoanApplication:
    ebitda = 900_000.0
    loan = 500_000.0
    rate = 8.0
    term = 5
    return LoanApplication(
        business_name="Harbor Logistics LLC",
        industry="Logistics",
        years_in_business=10,
        loan_amount=loan,
        loan_purpose="Fleet and warehouse fit-out",
        loan_term_years=term,
        interest_rate_pct=rate,
        revenue=6_400_000,
        ebitda=ebitda,
        interest_expense=200_000,
        net_income=210_000,
        current_assets=1_800_000,
        current_liabilities=1_000_000,
        cash=260_000,
        receivables=640_000,
        total_assets=4_800_000,
        existing_debt=1_930_000,
        equity=1_700_000,
        existing_annual_debt_service=_service_for_target(ebitda, loan, rate, term, 1.50),
        credit_score=705,
        delinquencies_12m=0,
        bankruptcy=False,
        relationship_years=4,
        deposit_balance=310_000,
        prior_loans_current=True,
        revenue_growth=0.05,
        industry_outlook="Stable",
        analyst_request="Analyze this business loan application and assess the risk.",
    )


def northwind() -> LoanApplication:
    ebitda = 500_000.0
    loan = 600_000.0
    rate = 9.5
    term = 5
    return LoanApplication(
        business_name="Northwind Retail Inc.",
        industry="Retail",
        years_in_business=4,
        loan_amount=loan,
        loan_purpose="Refinance and inventory",
        loan_term_years=term,
        interest_rate_pct=rate,
        revenue=3_100_000,
        ebitda=ebitda,
        interest_expense=160_000,
        net_income=-40_000,
        current_assets=760_000,
        current_liabilities=800_000,
        cash=35_000,
        receivables=180_000,
        total_assets=2_200_000,
        existing_debt=1_650_000,
        equity=350_000,
        existing_annual_debt_service=_service_for_target(ebitda, loan, rate, term, 0.98),
        credit_score=600,
        delinquencies_12m=2,
        bankruptcy=False,
        relationship_years=1,
        deposit_balance=20_000,
        prior_loans_current=False,
        revenue_growth=-0.05,
        industry_outlook="Negative",
        analyst_request="Analyze this business loan application and assess the risk.",
    )


_BUILDERS = {"apex": apex, "harbor": harbor, "northwind": northwind}


def get_sample(name: str) -> LoanApplication:
    key = name.lower().strip()
    if key not in _BUILDERS:
        known = ", ".join(_BUILDERS)
        raise KeyError(f"Unknown sample '{name}'. Choose from: {known}")
    return _BUILDERS[key]()


def to_form(app: LoanApplication) -> dict:
    data = app.model_dump()
    data["revenue_growth_pct"] = round(float(data.pop("revenue_growth")) * 100, 2)
    return data


def from_form(values: dict) -> LoanApplication:
    data = {name: values[name] for name in LoanApplication.model_fields if name != "revenue_growth"}
    data["revenue_growth"] = float(values["revenue_growth_pct"]) / 100.0
    return LoanApplication(**data)
