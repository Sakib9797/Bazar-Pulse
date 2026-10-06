import os

from bazarpulse import catalog, listing
from bazarpulse.parse import parse_workbook
from conftest import FIXTURES


def test_listing_page():
    html = open(os.path.join(FIXTURES, "listing_last_page.html"), encoding="utf-8").read()
    rows = listing.parse_page(html)
    assert len(rows) == 6
    assert rows[0]["listing_date"] == "2021-05-22"
    assert rows[0]["file_url"].endswith(".xlsx")
    assert any(r["listing_date"] is None for r in rows)      # one entry has no date
    assert listing.total_entries(html) == 1406
    assert listing.page_count(html) == 141


def test_key_normalisation():
    assert catalog.key("চাল (মাঝারী)পাইজাম/আটাশ") == "চাল (মাঝারী) পাইজাম/আটাশ"
    assert catalog.key("  ৫ লিটার ") == "5 লিটার"
    assert catalog.key("চিনি                  ") == "চিনি"
    assert catalog.key("ডানো*") == "ডানো"


def test_every_fixture_row_maps_to_a_product(products):
    aliases = catalog.load_aliases()
    assert set(aliases.values()) <= set(products)
    for name in ("2021-05-22.xlsx", "2026-10-04.xlsx"):
        rows = parse_workbook(os.path.join(FIXTURES, name))["rows"]
        unmapped = [(r["product_raw"], r["unit_raw"]) for r in rows
                    if catalog.lookup(aliases, r["product_raw"], r["unit_raw"]) is None]
        assert not unmapped, f"{name}: {unmapped}"
