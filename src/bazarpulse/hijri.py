"""Islamic calendar events that move Bangladeshi food prices.

Dates come from the Umm al-Qura calendar; Bangladesh often observes them a day later,
which is close enough for a model feature.
"""
from functools import lru_cache

import numpy as np
import pandas as pd
from hijridate import Hijri

HIJRI_YEARS = range(1440, 1455)          # 2018 - 2033
CLIP_DAYS = 90


@lru_cache(maxsize=1)
def events():
    def g(y, m, d):
        return pd.Timestamp(Hijri(y, m, d).to_gregorian())
    return {
        "ramadan_start": [g(y, 9, 1) for y in HIJRI_YEARS],
        "eid_fitr": [g(y, 10, 1) for y in HIJRI_YEARS],
        "eid_adha": [g(y, 12, 10) for y in HIJRI_YEARS],
    }


def _days_to_next(dates, event_dates):
    ev = np.array(sorted(event_dates), dtype="datetime64[D]")
    d = dates.values.astype("datetime64[D]")
    idx = np.searchsorted(ev, d, side="left")
    nxt = ev[np.minimum(idx, len(ev) - 1)]
    days = (nxt - d).astype(int)
    return np.clip(days, 0, CLIP_DAYS)


def calendar_features(dates):
    """dates: Series of Timestamps -> DataFrame of calendar features aligned to it."""
    dates = pd.to_datetime(pd.Series(dates).reset_index(drop=True))
    ev = events()
    to_ramadan = _days_to_next(dates, ev["ramadan_start"])
    to_fitr = _days_to_next(dates, ev["eid_fitr"])
    # Inside Ramadan the next Eid al-Fitr is under 30 days away and comes before the next Ramadan.
    in_ramadan = (to_fitr < 30) & (to_fitr < to_ramadan)
    return pd.DataFrame({
        "dow": dates.dt.dayofweek.values,
        "month": dates.dt.month.values,
        "in_ramadan": in_ramadan.astype(int),
        "days_to_ramadan": to_ramadan,
        "days_to_eid_fitr": to_fitr,
        "days_to_eid_adha": _days_to_next(dates, ev["eid_adha"]),
    })
