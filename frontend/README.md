# Demo Frontend

A single-page HTML/CSS/JS app that talks to the Autonomous SQL Agent API.

## Run the demo

**Terminal 1 — start the API:**
```bash
cd Data-warehouse-endsem
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

**Terminal 2 — serve the frontend:**
```bash
cd Data-warehouse-endsem/frontend
python3 -m http.server 5173
```

Then open: http://localhost:5173

## What it shows

- **Health indicator** (top-right green dot) — confirms API is reachable
- **Dataset selector** — pick a registered dataset, or use built-in schema
- **Question input** with example chips (Cmd/Ctrl+Enter to submit)
- **Generated SQL** with copy button
- **Results table** — query output
- **Pipeline metrics** — status, rows, retries, cache hit, planner source
- **Debug trace** — full debug payload (toggle on/off)

## Demo flow for presentation

1. Open the app — show the green API status dot.
2. Click an example chip ("Top 10 customers by revenue").
3. Hit **Run Analysis** — show the live spinner.
4. Walk through the result:
   - **Generated SQL** (LLM output)
   - **Results table** (executed query)
   - **Metrics** (timing, retries, cache)
   - **Debug trace** (full pipeline state)
5. Toggle datasets to show schema-aware planning.

## API endpoints used

- `GET /health` — status check
- `GET /dataset/list` — populate dataset dropdown
- `POST /analyze/debug` — main analysis call (with debug data)
- `POST /analyze` — analysis without debug

CORS is enabled on the API to allow cross-origin calls from the static frontend.
