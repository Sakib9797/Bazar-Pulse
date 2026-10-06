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
    assert set(rows["h"]) == set(features.HORIZONS)


def test_forecast_rows_cover_seven_days(synthetic_prices, products):
    rows = features.forecast_rows(synthetic_prices, products)
    assert sorted(rows["h"].unique()) == list(range(1, 8))
    assert rows["product_id"].nunique() == synthetic_prices["product_id"].nunique()


def test_ramadan_flag():
    cal = calendar_features(pd.Series(pd.to_datetime(["2026-03-01", "2026-06-01", "2026-05-20"])))
    assert cal["in_ramadan"].tolist() == [1, 0, 0]
    assert cal["days_to_eid_adha"].iloc[2] == 7                   # Eid al-Adha 2026-05-27
    assert cal["days_to_eid_adha"].iloc[1] == 90                  # next one is a year away: clipped


def test_ape():
    assert np.isclose(models.ape(np.log(1.1), 0.0), 0.1)
    assert models.ape(0.0, 0.0) == 0


def test_backtest_never_trains_on_the_future(synthetic_prices, products, monkeypatch):
    rows = features.training_rows(synthetic_prices, products)
    seen = []
    real_fit = models.fit

    def spy(train, config):
        seen.append(train["target_date"].max())
        return real_fit(train, {**config, "num_boost_round": 5})

    monkeypatch.setattr(models, "fit", spy)
    end = rows["date"].max()
    start = end - pd.Timedelta(days=55)
    preds = models.backtest(rows, models.CANDIDATES[0], start, end, refit_every=28, log=lambda m: None)
    blocks = [start, start + pd.Timedelta(days=28)]
    assert len(seen) == 2
    for max_target, block in zip(seen, blocks, strict=True):
        assert max_target < block
    s = models.summarize(preds)
    assert s["rows"] == len(preds) and s["products"] > 0
