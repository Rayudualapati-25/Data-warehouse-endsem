from agent.planner import Plan
from mining.feature_builder import feature_builder


def _base_metadata():
    return {
        "tables": [
            {
                "table_name": "records",
                "columns": [
                    {"column_name": "country", "data_type": "text"},
                    {"column_name": "event_date", "data_type": "date"},
                    {"column_name": "amount", "data_type": "numeric"},
                ],
            }
        ],
        "entities": [{"table": "records", "column": "country"}],
        "measures": [{"table": "records", "column": "amount"}],
        "time_columns": [{"table": "records", "column": "event_date"}],
        "relationships": [],
    }


def test_feature_builder_trend_topn(monkeypatch):
    plan = Plan(
        question="top 5 countries trend",
        requires_mining=True,
        intent="trend_analysis",
        planner_source="groq",
        task_type="trend_analysis",
        entity_scope="top_n",
        entity_dimension="country",
        n=5,
        metric="amount",
        time_grain="month",
        compare_against="global",
    )

    captured = {}

    def fake_execute(sql, row_limit=100, timeout_ms=1000, db_engine=None, source_config=None):
        captured["sql"] = sql
        return [{"period_start": "2024-01-01", "entity_key": "A", "metric_value": 10.0}]

    monkeypatch.setattr("mining.feature_builder.execute_safe_query", fake_execute)

    built = feature_builder(_base_metadata(), plan, db_engine="postgres")
    assert built["status"] == "ok"
    assert "top_entities" in built["sql"].lower()
    assert len(built["rows"]) == 1


def test_feature_builder_segmentation(monkeypatch):
    plan = Plan(
        question="segment customers",
        requires_mining=True,
        intent="customer_segmentation",
        planner_source="groq",
        task_type="segmentation",
        entity_scope="all",
        entity_dimension="country",
        n=None,
        metric="amount",
        time_grain="month",
        compare_against="none",
    )

    def fake_execute(sql, row_limit=100, timeout_ms=1000, db_engine=None, source_config=None):
        return [{"entity_id": "A", "recency_days": 2, "frequency": 10, "monetary": 123.4}]

    monkeypatch.setattr("mining.feature_builder.execute_safe_query", fake_execute)
    built = feature_builder(_base_metadata(), plan, db_engine="postgres")
    assert built["status"] == "ok"
    assert "entity_rollup" in built["sql"].lower()
    assert built["rows"][0]["entity_id"] == "A"
