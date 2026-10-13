"""Turn one TCB daily price workbook into rows.

Layout facts the parser relies on (checked on files from 2021 and 2026):
  * The header row holds "পণ্যের নাম" and "অদ্যকার মূল্য"; the row below it holds the
    date of each price block. Columns are found by HEADER TEXT, never by position.
  * Each price block is two columns: সর্বনিম্ন (min) then সর্ব্বোচ্চ (max).
  * The header REPEATS mid-sheet (a page-two header). It is skipped, not treated as the
    end of the table. In some files its dates differ from the first header's; the first
    header is authoritative and the mismatch is reported as a warning.
  * Section rows ("ভোজ্য তেল", "মসলাঃ") carry a name but no prices.
  * A price of 0 means "not in the market" and becomes missing, never zero.
  * Below the main table sits a second table of price changes with its own header and
    numbers; parsing stops before it.
"""
import datetime as dt
import re

from openpyxl import load_workbook

from bazarpulse.textutil import clean

BLOCKS = {                       # block name -> header text that identifies it
    "today": "অদ্যকার",
    "week": "সপ্তাহ পূর্বের",
    "month": "মাস পূর্বের",
    "year": "বছর পূর্বের",
}
END_MARKERS = ("তারকা চিহ্নিত", "যে সকল বাজার", "যে সকল পণ্যের", "মন্তব্য")
NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
DATE_DMY = re.compile(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})")


class ParseError(Exception):
    pass


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = clean(v).replace(",", "")
    return float(s) if NUMBER.match(s) else None


def _price(v):
    n = _num(v)
    return n if n is not None and n > 0 else None


def _date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    m = DATE_DMY.search(clean(v or ""))
    if m:
        try:
            return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _text(v):
    return clean(v) if v is not None else ""


def _is_header(cells):
    joined = " ".join(cells)
    return "পণ্যের নাম" in joined and BLOCKS["today"] in joined


def _header_columns(cells):
    cols = {}
    for name, needle in BLOCKS.items():
        for i, c in enumerate(cells):
            if needle in c and name not in cols:
                cols[name] = i
    return cols


def _find_table(ws_rows):
    for i, row in enumerate(ws_rows):
        cells = [_text(v) for v in row]
        if _is_header(cells):
            return i, _header_columns(cells)
    return None, None


def parse_workbook(path):
    """Return {report_date, block_dates, rows, warnings} or raise ParseError.

    Every sheet is tried in order and the first one that parses completely wins: some
    2025 workbooks put an unrelated TCB sales table in 'Sheet1' and the price sheet third.
    """
    with open(path, "rb") as f:
        head = f.read(4096)
    if head and not head.strip(b"\0"):
        raise ParseError("file contains only zero bytes (corrupt on TCB's server)")
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception as e:
        raise ParseError(f"cannot open workbook: {type(e).__name__}: {e}") from e
    sheets = [(ws.title, [tuple(r) for r in ws.iter_rows(values_only=True)]) for ws in wb.worksheets]
    wb.close()

    errors = []
    for title, ws_rows in sheets:
        try:
            return _parse_sheet(ws_rows)
        except ParseError as e:
            errors.append(f"{title}: {e}")
    raise ParseError("; ".join(errors) or "workbook has no sheets")


def _parse_sheet(ws_rows):
    start, cols = _find_table(ws_rows)
    if start is None:
        raise ParseError("no 'পণ্যের নাম' / 'অদ্যকার মূল্য' header")
    if "today" not in cols:
        raise ParseError("header has no today's-price column")
    warnings = []
    missing = [b for b in BLOCKS if b not in cols]
    if missing:
        warnings.append(f"header lacks block(s): {missing}")

    def block_dates(row):
        return {b: _date(row[c]) if c < len(row) else None for b, c in cols.items()}

    first_dates = block_dates(ws_rows[start + 1]) if start + 1 < len(ws_rows) else {}
    report_date = first_dates.get("today")
    if report_date is None:
        raise ParseError("no date under the today's-price header")

    price_cols = [c + k for c in cols.values() for k in (0, 1)]
    rows, section = [], ""
    i = start + 2
    while i < len(ws_rows):
        row = ws_rows[i]
        cells = [_text(v) for v in row]
        name = cells[0] if cells else ""
        if any(m in c for c in cells for m in END_MARKERS):
            break
        if _is_header(cells):                              # repeated page header
            again = block_dates(ws_rows[i + 1]) if i + 1 < len(ws_rows) else {}
            if again.get("today") and again["today"] != report_date:
                warnings.append(f"repeated header dated {again['today']} != {report_date}")
            i += 2
            continue
        unit = cells[1] if len(cells) > 1 else ""
        has_numbers = any(_num(row[c]) is not None for c in price_cols if c < len(row))
        if name and not unit and not has_numbers:
            section = name.rstrip(":ঃ ").strip()
        elif name and unit:
            rec = {"report_date": report_date, "section": section,
                   "product_raw": name, "unit_raw": unit}
            for b in BLOCKS:
                c = cols.get(b)
                rec[f"{b}_min"] = _price(row[c]) if c is not None and c < len(row) else None
                rec[f"{b}_max"] = _price(row[c + 1]) if c is not None and c + 1 < len(row) else None
            rows.append(rec)
        i += 1

    if not rows:
        raise ParseError("header found but no product rows under it")
    return {"report_date": report_date, "block_dates": first_dates, "rows": rows, "warnings": warnings}
