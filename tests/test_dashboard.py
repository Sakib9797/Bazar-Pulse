from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "dashboard" / "streamlit_app.py")


@pytest.mark.parametrize("lang", ["English", "বাংলা"])
def test_dashboard_renders_without_errors(lang):
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["lang"] = lang
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 5
    assert len(at.metric) >= 8


def test_basket_totals_are_ordered():
    at = AppTest.from_file(APP, default_timeout=120).run()
    basket = {m.label: m.value for m in at.metric}
    taka = {
        k: float(v.replace("৳", "").replace(",", ""))
        for k, v in basket.items()
        if k in ("Cost today", "Likely cost", "Best case", "Worst case")
    }
    assert taka["Best case"] <= taka["Likely cost"] <= taka["Worst case"]
    assert taka["Best case"] <= taka["Cost today"] <= taka["Worst case"]
