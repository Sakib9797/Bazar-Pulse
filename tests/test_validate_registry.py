import lightgbm as lgb
import numpy as np

from bazarpulse import registry, validate


def test_clean_data_passes(synthetic_prices, products):
    last = synthetic_prices["date"].max()
    hard, warn = validate.check_days(synthetic_prices, None, [last], products.keys())
    assert hard == [] and warn == []


def test_schema_rejects_bad_prices(synthetic_prices, products):
    bad = synthetic_prices.copy()
    bad.loc[0, "price_min"] = bad.loc[0, "price_max"] + 10          # min > max
    bad.loc[1, "price_mid"] = -5                                      # negative
    hard, _ = validate.check_days(bad, None, [], products.keys())
    assert hard and "schema" in hard[0]


def test_too_few_products_is_a_hard_failure(synthetic_prices, products):
    last = synthetic_prices["date"].max()
    thin = synthetic_prices[(synthetic_prices["date"] < last)
                            | synthetic_prices["product_id"].isin(sorted(products)[:10])]
    hard, _ = validate.check_days(thin, None, [last], products.keys())
    assert any("only 10 products" in h for h in hard)


def test_big_jump_is_a_warning(synthetic_prices, products):
    last = synthetic_prices["date"].max()
    jumped = synthetic_prices.copy()
    sel = (jumped["date"] == last) & (jumped["product_id"] == sorted(products)[0])
    jumped.loc[sel, ["price_min", "price_max", "price_mid"]] *= 2
    hard, warn = validate.check_days(jumped, None, [last], products.keys())
    assert not hard and warn and "moved" in warn[0]


def _tiny_model():
    x = np.random.default_rng(0).normal(size=(50, 2))
    b = lgb.train({"verbose": -1}, lgb.Dataset(x, label=x[:, 0]), num_boost_round=2)
    return {"boosters": {0.1: b, 0.5: b, 0.9: b}, "conformal": {7: 0.01, 28: 0.03}}


def test_register_and_rollback(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(registry, "REGISTRY", str(tmp_path / "registry.json"))
    cfg = {"name": "test"}
    v1 = registry.register(_tiny_model(), cfg, "2026-01-01", {"pinball_model": 2.0}, {"kind": "initial"})
    v2 = registry.register(_tiny_model(), cfg, "2026-01-08", {"pinball_model": 1.9}, {"kind": "weekly"})
    reg = registry.load()
    assert reg["champion"]["version"] == v2["version"] == 2
    assert reg["previous"]["version"] == v1["version"] == 1
    model, champ = registry.load_champion()
    assert champ["version"] == 2 and model["boosters"][0.5].num_trees() == 2
    assert model["conformal"] == {7: 0.01, 28: 0.03}

    back = registry.rollback("test")
    assert back["version"] == 1 and registry.load()["previous"] is None
    assert registry.load()["decisions"][-1]["kind"] == "rollback"
    assert registry.rollback("again") is None


def test_baseline_champion_has_no_model_file(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(registry, "REGISTRY", str(tmp_path / "registry.json"))
    entry = registry.register(None, {"name": "climatology"}, "2026-01-01", {"pinball_model": 2.0},
                              {"kind": "initial"})
    assert entry["file"] is None
    model, champ = registry.load_champion()
    assert model is None and champ["config"]["name"] == "climatology"


def test_monitor_psi_detects_shift():
    from bazarpulse.monitor import _psi
    rng = np.random.default_rng(1)
    ref = rng.normal(0, 0.02, 5000)
    assert _psi(ref, rng.normal(0, 0.02, 500)) < 0.1
    assert _psi(ref, rng.normal(0.05, 0.02, 500)) > 0.25
