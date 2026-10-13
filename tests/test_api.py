import importlib
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path / "forecasts").mkdir()
    (tmp_path / "clean").mkdir()

    def product(pid, name, last, step):
        return {"product_id": pid, "name_en": name, "name_bn": name, "category": "groceries", "unit": "kg",
                "last_price": last, "last_seen": "2026-10-04",
                "forecast": [{"date": f"2026-10-{4 + 7 * w:02d}" if w < 4 else "2026-11-01", "weeks": w,
                              "low": last * 0.95, "mid": last * (1 + step * w),
                              "high": last * (1.05 + step * w),
                              "change_pct": step * w * 100, "upside_pct": (0.05 + step * w) * 100}
                             for w in (1, 2, 3, 4)]}

    latest = {"origin_date": "2026-10-04", "model_version": 3, "model": "qlgbm", "coverage_target": 0.8,
              "products": [product("sugar", "চিনি", 112.5, 0.01), product("salt", "লবণ", 41.0, 0.0)]}
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


def test_forecast_has_ranges(client):
    body = client.get("/forecast/sugar").json()
    assert [f["weeks"] for f in body["forecast"]] == [1, 2, 3, 4]
    assert all(f["low"] <= f["mid"] <= f["high"] for f in body["forecast"])
    assert client.get("/forecast/unknown").status_code == 404


def test_history_uses_sql_over_parquet(client):
    body = client.get("/history/sugar?days=30").json()
    assert [p["date"] for p in body["prices"]] == ["2026-10-03", "2026-10-04"]
    assert client.get("/history/sugar'; DROP TABLE x;--").status_code == 404


def test_movers(client):
    body = client.get("/movers?limit=1").json()
    assert body["rises"][0]["product_id"] == "sugar"
    assert body["falls"][0]["product_id"] == "salt"
    assert body["upside_risk"][0]["weeks"] == 4
