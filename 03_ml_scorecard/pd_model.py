"""Explainable PD scorecard plus a local ML cross-check.

The official probability of default is a logistic scorecard. A reference
low-risk profile lands on 3.8 percent. Each factor below moves the log-odds
away from that profile. Positive logit raises PD.

The gradient model is trained on a synthetic book drawn from this same
scorecard. It is a cross-check only and never changes the recommendation.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from app.schemas import LoanApplication

REFERENCE_PD = 0.038
BASE_LOGIT = math.log(REFERENCE_PD / (1 - REFERENCE_PD))

INDUSTRY_LOGIT = {
    "Manufacturing": 0.0,
    "Wholesale": 0.05,
    "Logistics": 0.15,
    "Professional Services": -0.08,
    "Healthcare": -0.05,
    "Retail": 0.30,
    "Construction": 0.40,
    "Hospitality": 0.35,
    "Technology": 0.05,
    "Agriculture": 0.10,
}
INDUSTRIES = tuple(INDUSTRY_LOGIT)
OUTLOOK_LOGIT = {"Positive": -0.10, "Stable": 0.0, "Negative": 0.25}
OUTLOOKS = tuple(OUTLOOK_LOGIT)

FEATURE_NAMES = (
    "credit_score",
    "debt_to_ebitda",
    "dscr",
    "current_ratio",
    "years_in_business",
    "revenue_growth",
    "delinquencies_12m",
    "bankruptcy",
    "industry_logit",
    "outlook_logit",
)


def risk_grade(pd_value: float) -> str:
    if pd_value < 0.02:
        return "Very Low"
    if pd_value < 0.05:
        return "Low"
    if pd_value < 0.10:
        return "Medium"
    if pd_value < 0.15:
        return "High"
    return "Very High"


def industry_addon(industry: str) -> float:
    return INDUSTRY_LOGIT.get(industry, 0.20)


def outlook_addon(outlook: str) -> float:
    return OUTLOOK_LOGIT.get(outlook, 0.0)


def _sigmoid(logit: float) -> float:
    clipped = max(min(logit, 12.0), -12.0)
    return 1.0 / (1.0 + math.exp(-clipped))


def _direction(logit: float) -> str:
    if abs(logit) < 1e-9:
        return "neutral"
    if logit > 0:
        return "increases PD"
    return "decreases PD"


def scorecard(
    credit_score: float,
    debt_to_ebitda: float,
    dscr: float,
    current_ratio: float,
    years_in_business: float,
    revenue_growth: float,
    delinquencies_12m: int,
    bankruptcy: bool,
    industry: str,
    industry_outlook: str,
) -> dict:
    parts = [
        ("Credit score vs 720 reference", (720 - credit_score) / 100 * 0.90),
        ("Debt/EBITDA vs 2.0x reference", (debt_to_ebitda - 2.0) * 0.55),
        ("DSCR vs 1.62x reference", (1.62 - dscr) * 0.70),
        ("Current ratio vs 1.80 reference", (1.80 - current_ratio) * 0.20),
        ("Years in business vs 10 reference", (10 - years_in_business) * 0.04),
        ("Revenue growth vs 5% reference", (0.05 - revenue_growth) * 1.50),
        ("Delinquency in the last 12 months", 0.65 if delinquencies_12m > 0 else 0.0),
        ("Bankruptcy flag", 1.25 if bankruptcy else 0.0),
        (f"Industry ({industry})", industry_addon(industry)),
        (f"Industry outlook ({industry_outlook})", outlook_addon(industry_outlook)),
    ]
    drivers = [
        {"factor": name, "logit": float(value), "direction": _direction(value)}
        for name, value in parts
    ]
    logit = BASE_LOGIT + sum(item["logit"] for item in drivers)
    pd_value = _sigmoid(logit)
    return {
        "pd": float(pd_value),
        "logit": float(logit),
        "grade": risk_grade(pd_value),
        "drivers": drivers,
    }


def score_application(app: LoanApplication, metrics: dict) -> dict | None:
    required = ("debt_to_ebitda", "dscr", "current_ratio")
    if any(metrics.get(key) is None for key in required):
        return None
    result = scorecard(
        credit_score=app.credit_score,
        debt_to_ebitda=metrics["debt_to_ebitda"],
        dscr=metrics["dscr"],
        current_ratio=metrics["current_ratio"],
        years_in_business=app.years_in_business,
        revenue_growth=app.revenue_growth,
        delinquencies_12m=app.delinquencies_12m,
        bankruptcy=app.bankruptcy,
        industry=app.industry,
        industry_outlook=app.industry_outlook,
    )
    ml_pd, backend = cross_check(app, metrics)
    result["ml_pd"] = ml_pd
    result["ml_backend"] = backend
    return result


def _feature_row(app: LoanApplication, metrics: dict) -> list[float]:
    return [
        float(app.credit_score),
        float(metrics["debt_to_ebitda"]),
        float(metrics["dscr"]),
        float(metrics["current_ratio"]),
        float(app.years_in_business),
        float(app.revenue_growth),
        float(app.delinquencies_12m),
        1.0 if app.bankruptcy else 0.0,
        float(industry_addon(app.industry)),
        float(outlook_addon(app.industry_outlook)),
    ]


def _synthetic(n: int = 4000, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    credit = rng.uniform(560, 820, n)
    debt = rng.uniform(0.4, 5.5, n)
    dscr = rng.uniform(0.7, 3.2, n)
    current = rng.uniform(0.5, 3.2, n)
    years = rng.uniform(1, 35, n)
    growth = rng.uniform(-0.25, 0.30, n)
    delinquencies = rng.integers(0, 5, n)
    bankruptcy = rng.random(n) < 0.04
    industries = rng.choice(list(INDUSTRIES), n)
    outlooks = rng.choice(list(OUTLOOKS), n)
    rows = []
    targets = []
    for i in range(n):
        scored = scorecard(
            credit[i],
            debt[i],
            dscr[i],
            current[i],
            years[i],
            growth[i],
            int(delinquencies[i]),
            bool(bankruptcy[i]),
            str(industries[i]),
            str(outlooks[i]),
        )
        rows.append(
            [
                credit[i],
                debt[i],
                dscr[i],
                current[i],
                years[i],
                growth[i],
                delinquencies[i],
                1.0 if bankruptcy[i] else 0.0,
                industry_addon(str(industries[i])),
                outlook_addon(str(outlooks[i])),
            ]
        )
        targets.append(scored["pd"])
    return np.asarray(rows, dtype=float), np.asarray(targets, dtype=float)


@lru_cache(maxsize=1)
def get_ml_model():
    features, target = _synthetic()
    try:
        from xgboost import XGBRegressor

        model = XGBRegressor(
            n_estimators=80,
            max_depth=3,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
            n_jobs=1,
            verbosity=0,
        )
        model.fit(features, target)
        return model, "XGBoost"
    except Exception:
        from sklearn.ensemble import GradientBoostingRegressor

        model = GradientBoostingRegressor(
            n_estimators=80,
            max_depth=3,
            learning_rate=0.08,
            random_state=42,
        )
        model.fit(features, target)
        return model, "scikit-learn GradientBoosting"


def cross_check(app: LoanApplication, metrics: dict) -> tuple[float | None, str]:
    try:
        model, backend = get_ml_model()
        row = np.asarray([_feature_row(app, metrics)], dtype=float)
        predicted = float(model.predict(row)[0])
        predicted = min(max(predicted, 0.001), 0.95)
        return predicted, backend
    except Exception:
        return None, "unavailable"
