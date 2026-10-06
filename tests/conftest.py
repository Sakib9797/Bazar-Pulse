import os

import numpy as np
import pandas as pd
import pytest

from bazarpulse import catalog

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(scope="session")
def products():
    return catalog.load_products()


@pytest.fixture
def synthetic_prices(products):
    """Random-walk prices for 45 real catalog products over 500 days, skipping Fridays."""
    rng = np.random.default_rng(0)
    ids = sorted(products)[:45]
    dates = [d for d in pd.date_range("2024-01-01", periods=500, freq="D") if d.dayofweek != 4]
    rows = []
    for i, pid in enumerate(ids):
        level = 50 + 10 * i
        for d in dates:
            level *= np.exp(rng.normal(0, 0.01))
            rows.append({"date": d, "product_id": pid, "price_min": round(level * 0.95, 2),
                         "price_max": round(level * 1.05, 2)})
    df = pd.DataFrame(rows)
    df["price_mid"] = (df["price_min"] + df["price_max"]) / 2
    df["source_file"] = "synthetic"
    return df
