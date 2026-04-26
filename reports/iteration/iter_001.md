# Iteration 001 - Local Demo Runtime Verification

Date: 2026-04-26

## Scope

Verified that the local demo can run from the current checkout using the documented FastAPI backend, static frontend, Groq-backed planner/SQL generation, and SQLite demo dataset.

## What Worked

- The automated Python test suite passed: 20 passed.
- `start_demo.sh` now clears stale local demo processes on the configured API and frontend ports.
- The launcher writes `frontend/config.js`, so the frontend uses the actual API base URL selected by the startup script.
- The API health endpoint returned `{"status":"ok"}` on `http://127.0.0.1:8000/health`.
- The frontend served successfully on `http://127.0.0.1:5173/`.
- The registered `demo_sales` SQLite dataset was available with status `ready`.
- A live `/analyze/debug` request for `Show top 10 customers by total revenue` returned evaluator status `ok`, 10 rows, and no retries.

## What Failed Or Was Weak

- Before this iteration, port `8000` was held by a stale `uvicorn api.main:app --reload --port 8000` process that did not respond to `/health`.
- Before this iteration, port `5173` was already occupied by an existing static frontend server.
- The frontend previously assumed the API was always on `http://localhost:8000`, which made alternate-port launches fragile.
- The full analysis path still depends on a valid `GROQ_API_KEY`; this is an external service dependency and should be documented as a runtime assumption.

## Evidence

- Run record: `experiments/runs/local_demo_smoke_20260426T092105Z.json`
- Summary table: `results/tables/local_demo_smoke_20260426T092105Z.csv`
- Query trace was appended by the API under `metadata/query_traces.jsonl`.

## Next Experiment Or Refinement

Add an automated smoke-test command that can be run in CI or before demos to verify health, dataset registration, and one deterministic no-LLM endpoint. Keep the live Groq analysis smoke test as an optional check because it depends on network access and API quota.
