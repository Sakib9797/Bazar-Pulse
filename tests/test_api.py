import importlib
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path / "forecasts").mkdir()
    (tmp_path / "clean").mkdir()
    latest = {"origin_date": "2026-10-04", "model_version": 3, "model": "lgbm_l1",
              "products": [{"product_id": "sugar", "name_en": "Sugar", "name_bn": "চিনি",
                            "category": "groceries", "unit": "kg", "last_price": 112.5,
                            "last_seen": "2026-10-04",
                            "forecast": [{"date": f"2026-10-{5 + i:02d}", "h": i + 1, "price": 113.0 + i,
                                          "change_pct": 0.4 * (i + 1)} for i in range(7)]}]}
    (tmp_path / "forecasts" / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    pd.DataFrame({"date": pd.to_datetime(["2026-10-03", "2026-10-04"]), "product_id": ["sugar"] * 2,
                  "price_min": [110.0, 110.0], "price_max": [115.0, 115.0], "price_mid": [112.5, 112.5]}
                 ).to_parquet(tmp_path / "clean" / "prices.parquet")
    monkeypatch.setenv("BAZARPULSE_DATA", str(tmp_path))
    import api.main
    return TestClient(importlib.reload(api.main).app)


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["model_version"] == 3


def test_forecast(client):
    body = client.get("/forecast/sugar").json()
    assert len(body["forecast"]) == 7 and body["name_bn"] == "চিনি"
    assert client.get("/forecast/unknown").status_code == 404


def test_history_uses_sql_over_parquet(client):
    body = client.get("/history/sugar?days=30").json()
    assert [p["date"] for p in body["prices"]] == ["2026-10-03", "2026-10-04"]
    assert client.get("/history/sugar'; DROP TABLE x;--").status_code == 404


def test_movers(client):
    body = client.get("/movers?limit=1").json()
    assert body["rises"][0]["product_id"] == "sugar"
