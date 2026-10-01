"""Credit desk. Run from the project folder: streamlit run 09_desk/ui.py"""

from __future__ import annotations

import base64
import html
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.data_engineering.warehouse import decide_stored, land_and_decide, load_application
from app.formatting import fmt_pct, fmt_ratio, money
from app.llm import ollama_status
from app.operator import ask
from app.schedule_control import (
    WEEKDAYS,
    inbox_loaded,
    inbox_waiting,
    project_incremental_files,
    run_incremental_load,
    run_initial_load,
    save_schedule,
    task_status,
)
from app.sql_chat import run_query
from app.orchestrator import run_decision
from app.platform.postgres import connect, postgres_status
from app.platform.release import release_manifest
from app.pd_model import INDUSTRIES, OUTLOOKS
from app.rag import get_index
from app.samples import SAMPLE_CATALOG, from_form, get_sample, to_form
from app.schemas import DecisionResult
from app.store import clear_decisions, get_decision, list_decisions

st.set_page_config(
    page_title="Agentic AI for Business Loan Decisioning",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

_HALL = base64.b64encode((Path(__file__).parent / "bank_hall.jpg").read_bytes()).decode("ascii")

st.markdown(
    f"""
    <style>
    .stApp {{
        background-color: #07111F;
        background-image:
            linear-gradient(180deg, rgba(7, 17, 31, 0.72) 0%, rgba(7, 17, 31, 0.55) 42%, rgba(7, 17, 31, 0.78) 100%),
            url("data:image/jpeg;base64,{_HALL}");
        background-repeat: no-repeat;
        background-position: center center;
        background-size: cover;
        background-attachment: fixed;
    }}
    [data-testid="stAppViewContainer"] {{background: transparent;}}
    [data-testid="stHeader"] {{background: rgba(7, 17, 31, 0.35);}}
    [data-testid="stSidebar"] {{background-color: rgba(10, 22, 40, 0.94);}}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.1rem; max-width: 1240px;}
    .hero {
        background: linear-gradient(105deg, #0d3f86 0%, #102848 58%, #0e5c45 130%);
        border-radius: 18px;
        padding: 22px 26px 18px;
        margin-bottom: 12px;
    }
    .hero h1 {margin: 0 0 4px 0; font-size: 1.85rem; color: white; letter-spacing: -0.02em;}
    .hero p {margin: 0; color: #d5e4f7; font-size: 0.98rem;}
    .kicker {color: #9ed0ff; font-size: 0.75rem; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 6px;}
    .trio {display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 8px 0 14px;}
    .trio div {background: #10233f; border: 1px solid #1d3e68; border-radius: 12px; padding: 10px 12px; color: #d7e3f4; font-size: 0.86rem;}
    .trio b {color: white; display: block; margin-bottom: 3px;}
    .banner {border-radius: 14px; padding: 14px 16px; font-size: 1.7rem; font-weight: 800; letter-spacing: 0.04em;}
    .banner.approve {background: #123d2a; color: #8dffb8; border: 1px solid #1f8a4c;}
    .banner.review {background: #3a3112; color: #ffd56a; border: 1px solid #c9922a;}
    .banner.reject {background: #3d161b; color: #ff9b9b; border: 1px solid #c94b4b;}
    .banner span {display: block; font-size: 0.72rem; letter-spacing: 0.08em; font-weight: 650; opacity: 0.8;}
    .metrics {display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin: 10px 0;}
    .metric {background: #10233f; border: 1px solid #1e3d66; border-radius: 12px; padding: 10px 12px;}
    .metric .label {color: #93a9c4; font-size: 0.68rem; letter-spacing: 0.06em; text-transform: uppercase;}
    .metric .value {color: white; font-size: 1.35rem; font-weight: 750; margin-top: 2px;}
    .why {margin: 6px 0 0; padding-left: 0; list-style: none;}
    .why li {margin: 5px 0; color: #e7eef8;}
    .flow {display: flex; gap: 6px; flex-wrap: wrap; margin: 6px 0 12px;}
    .step {background: #10233f; border-radius: 999px; padding: 6px 10px; font-size: 0.78rem; color: #d5e2f2; border: 1px solid #24486f;}
    .step.ok {border-color: #1f8a4c; color: #b8ffd4;}
    .step.warn {border-color: #c9922a; color: #ffe2a3;}
    .step.fail {border-color: #c94b4b; color: #ffc1c1;}
    .check-row {padding: 7px 0; border-bottom: 1px solid #1c3558; color: #e7eef8; font-size: 0.92rem;}
    .pass {color: #8dffb8;}
    .fail {color: #ff9b9b;}
    .stages {display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 8px;}
    .stages div {background: #0e1c33; border-radius: 12px; padding: 10px 12px; color: #d5e2f3; font-size: 0.84rem; border: 1px solid #1d3e68;}
    .driver {margin: 6px 0;}
    .driver .bar {height: 8px; border-radius: 99px; background: #1d3e68; margin-top: 3px;}
    .driver .fill {height: 8px; border-radius: 99px;}
    .up {background: #d46565;}
    .down {background: #3DDC97;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def preview_case(name: str) -> DecisionResult:
    return run_decision(get_sample(name), use_llm=False, persist=False)


@st.cache_data(ttl=30)
def cached_llm_status() -> dict:
    return ollama_status()


def load_sample(sample_id: str) -> None:
    application = get_sample(sample_id)
    for key, value in to_form(application).items():
        st.session_state[key] = value
    st.session_state.result = run_decision(application, use_llm=False, persist=False)
    st.session_state.user_ran = False


def open_saved() -> None:
    run_id = st.session_state.get("history_pick")
    if not run_id:
        return
    payload = get_decision(run_id)
    if payload:
        st.session_state.result = DecisionResult.model_validate(payload)
        st.session_state.user_ran = True


if "result" not in st.session_state:
    st.session_state.result = preview_case("apex")
    st.session_state.user_ran = False

for key, value in to_form(get_sample("apex")).items():
    st.session_state.setdefault(key, value)

llm_status = cached_llm_status()
if "use_llm" not in st.session_state:
    st.session_state.use_llm = bool(llm_status.get("ok"))


def render_result(result: DecisionResult, saved: bool) -> None:
    kind = result.recommendation.lower()
    ratios = result.key_ratios
    cards = [
        ("PD score", result.pd_display),
        ("Risk grade", (result.risk_grade or "n/a").upper()),
        ("Debt/EBITDA", fmt_ratio(ratios.get("debt_to_ebitda"))),
        ("DSCR", fmt_ratio(ratios.get("dscr"))),
        ("Credit score", str(ratios.get("credit_score"))),
    ]
    card_html = "".join(
        f'<div class="metric"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>'
        for label, value in cards
    )
    icon = "✓" if result.recommendation == "APPROVE" else "•"
    why_html = "".join(f"<li>{icon} {html.escape(line)}</li>" for line in result.why)
    business = result.application.get("business_name", "")
    purpose = result.application.get("loan_purpose", "")
    amount = money(result.application.get("loan_amount"))
    st.markdown(
        f'<div class="banner {kind}"><span>Risk decision · {html.escape(business)}</span>{html.escape(result.recommendation)}</div>'
        f'<div class="metrics">{card_html}</div>',
        unsafe_allow_html=True,
    )
    st.caption(f"{amount} · {purpose}")
    cross = ""
    if result.ml_pd is not None:
        cross = f"Official PD is the policy scorecard. Local {result.ml_backend} cross-check: {fmt_pct(result.ml_pd)}."
    else:
        cross = "The scorecard did not produce a PD because the file could not be scored."
    if result.deployment_id:
        stamp = f"Written to PostgreSQL as {result.run_id} · deployment {result.deployment_id}."
    elif saved:
        stamp = f"Saved locally as {result.run_id}."
    else:
        stamp = "Preview — not written to the audit log."
    st.caption(f"{stamp} {cross} Completed in {result.elapsed_ms} ms.")
    if result.warnings:
        st.warning(" ".join(result.warnings))
    if result.errors:
        st.error(" ".join(result.errors))
    st.markdown("**Why?**")
    st.markdown(f'<ul class="why">{why_html}</ul>', unsafe_allow_html=True)
    st.markdown("**Explanation**")
    st.caption("The recommendation and the reason list come from the policy rules. This paragraph restates those facts.")
    st.text(result.explanation)
    st.caption(f"Explanation source: {result.explanation_source}")

    flow = "".join(
        f'<div class="step {html.escape(step["status"])}">{step["step"]}. {html.escape(step["short"])}</div>'
        for step in result.audit
    )
    st.markdown(f'<div class="flow">{flow}</div>', unsafe_allow_html=True)

    overview, agents, policy, audit = st.tabs(["Financial metrics", "Agents", "Policy evidence", "Audit trail"])
    with overview:
        metrics = result.metrics or {}
        labels = [
            ("Revenue", money(metrics.get("revenue"))),
            ("EBITDA", money(metrics.get("ebitda"))),
            ("EBITDA margin", fmt_pct(metrics.get("ebitda_margin"))),
            ("Pro forma debt", money(metrics.get("pro_forma_debt"))),
            ("New annual payment", money(metrics.get("proposed_annual_payment"))),
            ("Pro forma debt service", money(metrics.get("pro_forma_debt_service"))),
            ("Current ratio", fmt_ratio(metrics.get("current_ratio"))),
            ("Quick ratio", fmt_ratio(metrics.get("quick_ratio"))),
            ("Interest coverage", fmt_ratio(metrics.get("interest_coverage"))),
            ("Debt/Equity", fmt_ratio(metrics.get("debt_to_equity"))),
            ("Loan / EBITDA", fmt_ratio(metrics.get("loan_to_ebitda"))),
            ("Net income", money(metrics.get("net_income"))),
        ]
        grid = "".join(
            f'<div class="metric"><div class="label">{html.escape(label)}</div><div class="value" style="font-size:1.05rem">{html.escape(value)}</div></div>'
            for label, value in labels
        )
        st.markdown(f'<div class="metrics" style="grid-template-columns: repeat(3, 1fr)">{grid}</div>', unsafe_allow_html=True)
        active = [item for item in result.drivers if item["direction"] != "neutral"]
        st.markdown("**What moved the PD**")
        if not result.drivers:
            st.write("No scorecard factors were calculated.")
        elif not active:
            st.write("This file matches the reference low-risk profile, so the score stays at 3.8%.")
        else:
            peak = max(abs(item["logit"]) for item in active) or 1
            rows = []
            for item in sorted(active, key=lambda row: abs(row["logit"]), reverse=True):
                width = max(8, int(abs(item["logit"]) / peak * 100))
                tone = "up" if item["logit"] > 0 else "down"
                rows.append(
                    f'<div class="driver"><div>{html.escape(item["factor"])} · {html.escape(item["direction"])}</div>'
                    f'<div class="bar"><div class="fill {tone}" style="width:{width}%"></div></div></div>'
                )
            st.markdown("".join(rows), unsafe_allow_html=True)
    with agents:
        for agent in result.agents:
            st.markdown(f"**{agent['name']}** · {agent['role']} · {agent['status']} · {agent['duration_ms']} ms")
            st.text(agent["summary"])
    with policy:
        for check in result.policy_checks:
            mark = "pass" if check["passed"] else "fail"
            symbol = "✓" if check["passed"] else "✕"
            st.markdown(
                f'<div class="check-row"><span class="{mark}">{symbol}</span> {html.escape(check["message"])}</div>',
                unsafe_allow_html=True,
            )
        st.markdown("**Retrieved and cited passages**")
        for item in result.policy_evidence:
            score = f" · match {item['score']}" if item.get("score") is not None else ""
            st.markdown(f"**{item['origin']} · {item['source']} {item['section']}**{score}")
            st.text(item["excerpt"])
    with audit:
        for step in result.audit:
            st.markdown(f"**{step['step']}. {step['name']}** · {step['status']} · {step['at']}")
            st.text(step["detail"])
        st.download_button(
            "Download decision JSON",
            data=result.model_dump_json(indent=2),
            file_name=f"decision-{result.run_id}.json",
            mime="application/json",
            key=f"download-{result.run_id}-{int(saved)}",
        )


st.markdown(
    """
    <div class="hero">
      <div class="kicker">From data to decision · local desk</div>
      <h1>Agentic AI for Business Loan Decisioning</h1>
      <p>LLM, retrieval, specialist agents, and one orchestrator. Runs on this PC with free local tools. No paid API key.</p>
    </div>
    <div class="trio">
      <div><b>Business problem</b>Volume, manual analysis, inconsistent decisions, and policy that is hard to trace.</div>
      <div><b>This solution</b>Validate the file, retrieve policy, calculate ratios, score PD, then approve, review, or reject.</div>
      <div><b>What you get</b>A PD, a risk grade, the key ratios, the policy evidence, a memo, and an audit trail.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("**Local runtime**")
    st.toggle("Draft the memo with local Ollama", key="use_llm")
    if llm_status.get("ok"):
        models = ", ".join(llm_status.get("models") or []) or "no models pulled"
        st.success(f"Ollama is running. Models: {models}")
    else:
        st.info("Ollama is not running. Memos use the grounded template. Install Ollama and pull a model to draft locally.")
    manifest = release_manifest()
    st.caption(
        f"Release {manifest['app_version']} · policy {manifest['policy_version']} · {manifest['rag_corpus_version']}"
    )
    st.caption(f"Policy corpus: {len(get_index())} sections on this PC.")
    warehouse = postgres_status()
    if warehouse.get("ok"):
        st.success(f"PostgreSQL deployment {warehouse['deployment_id']}")
        st.caption(f"{warehouse['applications']} input files · {warehouse['decisions']} decisions")
        st.text_input("Warehouse application id", value="apex", key="pg_application_id")

        def _decide_stored() -> None:
            application_id = st.session_state.pg_application_id.strip()
            st.session_state.result = decide_stored(application_id, use_llm=bool(st.session_state.get("use_llm")))
            st.session_state.user_ran = True
            with connect() as connection:
                application = load_application(connection, application_id)
            for key, value in to_form(application).items():
                st.session_state[key] = value

        def _store_form_and_decide() -> None:
            application_id = st.session_state.pg_application_id.strip()
            st.session_state.result = land_and_decide(
                application_id,
                from_form(st.session_state),
                use_llm=bool(st.session_state.get("use_llm")),
            )
            st.session_state.user_ran = True

        st.button("Decide the stored file", on_click=_decide_stored, use_container_width=True)
        st.button("Store this form, then decide", on_click=_store_form_and_decide, use_container_width=True)
    else:
        st.caption("PostgreSQL warehouse is off. Set DATABASE_URL to land inputs and decisions there.")
    history = list_decisions(12)
    if history:
        st.selectbox(
            "Saved decisions",
            options=[row["run_id"] for row in history],
            format_func=lambda run_id: next(
                f"{row['recommendation']} · {row['business_name']}"
                for row in history
                if row["run_id"] == run_id
            ),
            key="history_pick",
        )
        st.button("Open saved decision", on_click=open_saved, use_container_width=True)
    if st.button("Clear saved decisions", use_container_width=True):
        clear_decisions()
        st.session_state.pop("history_pick", None)
        st.rerun()
    st.caption("API routes: /decide and /warehouse/applications/{id}/decide. Compose serves them on port 8010.")

def _loan_file_choices() -> list[str]:
    try:
        with connect() as connection:
            rows = connection.execute(
                "SELECT application_id FROM credit.loan_application ORDER BY application_id"
            ).fetchall()
    except Exception:
        return ["every file"]
    return ["every file", *[row["application_id"] for row in rows]]


def _show_query(page_name: str, question: str, application_id: str, remember: bool = False) -> None:
    try:
        st.session_state.sql_result = run_query(question, application_id=application_id)
        st.session_state.sql_file_used = application_id or "every file"
        st.session_state.sql_error = ""
    except Exception as exc:
        st.session_state.sql_result = None
        st.session_state.sql_error = str(exc)
    if remember:
        st.session_state[f"sql_ask_{page_name}"] = question


def _readable_rows(rows: list[dict]) -> tuple[list[dict], str]:
    if not rows:
        return rows, ""
    names = set(rows[0])
    if "why_json" in names or "drivers_json" in names:
        keep = [
            "application_id",
            "recommendation",
            "pd_display",
            "risk_grade",
            "debt_to_ebitda",
            "dscr",
            "credit_score",
            "created_at",
            "run_id",
        ]
        shown = [name for name in keep if name in names]
        return [{name: row.get(name) for name in shown} for row in rows], (
            "Showing the decision columns. The SQL above reads the full stored row."
        )
    return rows, ""


def show_sql_panel(page_name: str) -> None:
    st.markdown("**PostgreSQL query**")
    st.caption("Pick one loan file, or leave every file selected.")
    picked = st.selectbox("Loan file", _loan_file_choices(), key="sql_file_pick")
    application_id = "" if picked == "every file" else picked
    presets = (
        [
            ("Latest decision", "latest decision"),
            ("Checks", "check"),
            ("Evidence", "evidence"),
            ("Full file", "full file"),
        ]
        if page_name == "decision"
        else [
            ("Input load", "input load"),
            ("Schedule", "schedule"),
            ("Loan files", "loan application"),
            ("Latest decision", "latest decision"),
        ]
    )
    columns = st.columns(4)
    for column, (label, query) in zip(columns, presets):
        with column:
            if st.button(label, key=f"sql-preset-{page_name}-{label}", use_container_width=True):
                _show_query(page_name, query, application_id, remember=True)
    ask_key = f"sql_ask_{page_name}"
    st.text_input(
        "Table or SELECT",
        placeholder="latest decision, check, schedule, or SELECT * FROM credit.decision",
        key=ask_key,
    )
    if st.button("Show query and rows", key=f"sql-run-{page_name}"):
        _show_query(page_name, st.session_state.get(ask_key, ""), application_id)
    if st.session_state.get("sql_error"):
        st.error(st.session_state.sql_error)
    sql_result = st.session_state.get("sql_result")
    if sql_result:
        st.markdown("**Query result**")
        st.caption(f"Loan file: {st.session_state.get('sql_file_used', picked)}")
        st.code(sql_result["sql"], language="sql")
        if sql_result.get("note"):
            st.caption(sql_result["note"])
        shown, focus_note = _readable_rows(sql_result["rows"])
        if focus_note:
            st.caption(focus_note)
        st.caption(f"{sql_result['row_count']} rows")
        if shown:
            st.dataframe(shown, use_container_width=True)
        else:
            st.caption("No rows for that file.")


page = st.radio("Open", ["Load and schedule", "Decision"], horizontal=True, key="desk_page")
if page == "Load and schedule":
    st.markdown("**Initial load**")
    st.caption("Loads apex, harbor, and northwind, then the JSON files already in the project incremental folder.")
    st.text("\n".join(project_incremental_files()) or "No project incremental JSON files.")
    if st.button("Run initial load now", type="primary"):
        with st.spinner("Loading the first files into PostgreSQL..."):
            try:
                st.session_state.load_message = run_initial_load()
            except Exception as exc:
                st.session_state.load_message = str(exc)
    st.markdown("**Incremental files**")
    st.caption(r"Drop a new .json file in C:\Users\Raja Reddy\Desktop\credit-inbox")
    waiting = inbox_waiting()
    st.text("Waiting: " + (", ".join(waiting) if waiting else "none"))
    loaded = inbox_loaded()
    st.caption("Already loaded: " + (", ".join(loaded[-8:]) if loaded else "none"))
    if st.button("Run incremental load now", type="primary"):
        with st.spinner("Picking up inbox files, then scoring them..."):
            try:
                st.session_state.load_message = run_incremental_load()
            except Exception as exc:
                st.session_state.load_message = str(exc)
    st.markdown("**Schedule**")
    mode = st.selectbox(
        "When to run the incremental load",
        ["Manual only", "Every day", "One weekday", "One date and time", "Every few minutes"],
    )
    clock = st.time_input("Time", value=datetime.strptime("09:00", "%H:%M").time())
    on_date = None
    weekday = "Monday"
    every_minutes = 15
    if mode == "One date and time":
        on_date = st.date_input("Date")
    if mode == "One weekday":
        weekday = st.selectbox("Day", list(WEEKDAYS))
    if mode == "Every few minutes":
        every_minutes = st.number_input("Minutes between runs", min_value=1, max_value=1440, value=15, step=1)
    if st.button("Save schedule"):
        try:
            st.session_state.load_message = save_schedule(mode, clock, on_date, weekday, int(every_minutes))
        except Exception as exc:
            st.session_state.load_message = str(exc)
    if st.button("Show current schedule"):
        try:
            st.session_state.load_message = task_status()
        except Exception as exc:
            st.session_state.load_message = str(exc)
    if st.session_state.get("load_message"):
        st.text(st.session_state.load_message)
    show_sql_panel("load")
    st.stop()

show_sql_panel("decision")

left, right = st.columns([1.05, 1], gap="large")
with left:
    st.markdown("**Try a filed example**")
    buttons = st.columns(3)
    for column, item in zip(buttons, SAMPLE_CATALOG):
        with column:
            st.button(
                item["expectation"],
                key=f"sample-{item['id']}",
                on_click=load_sample,
                args=(item["id"],),
                use_container_width=True,
                help=f"{item['business']}. {item['note']}",
            )
            st.caption(item["business"])
    with st.form("loan-file"):
        st.markdown("**1 · Loan application**")
        a, b = st.columns(2)
        with a:
            st.text_input("Business name", key="business_name")
            st.selectbox("Industry", INDUSTRIES, key="industry")
            st.number_input("Years in business", min_value=0, max_value=150, step=1, key="years_in_business")
            st.text_input("Loan purpose", key="loan_purpose")
        with b:
            st.number_input("Loan amount", min_value=0.0, step=10000.0, format="%.2f", key="loan_amount")
            st.number_input("Term (years)", min_value=1, max_value=30, step=1, key="loan_term_years")
            st.number_input("Interest rate (%)", min_value=0.0, max_value=40.0, step=0.1, format="%.2f", key="interest_rate_pct")
            st.selectbox("Industry outlook", OUTLOOKS, key="industry_outlook")
        st.markdown("**2 · Financial statements**")
        c, d = st.columns(2)
        with c:
            st.number_input("Revenue", min_value=0.0, step=10000.0, format="%.2f", key="revenue")
            st.number_input("EBITDA", min_value=0.0, step=10000.0, format="%.2f", key="ebitda")
            st.number_input("Interest expense", min_value=0.0, step=1000.0, format="%.2f", key="interest_expense")
            st.number_input("Net income", step=1000.0, format="%.2f", key="net_income")
            st.number_input("Current assets", min_value=0.0, step=10000.0, format="%.2f", key="current_assets")
            st.number_input("Current liabilities", min_value=0.0, step=10000.0, format="%.2f", key="current_liabilities")
        with d:
            st.number_input("Cash", min_value=0.0, step=1000.0, format="%.2f", key="cash")
            st.number_input("Receivables", min_value=0.0, step=1000.0, format="%.2f", key="receivables")
            st.number_input("Total assets", min_value=0.0, step=10000.0, format="%.2f", key="total_assets")
            st.number_input("Existing debt", min_value=0.0, step=10000.0, format="%.2f", key="existing_debt")
            st.number_input("Equity", step=10000.0, format="%.2f", key="equity")
            st.number_input(
                "Existing annual debt service",
                min_value=0.0,
                step=1000.0,
                format="%.2f",
                key="existing_annual_debt_service",
                help="Principal and interest already on the books. The new loan payment is added on top.",
            )
        st.markdown("**3 · Credit bureau**")
        e, f = st.columns(2)
        with e:
            st.number_input("Credit score", min_value=300, max_value=850, step=1, key="credit_score")
            st.number_input("Delinquencies in 12 months", min_value=0, max_value=20, step=1, key="delinquencies_12m")
        with f:
            st.checkbox("Bankruptcy on file", key="bankruptcy")
        st.markdown("**4 · Internal bank data**")
        g, h = st.columns(2)
        with g:
            st.number_input("Relationship (years)", min_value=0, max_value=80, step=1, key="relationship_years")
            st.number_input("Deposit balance", min_value=0.0, step=1000.0, format="%.2f", key="deposit_balance")
        with h:
            st.checkbox("Prior loans are current", key="prior_loans_current")
        st.markdown("**5 · Market**")
        st.number_input("Revenue growth (%)", min_value=-50.0, max_value=100.0, step=0.5, format="%.2f", key="revenue_growth_pct")
        st.text_area("Officer request", key="analyst_request", height=70)
        submitted = st.form_submit_button("Run decision", type="primary", use_container_width=True)

with right:
    if submitted:
        try:
            application = from_form(st.session_state)
            with st.spinner("Data, policy retrieval, ratios, PD, policy rules, then the decision..."):
                st.session_state.result = run_decision(
                    application,
                    use_llm=bool(st.session_state.get("use_llm")),
                    persist=True,
                )
                st.session_state.user_ran = True
        except Exception as exc:
            st.error(f"The file could not be scored: {exc}")
    result = st.session_state.get("result")
    if result is not None:
        render_result(result, bool(st.session_state.get("user_ran")))

st.markdown(
    """
    <div class="stages">
      <div><b>1 · LLM</b><br>Reads the officer request and writes the memo. Ollama if it is running, otherwise a grounded template.</div>
      <div><b>2 · RAG</b><br>Retrieves credit policy, risk policy, lending guidelines, regulatory notes, and past decisions from disk.</div>
      <div><b>3 · Agents</b><br>Data validates. Finance calculates. Risk scores PD. Policy tests the rules.</div>
      <div><b>4 · Orchestrator</b><br>One shared case, one route, one recommendation: approve, review, or reject.</div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown("**Operator**")
st.caption("Ask in plain language. The operator runs the system and stores each turn in credit.operator_log.")
if "operator_chat" not in st.session_state:
    st.session_state.operator_chat = []
for turn in st.session_state.operator_chat:
    with st.chat_message(turn["role"]):
        st.text(turn["content"])
prompt = st.chat_input("Monitor the process, list files, score apex, or explain harbor")
if prompt:
    st.session_state.operator_chat.append({"role": "user", "content": prompt})
    with st.spinner("Operator is checking the system..."):
        answer = ask(prompt)
    spoken = f"{answer['reply']}\n\nTool: {answer['tool']} · {answer['source']}"
    st.session_state.operator_chat.append({"role": "assistant", "content": spoken})
    st.rerun()

st.caption(
    "Decision support only. A credit officer owns the final call. "
    "The scorecard is a local demo model, not a regulatory capital model. "
    "Race, sex, religion, national origin, age, and marital status are not inputs."
)
