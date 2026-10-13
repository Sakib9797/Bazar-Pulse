import numpy as np
import pandas as pd

from bazarpulse import features, models
from bazarpulse.hijri import calendar_features


def test_features_use_only_the_past(synthetic_prices, products):
    """Changing prices after a cutoff must not change any feature of an earlier origin."""
    cutoff = pd.Timestamp("2024-12-01")
    a = features.training_rows(synthetic_prices, products)
    altered = synthetic_prices.copy()
    later = altered["date"] > cutoff
    altered.loc[later, ["price_min", "price_max", "price_mid"]] *= 3
    b = features.training_rows(altered, products)
    cols = ["date", "product_id", "h"] + [f for f in features.FEATURES if f not in features.CATEGORICAL]
    early_a = a[a["date"] <= cutoff].sort_values(["date", "product_id", "h"])[cols].reset_index(drop=True)
    early_b = b[b["date"] <= cutoff].sort_values(["date", "product_id", "h"])[cols].reset_index(drop=True)
    pd.testing.assert_frame_equal(early_a, early_b)


def test_targets_only_on_real_report_days(synthetic_prices, products):
    rows = features.training_rows(synthetic_prices, products)
    assert (rows["target_date"].dt.dayofweek != 4).all()          # no Fridays in the synthetic data
    assert set(rows["h"]) <= set(features.HORIZONS)


def test_forecast_rows_cover_every_horizon(synthetic_prices, products):
    rows = features.forecast_rows(synthetic_prices, products)
    assert sorted(rows["h"].unique()) == list(features.HORIZONS)
    assert rows["product_id"].nunique() == synthetic_prices["product_id"].nunique()


def test_ramadan_flag():
    cal = calendar_features(pd.Series(pd.to_datetime(["2026-03-01", "2026-06-01", "2026-05-20"])))
    assert cal["in_ramadan"].tolist() == [1, 0, 0]
    assert cal["days_to_eid_adha"].iloc[2] == 7                   # Eid al-Adha 2026-05-27
    assert cal["days_to_eid_adha"].iloc[1] == 90                  # next one is a year away: clipped


def test_pinball_and_ape():
    assert np.isclose(models.ape(np.log(1.1), 0.0), 0.1)
    # y inside the range at the median: only the median term is zero
    assert np.isclose(models.pinball(0.0, -0.1, 0.0, 0.1), 0.1 * 0.1 + 0.1 * 0.1)


def test_conformal_offsets_reach_target_coverage():
    rng = np.random.default_rng(3)
    n = 4000
    rows = pd.DataFrame({"h": np.repeat([7, 28], n // 2), "y": rng.normal(0, 0.05, n)})
    too_narrow = {0.1: np.full(n, -0.01), 0.9: np.full(n, 0.01)}
    off = models.conformal_offsets(too_narrow, rows)
    assert all(v > 0 for v in off.values())                       # range gets widened
    lo, hi = -0.01 - rows["h"].map(off), 0.01 + rows["h"].map(off)
    covered = ((rows["y"] >= lo) & (rows["y"] <= hi)).mean()
    assert abs(covered - models.COVERAGE) < 0.02


def test_climatology_falls_back_when_history_is_thin(synthetic_prices, products):
    rows = features.training_rows(synthetic_prices, products)
    cutoff = rows["target_date"].max()
    clim = models.climatology(rows.iloc[:50], rows.tail(20), cutoff)
    assert clim.notna().all().all()
    assert (clim["lo"] <= clim["mid"]).all() and (clim["mid"] <= clim["hi"]).all()


def test_backtest_never_trains_on_the_future(synthetic_prices, products, monkeypatch):
    rows = features.training_rows(synthetic_prices, products)
    seen = []
    real_fit = models.fit

    def spy(train, config, cutoff=None):
        seen.append((train["target_date"].max(), cutoff))
        return real_fit(train, {**config, "num_boost_round": 5}, cutoff)

    monkeypatch.setattr(models, "fit", spy)
    end = rows["date"].max()
    start = end - pd.Timedelta(days=55)
    res = models.backtest(rows, models.CANDIDATES[0], start, end, refit_every=28, log=lambda m: None)
    assert len(seen) == 2
    for max_target, cutoff in seen:
        assert max_target < cutoff
    s = models.summarize(res)
    assert s["rows"] == len(res) and s["products"] > 0
    assert 0 <= s["coverage_model"] <= 1 and "skill" in s
