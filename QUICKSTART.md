# Quickstart — Demo Submission

This is the fast path to run the project end-to-end for a presentation/demo.
Total time: ~2 minutes from clone to working demo.

## Prerequisites

- Python 3.11+
- A free Groq API key from https://console.groq.com/keys

## One-command demo

```bash
./start_demo.sh
```

This script does everything:
1. Verifies `.env` exists (errors if missing)
2. Creates a Python venv if needed
3. Installs all dependencies
4. Seeds a SQLite demo database (4,500 sales rows)
5. Starts the FastAPI server on port 8000
6. Onboards the demo dataset
7. Starts the static frontend on port 5173

Open: **http://localhost:5173**

## Manual setup (if you prefer)

```bash
# 1. Create .env
cp .env.example .env
# Edit .env and paste your GROQ_API_KEY

# 2. Install
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Seed the demo database
.venv/bin/python scripts/seed_sqlite_demo.py

# 4. Start API
.venv/bin/uvicorn api.main:app --port 8000

# 5. Onboard the dataset (one-time, in another terminal)
curl -X POST http://localhost:8000/dataset/onboard \
  -H "Content-Type: application/json" \
  -d '{"name":"demo_sales","db_engine":"sqlite","schema_name":"main","source_config":{"db_path":"data/demo.sqlite"}}'

# 6. Start the frontend (third terminal)
cd frontend && python3 -m http.server 5173
```

## Demo flow for presentation

1. Open **http://localhost:5173**
2. Confirm the **green API status dot** (top-right)
3. Pick **demo_sales** from the dataset dropdown
4. Click an example chip — e.g. **"Top 10 customers by revenue"**
5. Click **Run Analysis**
6. Walk through the result:
   - **Generated SQL** — the LLM-generated query (with CTEs, JOINs, etc.)
   - **Results table** — actual rows from SQLite
   - **Metrics card** — status, rows, retries, cache hit, planner source
   - **Debug trace** — full pipeline state with planner intent, prompt versions

## What's running

| Component | Port | URL |
|---|---|---|
| Frontend (HTML/CSS/JS) | 5173 | http://localhost:5173 |
| FastAPI backend | 8000 | http://localhost:8000 |
| API docs (Swagger) | 8000 | http://localhost:8000/docs |
| Database | — | SQLite file at `data/demo.sqlite` |
| LLM | — | Groq `llama-3.3-70b-versatile` (cloud) |

## Architecture (what to highlight)

```
┌────────────────┐
│   Frontend     │  Vanilla HTML/CSS/JS
│   (port 5173)  │
└───────┬────────┘
        │ HTTP/JSON (CORS-enabled)
┌───────▼─────────────────────────────────────────┐
│              FastAPI (port 8000)                 │
│  ┌────────┐  ┌────────────┐  ┌─────────────┐   │
│  │Planner │→ │SQL Generator│→ │  Executor   │   │
│  │(Groq)  │  │   (Groq)    │  │ (Adapters)  │   │
│  └────────┘  └────────────┘  └──────┬──────┘   │
│       ↓             ↓                ↓          │
│  ┌──────────────────────────────────────────┐  │
│  │  Evaluator → Insight LLM → Mining        │  │
│  └──────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────┘
                           │
                  ┌────────▼────────┐
                  │  SQLite / PG /  │
                  │     MySQL        │
                  └─────────────────┘
```

## Run the test suite

```bash
.venv/bin/pytest tests/
# 20 tests, all should pass
```

## Switch from SQLite to PostgreSQL (optional)

In `.env`:
```
DB_ENGINE=postgres
DB_HOST=localhost
DB_NAME=agentic_ai_db
DB_USER=youruser
DB_PASSWORD=yourpass
```

Then load the schema with `psql < agentic_ai_db.sql`.

## Try these example queries

| Question | Intent |
|---|---|
| Show top 10 customers by total revenue | `top_customers` |
| Total revenue grouped by country | `country_revenue` |
| Top 5 products by revenue | `top_products` |
| Monthly revenue trend over the last year | `monthly_revenue` |
| Revenue by product category | `generic_sales_summary` |

## Troubleshooting

**"GROQ_API_KEY is required"** — Add your key to `.env`.

**"Generated SQL uses non-allowlisted table"** — Pick a dataset from the dropdown. Without a dataset, the LLM hallucinates table names.

**"Address already in use"** — `lsof -ti:8000 | xargs kill -9` then restart.

**Frontend says "API offline"** — Make sure uvicorn is running on the same port the frontend expects (8000 by default).
