# Agentic AI for Business Loan Decisioning

Local credit desk for a business loan file. It follows the architecture in the diagram: language understanding, retrieval over internal policy, specialist agents, and one orchestrator that returns an approve, review, or reject decision.

Everything runs on this PC. There is no paid API key. If [Ollama](https://ollama.com) is installed, the memo is drafted by a local model. If it is not, the same facts are written from the policy result.

This is decision support for a demo book of business. It is not a validated capital model and it does not replace a credit officer.

## What it decides

The Apex Manufacturing sample is built to match the sample output on the diagram:

| Field | Result |
| --- | --- |
| Recommendation | APPROVE |
| PD | 3.8% |
| Risk grade | Low |
| Debt/EBITDA | 2.0x |
| DSCR | 1.62x |
| Credit score | 720 |

Harbor Logistics goes to review because PD is above the 5% straight-through gate and no hard stop is hit. Northwind Retail is declined on hard stops.

## How the pieces map

| In the diagram | In this build |
| --- | --- |
| LLM | Ollama on `127.0.0.1:11434`, or a grounded template |
| RAG / vector store | Local TF-IDF index over the policy files in `04_rag_policy/knowledge` |
| Data, financial, risk, policy, decision agents | Python agents sharing one case file |
| Orchestrator | A small local agent graph in `app/orchestrator.py` |
| PD model | Explainable scorecard, with XGBoost as a cross-check only |
| Database | PostgreSQL schema `credit` when `DATABASE_URL` is set. SQLite remains the desk log |
| API and desk | FastAPI and Streamlit |

The scorecard is the official PD. The gradient model is trained on a synthetic book drawn from that scorecard and cannot override the policy decision.

## Run the desk

From this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m streamlit run 09_desk\ui.py
```

Or:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Optional local model:

```powershell
ollama pull llama3.2
```

Leave Ollama running, then turn on "Draft the memo with local Ollama" in the desk. The recommendation still comes from the policy rules.

## Run the API

```powershell
.\.venv\Scripts\python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs`.

Score a built-in file:

```powershell
curl -X POST "http://127.0.0.1:8000/decide/sample/apex"
```

## Check the three outcomes

```powershell
.\.venv\Scripts\python -m unittest tests.test_pipeline
.\.venv\Scripts\python -m app
```

## Policy the engine actually applies

Straight-through approval needs PD below 5%, pro forma Debt/EBITDA below 3.0x, DSCR above 1.25x, credit score at least 680, current ratio at least 1.20x, at least 3 years in business, no recent delinquency, no bankruptcy, and current prior loans.

Hard stops include PD at or above 15%, Debt/EBITDA above 4.0x, DSCR below 1.10x, credit score below 620, and a bankruptcy flag. The full list is in `app/policy_rules.py` and the citation text is in `04_rag_policy/knowledge`.

The model does not use race, sex, religion, national origin, age, or marital status.

## Production warehouse

PostgreSQL is the system of record. The desk can still run without it.

| Layer | What it does | Where |
| --- | --- | --- |
| Data engineering | Lands five source tables, assembles one loan file, publishes the decision | `app/data_engineering/warehouse.py` |
| ML | Scorecard is the official PD. XGBoost is a versioned cross-check | `app/pd_model.py` |
| GenAI | Ollama writes the memo from the decided facts | `app/llm.py` |
| RAG | TF-IDF over the versioned policy corpus | `app/rag.py`, `04_rag_policy/knowledge` |
| Agents | Data, knowledge, financial, risk, policy, orchestrator, decision | `app/agents.py` |

Input tables, one per source system: `credit.loan_application`, `credit.financial_statement`, `credit.credit_bureau`, `credit.bank_relationship`, `credit.market_observation`.

Output tables: `credit.feature_record`, `credit.decision`, `credit.decision_check`, `credit.decision_evidence`, `credit.decision_audit`. `credit.latest_decision` is the latest outcome per file.

Every decision stores a deployment id. That id changes when the app version, policy version, scorecard version, model version, or the policy-file hash changes. Versions are in `app/platform/release.py`. Schema changes are files in `01_database/migrations` and are applied once.

Start the database, API, and desk:

```powershell
docker compose up --build
```

API: `http://127.0.0.1:8010/docs`. Desk: `http://127.0.0.1:8502`. The database is on host port `5436` so it does not collide with another PostgreSQL already on `5432`.

The three sample files are loaded as application ids `apex`, `harbor`, and `northwind` the first time the warehouse starts.

```powershell
curl -X POST "http://127.0.0.1:8010/warehouse/applications/apex/decide"
```

To point a local API at the database without Docker for the app itself:

```powershell
$env:DATABASE_URL = "postgresql://credit:credit@localhost:5436/credit"
$env:PD_ENV = "local"
.\.venv\Scripts\python -m uvicorn app.api:app --host 127.0.0.1 --port 8011
```

`GET /release` returns the version manifest. `GET /health` includes the PostgreSQL deployment id.
