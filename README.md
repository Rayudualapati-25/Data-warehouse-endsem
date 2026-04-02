# Autonomous SQL Agent Data Warehouse (Baseline)

This repository now includes a baseline implementation for:

- Data warehouse schema (`agentic_ai_db.sql`)
- Reproducible ETL pipeline (`etl/`)
- Validation SQL pack (`sql/validations/`)
- Phase 4 API baseline (`api/`, `agent/`)

## Repository Structure

```text
project/
  adapters/
    base.py
    postgres.py
    sqlite.py
    mysql.py
  metadata/
    schema_cache/
    semantic_maps/
    plan_sql_cache.json
    query_traces.jsonl
  data/
    raw/
    processed/
  etl/
    extract.py
    transform.py
    load.py
    pipeline.py
  agent/
    prompts/
  mining/
  evaluation/
  api/
  sql/
    validations/
    benchmarks/
  tests/
    unit/
    integration/
  docs/
  agentic_ai_db.sql
  data.csv
  final_plan.md
```

## ETL Cleaning Rules

Rows are accepted only if all rules pass:

- `CustomerID` is present
- `Quantity > 0`
- `UnitPrice > 0`
- `InvoiceDate` parses using format `M/d/yyyy H:mm`

## Python Requirements

- Python 3.10+
- `psycopg` (recommended) or `psycopg2`

Install one PostgreSQL driver:

```bash
pip install psycopg[binary]
```

or

```bash
pip install psycopg2-binary
```

Install API dependencies:

```bash
pip install -r requirements.txt
```

## Database Setup

Run the schema before the first load:

```sql
\i agentic_ai_db.sql
```

## Run ETL

Set DB environment variables in either way:

- `DB_HOST` (required)
- `DB_PORT` (default: `5432`)
- `DB_NAME` (required)
- `DB_USER` (required)
- `DB_PASSWORD` (required)

Option A:
- Add them in `.env` at project root (auto-loaded by `etl/pipeline.py`)

Option B:
- Export them in your shell session

Run pipeline:

```bash
python etl/pipeline.py --input data.csv --processed-dir data/processed
```

Outputs:

- `data/processed/clean_sales.csv`
- `data/processed/rejected_sales.csv`
- Console ETL metrics and load counts

## Validation Queries

Run:

```sql
\i sql/validations/01_row_count_and_revenue.sql
\i sql/validations/02_dimension_counts.sql
\i sql/validations/03_data_quality_assertions.sql
\i sql/validations/04_top_countries_revenue.sql
\i sql/validations/05_monthly_revenue_check.sql
```

Expected values for the current `data.csv` are documented in:

- `sql/validations/EXPECTED_OUTPUTS.md`

## Phase 4 API (Baseline)

Run API:

```bash
uvicorn api.main:app --reload
```

Hugging Face Inference API configuration (required):

- `HF_TOKEN=hf_your_token_here`
- `HF_MODEL=mistralai/Mistral-7B-Instruct-v0.3` (default)
- `HF_TIMEOUT_SEC=30` (default)
- `HF_PLANNER_ENABLED=1` (default)

Planner uses Hugging Face Inference API. If HF_TOKEN is missing or planner is disabled, `/analyze` returns an error.

Endpoints:

- `GET /health`
- `POST /dataset/onboard`
- `POST /dataset/upload`
- `GET /dataset/list`
- `GET /dataset/{dataset_id}/metadata`
- `POST /dataset/{dataset_id}/refresh`
- `POST /dataset/{dataset_id}/ingest`
- `GET /dataset/{dataset_id}/ingest/status`
- `POST /analyze`
- `POST /analyze/debug`
- `POST /analyze/report`
- `POST /mining/refresh`
- `GET /evaluation/metrics`
- `GET /evaluation/failures`

`/analyze` response includes:

- `trace_id` (request-level observability ID)
- `planner_source` (`huggingface`)
- `retries_used` (0 or 1)

Structured report endpoint:

```bash
curl -X POST "http://127.0.0.1:8000/analyze/report" \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"show trend analysis\"}"
```

Optional HF-based insight narration for `/analyze/report`:

- `INSIGHT_MODEL_ENABLED=1`
- `INSIGHT_MODEL=mistralai/Mistral-7B-Instruct-v0.3` (optional, falls back to `HF_MODEL`)

When enabled, LLM-generated insights are accepted only if evidence keys map to actual computed values; otherwise API falls back to deterministic insights.

Example request:

```bash
curl -X POST "http://127.0.0.1:8000/analyze" \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"Top 5 countries by revenue\",\"row_limit\":5}"
```

Dataset onboarding and metadata introspection:

```bash
curl -X POST "http://127.0.0.1:8000/dataset/onboard" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"retail-public\",\"db_engine\":\"postgres\",\"schema_name\":\"public\"}"

curl "http://127.0.0.1:8000/dataset/list"
curl "http://127.0.0.1:8000/dataset/<dataset_id>/metadata"
curl -X POST "http://127.0.0.1:8000/dataset/<dataset_id>/refresh"
```

File dataset flow (ingest + introspect):

```bash
curl -X POST "http://127.0.0.1:8000/dataset/upload" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"student-scores\",\"file_path\":\"C:/data/student_scores.csv\"}"

curl -X POST "http://127.0.0.1:8000/dataset/<dataset_id>/ingest"
curl "http://127.0.0.1:8000/dataset/<dataset_id>/ingest/status"
curl "http://127.0.0.1:8000/dataset/<dataset_id>/metadata"
```

Use `dataset_id` in analysis requests to provide schema metadata context:

```bash
curl -X POST "http://127.0.0.1:8000/analyze" \
  -H "Content-Type: application/json" \
  -d "{\"dataset_id\":\"<dataset_id>\",\"question\":\"top countries by revenue\"}"
```

Semantic map is persisted per dataset in `metadata/semantic_maps/` and used to rank entity/measure/time candidates.

Structured planner output (internal contract) now includes:

- `task_type`
- `entity_scope`
- `entity_dimension`
- `n`
- `metric`
- `time_grain`
- `compare_against`

SQL generation now supports HF Inference API + repair loop:

- `SQL_LLM_ENABLED=1`
- `SQL_REPAIR_MAX_RETRIES=2`
- `SQL_MODEL` (optional, falls back to `HF_MODEL`)
- `SQL_PROMPT_VERSION=v1`
- `PLANNER_PROMPT_VERSION=v1`
- `INSIGHT_PROMPT_VERSION=v1`
- `DB_ENGINE=postgres` (or `sqlite`/`mysql` for adapter-based paths)

Domain-agnostic mining (Phase 8 MVP):

- Mining now uses a schema-aware `feature_builder(schema, plan)` (`mining/feature_builder.py`).
- Trend and segmentation snapshots can be dataset-scoped (`dataset_id` + plan scope key).
- For trend requests with `top_n` + `compare_against=global`, snapshot payload can include scoped and global trend evidence.

Runtime metadata/cache artifacts:

- `metadata/schema_cache/` stores introspected schema snapshots with `schema_hash`.
- `metadata/plan_sql_cache.json` stores cached plan-to-SQL mappings (schema-hash keyed).
- `metadata/query_traces.jsonl` stores request traces (planner/sql/execution/insight stages).

PostgreSQL metadata backend (recommended):

- `METADATA_BACKEND=postgres` to store datasets/metadata/cache/traces in DB tables.
- `METADATA_BACKEND=file` to force local JSON files.
- `METADATA_BACKEND=auto` (default): uses postgres when DB env vars are present.

Create metadata tables:

```bash
psql -U $DB_USER -d $DB_NAME -f migrations/001_agent_metadata.sql
```

Or apply with `.env` auto-load:

```bash
python -m metadata.apply_metadata_migration
```

Migrate existing file metadata to PostgreSQL:

```bash
python -m metadata.migrate_to_postgres --pretty
```

Evaluation metrics API:

```bash
curl "http://127.0.0.1:8000/evaluation/metrics?limit=1000"
curl "http://127.0.0.1:8000/evaluation/failures?limit=5000"
```

Run 3-dataset evaluation campaign (mock harness):

```bash
python -m evaluation.run_campaign --pretty
```

Run 3-dataset live evaluation campaign:

```bash
python -m evaluation.run_campaign --mode live --datasets-file evaluation/live_datasets.json --api-base-url http://127.0.0.1:8000 --pretty
```

Outputs:
- `docs/evaluation_report.json`
- `docs/evaluation.md`

Run PostgreSQL benchmark suite (`EXPLAIN ANALYZE`):

```bash
python -m evaluation.benchmark_runner --pretty
```

Outputs:
- `docs/benchmark_report.json`
- `docs/benchmark_report.md`

## Phase 5 Mining Modules

Run trend analysis:

```bash
python -m mining.trend --pretty
```

Build RFM features:

```bash
python -m mining.rfm --pretty
```

Run clustering:

```bash
python -m mining.clustering --k 4 --pretty
```

Refresh mining snapshots (precompute/cache):

```bash
python -m mining.snapshots --all --pretty
```

Read one snapshot (auto-refresh if stale):

```bash
python -m mining.snapshots --type trend_analysis --pretty
python -m mining.snapshots --type customer_segmentation --pretty
```

Snapshot cache behavior in API:

- For mining intents (`trend_analysis`, `customer_segmentation`), `/analyze` serves from `mining_snapshots`.
- If snapshot is missing or stale, API recomputes and updates snapshot automatically.
- Staleness TTL can be configured with `MINING_SNAPSHOT_TTL_HOURS` (default: `24`).
- Each snapshot includes `snapshot_version` and `run_id` for traceability.

Refresh snapshots from API:

```bash
curl -X POST "http://127.0.0.1:8000/mining/refresh" -H "Content-Type: application/json" -d "{\"refresh_all\":true}"
curl -X POST "http://127.0.0.1:8000/mining/refresh" -H "Content-Type: application/json" -d "{\"snapshot_type\":\"trend_analysis\",\"refresh_all\":false}"
```
