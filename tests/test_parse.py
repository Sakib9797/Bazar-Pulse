import datetime as dt
import os

import pytest

from bazarpulse.parse import ParseError, parse_workbook
from conftest import FIXTURES

FILES = {
    "2021": ("2021-05-22.xlsx", dt.date(2021, 5, 22)),
    "2026": ("2026-10-04.xlsx", dt.date(2026, 10, 4)),
}


@pytest.mark.parametrize("year", FILES)
def test_report_date_and_rows(year):
    name, date = FILES[year]
    out = parse_workbook(os.path.join(FIXTURES, name))
    assert out["report_date"] == date
    assert len(out["rows"]) >= 50
    for r in out["rows"]:
        assert r["today_min"] is None or r["today_max"] is None or r["today_min"] <= r["today_max"]


@pytest.mark.parametrize("year", FILES)
def test_second_table_is_not_read(year):
    """The 'price changes' table under the main one repeats products; they must not be duplicated."""
    rows = parse_workbook(os.path.join(FIXTURES, FILES[year][0]))["rows"]
    keys = [(r["product_raw"], r["unit_raw"]) for r in rows]
    assert len(keys) == len(set(keys))


def test_repeated_header_with_other_date_is_reported_not_trusted():
    out = parse_workbook(os.path.join(FIXTURES, "2021-05-22.xlsx"))
    assert out["report_date"] == dt.date(2021, 5, 22)
    assert any("repeated header dated 2021-05-23" in w for w in out["warnings"])


def test_rows_after_repeated_header_are_kept():
    rows = parse_workbook(os.path.join(FIXTURES, "2026-10-04.xlsx"))["rows"]
    names = {r["product_raw"] for r in rows}
    assert "চিনি" in names and "ডিম (ফার্ম)" in names      # both sit below the mid-sheet header


def test_zero_price_means_missing():
    rows = parse_workbook(os.path.join(FIXTURES, "2026-10-04.xlsx"))["rows"]
    onion = next(r for r in rows if r["product_raw"] == "পিঁয়াজ (আমদানি)")
    assert onion["today_min"] is None and onion["today_max"] is None


def test_bengali_digits_in_units_are_normalised():
    rows = parse_workbook(os.path.join(FIXTURES, "2026-10-04.xlsx"))["rows"]
    units = {r["unit_raw"] for r in rows if r["product_raw"].startswith("সয়াবিন তেল (বোতল)")}
    assert units == {"5 লিটার", "2 লিটার", "1 লিটার"}


def test_not_a_workbook(tmp_path):
    bad = tmp_path / "x.xlsx"
    bad.write_text("<html>error</html>")
    with pytest.raises(ParseError):
        parse_workbook(str(bad))
