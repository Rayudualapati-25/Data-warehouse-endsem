from fastapi.testclient import TestClient

from agent.planner import Plan
from api.main import app


def test_dataset_upload_endpoint(monkeypatch):
    client = TestClient(app)

    def fake_register_uploaded_dataset(name: str, file_path: str, description=None):
        assert name == "scores"
        assert file_path.endswith(".csv")
        return {
            "dataset": {
                "dataset_id": "ds-1",
                "name": name,
                "source_type": "file_upload",
                "schema_name": "raw_ds1",
                "status": "uploaded",
            }
        }

    monkeypatch.setattr("api.routes.register_uploaded_dataset", fake_register_uploaded_dataset)
    response = client.post("/dataset/upload", json={"name": "scores", "file_path": "C:/tmp/scores.csv"})
    assert response.status_code == 200
    body = response.json()
    assert body["dataset"]["dataset_id"] == "ds-1"
    assert body["dataset"]["status"] == "uploaded"


def test_dataset_ingest_endpoint(monkeypatch):
    client = TestClient(app)

    def fake_run_ingestion(dataset_id: str):
        assert dataset_id == "ds-2"
        return {
            "dataset": {"dataset_id": "ds-2", "status": "ready"},
            "ingest_result": {"row_count_inserted": 10},
            "quality_report": {"status": "ok"},
            "metadata_profile": {"table_count": 1},
        }

    monkeypatch.setattr("api.routes.run_ingestion", fake_run_ingestion)
    response = client.post("/dataset/ds-2/ingest")
    assert response.status_code == 200
    body = response.json()
    assert body["dataset"]["status"] == "ready"
    assert body["ingest_result"]["row_count_inserted"] == 10


def test_analyze_blocks_file_dataset_without_metadata(monkeypatch):
    client = TestClient(app)

    monkeypatch.setattr("api.routes.load_schema_metadata", lambda dataset_id: None)
    monkeypatch.setattr(
        "api.routes.get_ingestion_status",
        lambda dataset_id: {"dataset": {"dataset_id": dataset_id, "source_type": "file_upload", "status": "uploaded"}},
    )

    response = client.post("/analyze", json={"dataset_id": "ds-x", "question": "top 5 countries by revenue"})
    assert response.status_code == 400
    assert "ingest first" in response.json()["detail"].lower()


def test_analyze_sql_repair_loop(monkeypatch):
    client = TestClient(app)
    metadata = {
        "tables": [{"table_name": "records", "columns": [{"column_name": "country"}, {"column_name": "amount"}]}],
        "entities": [{"table": "records", "column": "country"}],
        "measures": [{"table": "records", "column": "amount"}],
        "time_columns": [],
        "relationships": [],
    }

    monkeypatch.setattr("api.routes.load_schema_metadata", lambda dataset_id: metadata)
    monkeypatch.setattr(
        "api.routes.build_plan",
        lambda question, dataset_metadata=None: Plan(
            question=question,
            requires_mining=False,
            intent="country_revenue",
            planner_source="huggingface",
            task_type="sql_retrieval",
            entity_scope="top_n",
            entity_dimension="country",
            n=5,
            metric="amount",
            time_grain=None,
            compare_against="none",
        ),
    )

    sql_calls = {"count": 0}

    def fake_generate_sql_from_plan(question, plan, dataset_metadata, previous_sql=None, error_message=None):
        if previous_sql is None:
            return 'SELECT "country", SUM("amount") AS value FROM "records" GROUP BY 1 ORDER BY value DESC'
        return 'SELECT "country", SUM("amount") AS value FROM "records" GROUP BY 1 ORDER BY value DESC LIMIT 5'

    def fake_execute_safe_query(sql, row_limit=100, timeout_ms=15000):
        sql_calls["count"] += 1
        if sql_calls["count"] == 1:
            raise RuntimeError("syntax error near LIMIT")
        return [{"country": "A", "value": 100}]

    monkeypatch.setattr("api.routes.generate_sql_from_plan", fake_generate_sql_from_plan)
    monkeypatch.setattr("api.routes.execute_safe_query", fake_execute_safe_query)
    monkeypatch.setattr("api.routes.classify_sql_error", lambda exc: "syntax_error")

    response = client.post("/analyze/debug", json={"dataset_id": "ds-ok", "question": "top 5 countries by revenue"})
    assert response.status_code == 200
    body = response.json()
    assert body["retries_used"] == 1
    assert body["rows"][0]["country"] == "A"
    assert body["debug"]["plan"]["entity_scope"] == "top_n"

