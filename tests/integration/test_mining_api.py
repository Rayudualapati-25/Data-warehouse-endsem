from fastapi.testclient import TestClient

from agent.planner import Plan
from api.main import app


def test_analyze_mining_uses_snapshot(monkeypatch):
    client = TestClient(app)

    def fake_build_plan(_question: str, dataset_metadata=None) -> Plan:
        return Plan(
            question="show trend analysis",
            requires_mining=True,
            intent="trend_analysis",
            planner_source="huggingface",
        )

    def fake_get_snapshot(snapshot_type: str, refresh_if_stale: bool = True):
        assert snapshot_type == "trend_analysis"
        return {
            "snapshot_type": "trend_analysis",
            "snapshot_json": {"trend": {"status": "ok"}, "monthly_revenue": []},
            "source_max_date": "2011-12-09",
            "snapshot_version": 3,
            "run_id": "run-abc-123",
            "generated_at": "2026-02-22T06:10:00+00:00",
            "refreshed": False,
        }

    monkeypatch.setattr("api.routes.build_plan", fake_build_plan)
    monkeypatch.setattr("api.routes.get_snapshot", fake_get_snapshot)

    response = client.post("/analyze", json={"question": "show trend analysis"})
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "trend_analysis"
    assert body["planner_source"] == "huggingface"
    assert body["sql"] == "-- mining snapshot retrieval"
    assert body["rows"][0]["snapshot_version"] == 3
    assert body["rows"][0]["run_id"] == "run-abc-123"


def test_refresh_mining_single(monkeypatch):
    client = TestClient(app)

    def fake_refresh_snapshot(snapshot_type: str):
        return {
            "snapshot_type": snapshot_type,
            "snapshot_json": {"ok": True},
            "source_max_date": "2011-12-09",
            "snapshot_version": 7,
            "run_id": "run-xyz",
            "generated_at": "2026-02-22T06:11:00+00:00",
            "refreshed": True,
        }

    monkeypatch.setattr("api.routes.refresh_snapshot", fake_refresh_snapshot)

    response = client.post("/mining/refresh", json={"snapshot_type": "trend_analysis", "refresh_all": False})
    assert response.status_code == 200
    body = response.json()
    assert len(body["refreshed"]) == 1
    assert body["refreshed"][0]["snapshot_type"] == "trend_analysis"
    assert body["refreshed"][0]["snapshot_version"] == 7


def test_refresh_mining_all(monkeypatch):
    client = TestClient(app)

    def fake_refresh_all():
        return [
            {
                "snapshot_type": "customer_segmentation",
                "snapshot_json": {"ok": True},
                "source_max_date": "2011-12-09",
                "snapshot_version": 2,
                "run_id": "run-a",
                "generated_at": "2026-02-22T06:12:00+00:00",
                "refreshed": True,
            },
            {
                "snapshot_type": "trend_analysis",
                "snapshot_json": {"ok": True},
                "source_max_date": "2011-12-09",
                "snapshot_version": 4,
                "run_id": "run-b",
                "generated_at": "2026-02-22T06:12:01+00:00",
                "refreshed": True,
            },
        ]

    monkeypatch.setattr("api.routes.refresh_all", fake_refresh_all)

    response = client.post("/mining/refresh", json={"refresh_all": True})
    assert response.status_code == 200
    body = response.json()
    assert len(body["refreshed"]) == 2
    assert {item["snapshot_type"] for item in body["refreshed"]} == {"customer_segmentation", "trend_analysis"}
