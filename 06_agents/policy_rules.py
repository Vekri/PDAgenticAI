"""Executable credit policy.

Thresholds here are the system of record. The markdown corpus explains the
same rules so retrieval can cite them. A preferred miss sends the file to
review. A hard stop declines it. Incomplete data stays in review unless a
hard stop is already true.
"""

from __future__ import annotations

from app.formatting import fmt_pct, fmt_ratio
from app.schemas import LoanApplication, PolicyCheck

PD_STRAIGHT = 0.05
PD_HARD = 0.15
DTE_STRAIGHT = 3.0
DTE_HARD = 4.0
DSCR_STRAIGHT = 1.25
DSCR_HARD = 1.10
CREDIT_STRAIGHT = 680
CREDIT_HARD = 620
CURRENT_STRAIGHT = 1.20
CURRENT_HARD = 0.80
YEARS_STRAIGHT = 3
YEARS_HARD = 2
TERM_STRAIGHT = 7
TERM_HARD = 10
LOAN_EBITDA_STRAIGHT = 2.5
LOAN_EBITDA_HARD = 4.0
DEBT_EQUITY_STRAIGHT = 3.5
DEBT_EQUITY_HARD = 5.0
INTEREST_COVER_STRAIGHT = 2.0
INTEREST_COVER_HARD = 1.25
DELINQ_HARD = 3

APPROVE_WHY = [
    "PD is below policy threshold (< 5%)",
    "Debt/EBITDA within limit (< 3.0)",
    "DSCR meets requirement (> 1.25)",
    "Credit score satisfies preferred threshold",
    "Complies with Credit Policy §4.2 and Risk Policy §3.1",
]


def _check(code: str, level: str, passed: bool, section: str, message: str) -> PolicyCheck:
    return PolicyCheck(code=code, level=level, passed=passed, section=section, message=message)


def evaluate(app: LoanApplication, metrics: dict, pd_value: float | None, data_errors: list[str]) -> list[PolicyCheck]:
    checks: list[PolicyCheck] = []
    for message in data_errors:
        checks.append(_check("data", "data", False, "Credit Policy §2", message))

    if app.bankruptcy:
        checks.append(
            _check(
                "bankruptcy",
                "hard",
                False,
                "Risk Policy §3.1",
                "A bankruptcy flag is a hard stop (Risk Policy §3.1).",
            )
        )
    else:
        checks.append(
            _check(
                "bankruptcy",
                "hard",
                True,
                "Risk Policy §3.1",
                "No bankruptcy flag is on the file (Risk Policy §3.1).",
            )
        )

    if 300 <= app.credit_score <= 850:
        if app.credit_score < CREDIT_HARD:
            checks.append(
                _check(
                    "credit",
                    "hard",
                    False,
                    "Risk Policy §3.1",
                    f"Credit score is {app.credit_score}, below the {CREDIT_HARD} hard stop (Risk Policy §3.1).",
                )
            )
        elif app.credit_score < CREDIT_STRAIGHT:
            checks.append(
                _check(
                    "credit",
                    "preferred",
                    False,
                    "Credit Policy §4.2",
                    f"Credit score is {app.credit_score}, below the {CREDIT_STRAIGHT} straight-through requirement (Credit Policy §4.2).",
                )
            )
        else:
            checks.append(
                _check(
                    "credit",
                    "preferred",
                    True,
                    "Credit Policy §4.2",
                    f"Credit score is {app.credit_score}, which meets the {CREDIT_STRAIGHT} straight-through requirement (Credit Policy §4.2).",
                )
            )

    if data_errors:
        checks.append(_fair_lending())
        return checks

    if pd_value is not None:
        shown = fmt_pct(pd_value)
        if pd_value >= PD_HARD:
            checks.append(
                _check(
                    "pd",
                    "hard",
                    False,
                    "Risk Policy §3.1",
                    f"PD is {shown}, at or above the {fmt_pct(PD_HARD)} hard stop (Risk Policy §3.1).",
                )
            )
        elif pd_value >= PD_STRAIGHT:
            checks.append(
                _check(
                    "pd",
                    "preferred",
                    False,
                    "Credit Policy §4.2",
                    f"PD is {shown}, above the {fmt_pct(PD_STRAIGHT)} straight-through threshold (Credit Policy §4.2).",
                )
            )
        else:
            checks.append(
                _check(
                    "pd",
                    "preferred",
                    True,
                    "Credit Policy §4.2",
                    f"PD is {shown}, below the {fmt_pct(PD_STRAIGHT)} straight-through threshold (Credit Policy §4.2).",
                )
            )

    dte = metrics["debt_to_ebitda"]
    if dte > DTE_HARD:
        checks.append(
            _check(
                "leverage",
                "hard",
                False,
                "Risk Policy §3.1",
                f"Pro forma Debt/EBITDA is {fmt_ratio(dte)}, above the {fmt_ratio(DTE_HARD)} hard stop (Risk Policy §3.1).",
            )
        )
    elif dte >= DTE_STRAIGHT:
        checks.append(
            _check(
                "leverage",
                "preferred",
                False,
                "Credit Policy §4.2",
                f"Pro forma Debt/EBITDA is {fmt_ratio(dte)}, outside the {fmt_ratio(DTE_STRAIGHT)} straight-through limit (Credit Policy §4.2).",
            )
        )
    else:
        checks.append(
            _check(
                "leverage",
                "preferred",
                True,
                "Credit Policy §4.2",
                f"Pro forma Debt/EBITDA is {fmt_ratio(dte)}, within the {fmt_ratio(DTE_STRAIGHT)} straight-through limit (Credit Policy §4.2).",
            )
        )

    dscr = metrics["dscr"]
    if dscr < DSCR_HARD:
        checks.append(
            _check(
                "dscr",
                "hard",
                False,
                "Risk Policy §3.1",
                f"DSCR is {fmt_ratio(dscr)}, below the {fmt_ratio(DSCR_HARD)} hard stop (Risk Policy §3.1).",
            )
        )
    elif dscr <= DSCR_STRAIGHT:
        checks.append(
            _check(
                "dscr",
                "preferred",
                False,
                "Credit Policy §4.2",
                f"DSCR is {fmt_ratio(dscr)}, below the {fmt_ratio(DSCR_STRAIGHT)} straight-through requirement (Credit Policy §4.2).",
            )
        )
    else:
        checks.append(
            _check(
                "dscr",
                "preferred",
                True,
                "Credit Policy §4.2",
                f"DSCR is {fmt_ratio(dscr)}, which meets the {fmt_ratio(DSCR_STRAIGHT)} straight-through requirement (Credit Policy §4.2).",
            )
        )

    current = metrics["current_ratio"]
    if current < CURRENT_HARD:
        checks.append(
            _check(
                "liquidity",
                "hard",
                False,
                "Risk Policy §3.1",
                f"Current ratio is {fmt_ratio(current)}, below the {fmt_ratio(CURRENT_HARD)} hard stop (Risk Policy §3.1).",
            )
        )
    elif current < CURRENT_STRAIGHT:
        checks.append(
            _check(
                "liquidity",
                "preferred",
                False,
                "Credit Policy §4.2",
                f"Current ratio is {fmt_ratio(current)}, below the {fmt_ratio(CURRENT_STRAIGHT)} straight-through requirement (Credit Policy §4.2).",
            )
        )
    else:
        checks.append(
            _check(
                "liquidity",
                "preferred",
                True,
                "Credit Policy §4.2",
                f"Current ratio is {fmt_ratio(current)}, which meets the {fmt_ratio(CURRENT_STRAIGHT)} straight-through requirement (Credit Policy §4.2).",
            )
        )

    years = app.years_in_business
    if years < YEARS_HARD:
        checks.append(
            _check(
                "tenure",
                "hard",
                False,
                "Risk Policy §3.1",
                f"Years in business is {years}, below the {YEARS_HARD}-year hard stop (Risk Policy §3.1).",
            )
        )
    elif years < YEARS_STRAIGHT:
        checks.append(
            _check(
                "tenure",
                "preferred",
                False,
                "Credit Policy §4.2",
                f"Years in business is {years}, below the {YEARS_STRAIGHT}-year straight-through requirement (Credit Policy §4.2).",
            )
        )
    else:
        checks.append(
            _check(
                "tenure",
                "preferred",
                True,
                "Credit Policy §4.2",
                f"Years in business is {years}, which meets the {YEARS_STRAIGHT}-year requirement (Credit Policy §4.2).",
            )
        )

    if app.delinquencies_12m >= DELINQ_HARD:
        checks.append(
            _check(
                "delinquency",
                "hard",
                False,
                "Risk Policy §3.1",
                f"{app.delinquencies_12m} delinquencies in 12 months hit the hard stop (Risk Policy §3.1).",
            )
        )
    elif app.delinquencies_12m > 0:
        checks.append(
            _check(
                "delinquency",
                "preferred",
                False,
                "Credit Policy §4.2",
                f"{app.delinquencies_12m} delinquencies in 12 months block straight-through approval (Credit Policy §4.2).",
            )
        )
    else:
        checks.append(
            _check(
                "delinquency",
                "preferred",
                True,
                "Credit Policy §4.2",
                "No delinquency in the last 12 months (Credit Policy §4.2).",
            )
        )

    term = app.loan_term_years
    if term > TERM_HARD:
        checks.append(
            _check(
                "term",
                "hard",
                False,
                "Lending Guidelines §2",
                f"Loan term of {term} years exceeds the {TERM_HARD}-year hard stop (Lending Guidelines §2).",
            )
        )
    elif term > TERM_STRAIGHT:
        checks.append(
            _check(
                "term",
                "preferred",
                False,
                "Lending Guidelines §2",
                f"Loan term of {term} years exceeds the {TERM_STRAIGHT}-year straight-through limit (Lending Guidelines §2).",
            )
        )
    else:
        checks.append(
            _check(
                "term",
                "preferred",
                True,
                "Lending Guidelines §2",
                f"Loan term of {term} years is within the {TERM_STRAIGHT}-year guideline (Lending Guidelines §2).",
            )
        )

    loan_ratio = metrics["loan_to_ebitda"]
    if loan_ratio > LOAN_EBITDA_HARD:
        checks.append(
            _check(
                "loan_size",
                "hard",
                False,
                "Lending Guidelines §2",
                f"Proposed loan / EBITDA is {fmt_ratio(loan_ratio)}, above the {fmt_ratio(LOAN_EBITDA_HARD)} hard stop (Lending Guidelines §2).",
            )
        )
    elif loan_ratio > LOAN_EBITDA_STRAIGHT:
        checks.append(
            _check(
                "loan_size",
                "preferred",
                False,
                "Lending Guidelines §2",
                f"Proposed loan / EBITDA is {fmt_ratio(loan_ratio)}, outside the {fmt_ratio(LOAN_EBITDA_STRAIGHT)} straight-through limit (Lending Guidelines §2).",
            )
        )
    else:
        checks.append(
            _check(
                "loan_size",
                "preferred",
                True,
                "Lending Guidelines §2",
                f"Proposed loan / EBITDA is {fmt_ratio(loan_ratio)}, within the {fmt_ratio(LOAN_EBITDA_STRAIGHT)} guideline (Lending Guidelines §2).",
            )
        )

    debt_equity = metrics.get("debt_to_equity")
    if debt_equity is not None:
        if debt_equity > DEBT_EQUITY_HARD:
            checks.append(
                _check(
                    "debt_equity",
                    "hard",
                    False,
                    "Lending Guidelines §2",
                    f"Pro forma Debt/Equity is {fmt_ratio(debt_equity)}, above the {fmt_ratio(DEBT_EQUITY_HARD)} hard stop (Lending Guidelines §2).",
                )
            )
        elif debt_equity > DEBT_EQUITY_STRAIGHT:
            checks.append(
                _check(
                    "debt_equity",
                    "preferred",
                    False,
                    "Lending Guidelines §2",
                    f"Pro forma Debt/Equity is {fmt_ratio(debt_equity)}, outside the {fmt_ratio(DEBT_EQUITY_STRAIGHT)} guideline (Lending Guidelines §2).",
                )
            )
        else:
            checks.append(
                _check(
                    "debt_equity",
                    "preferred",
                    True,
                    "Lending Guidelines §2",
                    f"Pro forma Debt/Equity is {fmt_ratio(debt_equity)}, within the {fmt_ratio(DEBT_EQUITY_STRAIGHT)} guideline (Lending Guidelines §2).",
                )
            )

    if app.interest_expense <= 0:
        checks.append(
            _check(
                "interest_cover",
                "preferred",
                True,
                "Lending Guidelines §3",
                "No interest expense was reported, so coverage is not a constraint (Lending Guidelines §3).",
            )
        )
    elif metrics.get("interest_coverage") is not None:
        coverage = metrics["interest_coverage"]
        if coverage < INTEREST_COVER_HARD:
            checks.append(
                _check(
                    "interest_cover",
                    "hard",
                    False,
                    "Lending Guidelines §3",
                    f"Interest coverage is {fmt_ratio(coverage)}, below the {fmt_ratio(INTEREST_COVER_HARD)} hard stop (Lending Guidelines §3).",
                )
            )
        elif coverage < INTEREST_COVER_STRAIGHT:
            checks.append(
                _check(
                    "interest_cover",
                    "preferred",
                    False,
                    "Lending Guidelines §3",
                    f"Interest coverage is {fmt_ratio(coverage)}, below the {fmt_ratio(INTEREST_COVER_STRAIGHT)} guideline (Lending Guidelines §3).",
                )
            )
        else:
            checks.append(
                _check(
                    "interest_cover",
                    "preferred",
                    True,
                    "Lending Guidelines §3",
                    f"Interest coverage is {fmt_ratio(coverage)}, which meets the {fmt_ratio(INTEREST_COVER_STRAIGHT)} guideline (Lending Guidelines §3).",
                )
            )

    if app.prior_loans_current:
        checks.append(
            _check(
                "relationship",
                "preferred",
                True,
                "Credit Policy §4.2",
                "Prior loans with the bank are current (Credit Policy §4.2).",
            )
        )
    else:
        checks.append(
            _check(
                "relationship",
                "preferred",
                False,
                "Credit Policy §4.2",
                "Prior loans are not current, so the file cannot be straight-through approved (Credit Policy §4.2).",
            )
        )

    checks.append(_fair_lending())
    return checks


def _fair_lending() -> PolicyCheck:
    return _check(
        "fair_lending",
        "control",
        True,
        "Regulatory Notes §1",
        "No prohibited-basis attributes are used. The model sees business financials, credit score, and industry only.",
    )


def recommendation_from(checks: list[PolicyCheck]) -> str:
    if any(not item.passed and item.level == "hard" for item in checks):
        return "REJECT"
    if any(not item.passed and item.level in {"data", "preferred"} for item in checks):
        return "REVIEW"
    return "APPROVE"


def why_lines(recommendation: str, checks: list[PolicyCheck]) -> list[str]:
    if recommendation == "APPROVE":
        return list(APPROVE_WHY)
    return [item.message for item in checks if not item.passed and item.level in {"hard", "preferred", "data"}]
