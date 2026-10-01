"""Data engineering for the credit warehouse.

Inputs live in five source tables, one per system in the architecture.
Those rows are assembled into the loan file the agents score. The decision,
its checks, its evidence, and its audit steps are written back as outputs.
"""

from __future__ import annotations

from psycopg.types.json import Jsonb

from app.orchestrator import run_decision
from app.platform.postgres import connect, current_deployment_id
from app.platform.release import release_manifest
from app.samples import SAMPLE_CATALOG, get_sample
from app.schemas import DecisionResult, LoanApplication


def upsert_sources(connection, application_id: str, application: LoanApplication) -> None:
    connection.execute(
        """
        INSERT INTO credit.loan_application (
            application_id, business_name, industry, years_in_business, loan_amount,
            loan_purpose, loan_term_years, interest_rate_pct, analyst_request
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (application_id) DO UPDATE SET
            business_name = EXCLUDED.business_name,
            industry = EXCLUDED.industry,
            years_in_business = EXCLUDED.years_in_business,
            loan_amount = EXCLUDED.loan_amount,
            loan_purpose = EXCLUDED.loan_purpose,
            loan_term_years = EXCLUDED.loan_term_years,
            interest_rate_pct = EXCLUDED.interest_rate_pct,
            analyst_request = EXCLUDED.analyst_request,
            received_at = now()
        """,
        (
            application_id,
            application.business_name,
            application.industry,
            application.years_in_business,
            application.loan_amount,
            application.loan_purpose,
            application.loan_term_years,
            application.interest_rate_pct,
            application.analyst_request,
        ),
    )
    connection.execute(
        """
        INSERT INTO credit.financial_statement (
            application_id, revenue, ebitda, interest_expense, net_income,
            current_assets, current_liabilities, cash, receivables, total_assets,
            existing_debt, equity, existing_annual_debt_service
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (application_id) DO UPDATE SET
            revenue = EXCLUDED.revenue,
            ebitda = EXCLUDED.ebitda,
            interest_expense = EXCLUDED.interest_expense,
            net_income = EXCLUDED.net_income,
            current_assets = EXCLUDED.current_assets,
            current_liabilities = EXCLUDED.current_liabilities,
            cash = EXCLUDED.cash,
            receivables = EXCLUDED.receivables,
            total_assets = EXCLUDED.total_assets,
            existing_debt = EXCLUDED.existing_debt,
            equity = EXCLUDED.equity,
            existing_annual_debt_service = EXCLUDED.existing_annual_debt_service
        """,
        (
            application_id,
            application.revenue,
            application.ebitda,
            application.interest_expense,
            application.net_income,
            application.current_assets,
            application.current_liabilities,
            application.cash,
            application.receivables,
            application.total_assets,
            application.existing_debt,
            application.equity,
            application.existing_annual_debt_service,
        ),
    )
    connection.execute(
        """
        INSERT INTO credit.credit_bureau (
            application_id, credit_score, delinquencies_12m, bankruptcy
        ) VALUES (%s, %s, %s, %s)
        ON CONFLICT (application_id) DO UPDATE SET
            credit_score = EXCLUDED.credit_score,
            delinquencies_12m = EXCLUDED.delinquencies_12m,
            bankruptcy = EXCLUDED.bankruptcy,
            pulled_at = now()
        """,
        (
            application_id,
            application.credit_score,
            application.delinquencies_12m,
            application.bankruptcy,
        ),
    )
    connection.execute(
        """
        INSERT INTO credit.bank_relationship (
            application_id, relationship_years, deposit_balance, prior_loans_current
        ) VALUES (%s, %s, %s, %s)
        ON CONFLICT (application_id) DO UPDATE SET
            relationship_years = EXCLUDED.relationship_years,
            deposit_balance = EXCLUDED.deposit_balance,
            prior_loans_current = EXCLUDED.prior_loans_current
        """,
        (
            application_id,
            application.relationship_years,
            application.deposit_balance,
            application.prior_loans_current,
        ),
    )
    connection.execute(
        """
        INSERT INTO credit.market_observation (
            application_id, revenue_growth, industry_outlook
        ) VALUES (%s, %s, %s)
        ON CONFLICT (application_id) DO UPDATE SET
            revenue_growth = EXCLUDED.revenue_growth,
            industry_outlook = EXCLUDED.industry_outlook,
            observed_at = now()
        """,
        (application_id, application.revenue_growth, application.industry_outlook),
    )


def load_application(connection, application_id: str) -> LoanApplication:
    row = connection.execute(
        """
        SELECT
            a.business_name, a.industry, a.years_in_business, a.loan_amount, a.loan_purpose,
            a.loan_term_years, a.interest_rate_pct, a.analyst_request,
            f.revenue, f.ebitda, f.interest_expense, f.net_income, f.current_assets,
            f.current_liabilities, f.cash, f.receivables, f.total_assets, f.existing_debt,
            f.equity, f.existing_annual_debt_service,
            b.credit_score, b.delinquencies_12m, b.bankruptcy,
            r.relationship_years, r.deposit_balance, r.prior_loans_current,
            m.revenue_growth, m.industry_outlook
        FROM credit.loan_application AS a
        JOIN credit.financial_statement AS f USING (application_id)
        JOIN credit.credit_bureau AS b USING (application_id)
        JOIN credit.bank_relationship AS r USING (application_id)
        JOIN credit.market_observation AS m USING (application_id)
        WHERE a.application_id = %s
        """,
        (application_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"No complete loan file for '{application_id}'.")
    return LoanApplication(
        business_name=row["business_name"],
        industry=row["industry"],
        years_in_business=int(row["years_in_business"]),
        loan_amount=float(row["loan_amount"]),
        loan_purpose=row["loan_purpose"],
        loan_term_years=int(row["loan_term_years"]),
        interest_rate_pct=float(row["interest_rate_pct"]),
        analyst_request=row["analyst_request"],
        revenue=float(row["revenue"]),
        ebitda=float(row["ebitda"]),
        interest_expense=float(row["interest_expense"]),
        net_income=float(row["net_income"]),
        current_assets=float(row["current_assets"]),
        current_liabilities=float(row["current_liabilities"]),
        cash=float(row["cash"]),
        receivables=float(row["receivables"]),
        total_assets=float(row["total_assets"]),
        existing_debt=float(row["existing_debt"]),
        equity=float(row["equity"]),
        existing_annual_debt_service=float(row["existing_annual_debt_service"]),
        credit_score=int(row["credit_score"]),
        delinquencies_12m=int(row["delinquencies_12m"]),
        bankruptcy=bool(row["bankruptcy"]),
        relationship_years=int(row["relationship_years"]),
        deposit_balance=float(row["deposit_balance"]),
        prior_loans_current=bool(row["prior_loans_current"]),
        revenue_growth=float(row["revenue_growth"]),
        industry_outlook=row["industry_outlook"],
    )


def list_applications(connection) -> list[dict]:
    return list(
        connection.execute(
            """
            SELECT a.application_id, a.business_name, a.industry, a.loan_amount, a.received_at,
                   d.recommendation, d.pd_display, d.risk_grade, d.run_id
            FROM credit.loan_application AS a
            LEFT JOIN credit.latest_decision AS d USING (application_id)
            ORDER BY a.received_at DESC
            """
        ).fetchall()
    )


def seed_missing_samples() -> list[str]:
    created: list[str] = []
    with connect() as connection:
        existing = {
            row["application_id"]
            for row in connection.execute("SELECT application_id FROM credit.loan_application").fetchall()
        }
        for item in SAMPLE_CATALOG:
            if item["id"] in existing:
                continue
            upsert_sources(connection, item["id"], get_sample(item["id"]))
            created.append(item["id"])
        connection.commit()
    return created


def stamp_release(result: DecisionResult, application_id: str, deployment: str) -> DecisionResult:
    manifest = release_manifest()
    return result.model_copy(
        update={
            "application_id": application_id,
            "deployment_id": deployment,
            "app_version": manifest["app_version"],
            "pipeline_version": manifest["pipeline_version"],
            "policy_version": manifest["policy_version"],
            "scorecard_version": manifest["scorecard_version"],
            "ml_model_version": manifest["ml_model_version"],
            "rag_corpus_version": manifest["rag_corpus_version"],
        }
    )


def publish_decision(connection, result: DecisionResult) -> None:
    if not result.application_id or not result.deployment_id:
        raise ValueError("A warehouse decision needs an application id and a deployment id.")
    ratios = result.key_ratios or {}
    connection.execute(
        """
        INSERT INTO credit.feature_record (run_id, application_id, deployment_id, built_at, payload)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            result.run_id,
            result.application_id,
            result.deployment_id,
            result.created_at,
            Jsonb(result.application),
        ),
    )
    connection.execute(
        """
        INSERT INTO credit.decision (
            run_id, application_id, deployment_id, recommendation, pd_score, pd_display,
            risk_grade, ml_pd, ml_backend, debt_to_ebitda, dscr, credit_score,
            explanation, explanation_source, why_json, metrics_json, drivers_json,
            elapsed_ms, created_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            result.run_id,
            result.application_id,
            result.deployment_id,
            result.recommendation,
            result.pd_score,
            result.pd_display,
            result.risk_grade,
            result.ml_pd,
            result.ml_backend,
            ratios.get("debt_to_ebitda"),
            ratios.get("dscr"),
            ratios.get("credit_score"),
            result.explanation,
            result.explanation_source,
            Jsonb(result.why),
            Jsonb(result.metrics),
            Jsonb(result.drivers),
            result.elapsed_ms,
            result.created_at,
        ),
    )
    for order, check in enumerate(result.policy_checks):
        connection.execute(
            """
            INSERT INTO credit.decision_check (run_id, check_order, code, level, passed, section, message)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (result.run_id, order, check["code"], check["level"], check["passed"], check["section"], check["message"]),
        )
    for order, item in enumerate(result.policy_evidence):
        connection.execute(
            """
            INSERT INTO credit.decision_evidence (
                run_id, evidence_order, source, section, title, excerpt, score, origin
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                result.run_id,
                order,
                item["source"],
                item["section"],
                item["title"],
                item["excerpt"],
                item.get("score"),
                item["origin"],
            ),
        )
    for step in result.audit:
        connection.execute(
            """
            INSERT INTO credit.decision_audit (run_id, step, name, short_name, status, detail, recorded_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                result.run_id,
                step["step"],
                step["name"],
                step["short"],
                step["status"],
                step["detail"],
                step["at"],
            ),
        )


def land_and_decide(application_id: str, application: LoanApplication, use_llm: bool = False) -> DecisionResult:
    from app.platform.postgres import ensure_platform

    ensure_platform()
    deployment = current_deployment_id()
    with connect() as connection:
        upsert_sources(connection, application_id, application)
        connection.commit()
    result = run_decision(application, use_llm=use_llm, persist=False)
    stamped = stamp_release(result, application_id, deployment)
    with connect() as connection:
        publish_decision(connection, stamped)
        connection.commit()
    return stamped


def decide_stored(application_id: str, use_llm: bool = False) -> DecisionResult:
    from app.platform.postgres import ensure_platform

    ensure_platform()
    with connect() as connection:
        application = load_application(connection, application_id)
    return land_and_decide(application_id, application, use_llm=use_llm)


def fetch_decision(connection, run_id: str) -> dict | None:
    row = connection.execute("SELECT * FROM credit.decision WHERE run_id = %s", (run_id,)).fetchone()
    if row is None:
        return None
    payload = dict(row)
    payload["checks"] = list(
        connection.execute(
            "SELECT * FROM credit.decision_check WHERE run_id = %s ORDER BY check_order",
            (run_id,),
        ).fetchall()
    )
    payload["evidence"] = list(
        connection.execute(
            "SELECT * FROM credit.decision_evidence WHERE run_id = %s ORDER BY evidence_order",
            (run_id,),
        ).fetchall()
    )
    payload["audit"] = list(
        connection.execute(
            "SELECT * FROM credit.decision_audit WHERE run_id = %s ORDER BY step",
            (run_id,),
        ).fetchall()
    )
    return payload
