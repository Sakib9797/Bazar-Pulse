"""Read TCB's paginated list of daily retail price files.

Columns are located by HEADER TEXT, never by position: the table carries both
English and Bengali copies of some columns, and the order is not guaranteed.
"""
import html as htmllib
import math
import re

from bazarpulse.textutil import clean

BASE_URL = "https://tcb.gov.bd/pages/daily-rmps"
PER_PAGE = 10
FILE_LINK = re.compile(r'href="([^"]+\.(?:xlsx|xls|pdf))"', re.I)
DATE_DMY = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{4})")


def page_url(n):
    return f"{BASE_URL}?page={n}"


def _cell_text(cell_html):
    return clean(htmllib.unescape(re.sub(r"<[^>]+>", " ", cell_html)))


def total_entries(page_html):
    m = re.search(r'pagination-counts">([^<]+)<', page_html)
    if not m:
        return None
    n = re.search(r"মোট\s*(\d+)", clean(m.group(1)))
    return int(n.group(1)) if n else None


def page_count(page_html):
    total = total_entries(page_html)
    return math.ceil(total / PER_PAGE) if total else 1


def parse_page(page_html):
    """Return [{title, listing_date, file_url}] for every row that links a file."""
    start, end = page_html.find("<table"), page_html.find("</table>")
    if start < 0 or end < 0:
        return []
    rows = re.findall(r"<tr.*?</tr>", page_html[start:end], re.S)
    if not rows:
        return []

    header = [_cell_text(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", rows[0], re.S)]
    col_title = next((i for i, h in enumerate(header) if h == "শিরোনাম"), None)
    col_date = next((i for i, h in enumerate(header) if h == "প্রকাশের তারিখ"), None)

    out = []
    for row in rows[1:]:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        links = [htmllib.unescape(u) for u in FILE_LINK.findall(row)]
        if not cells or not links:
            continue
        title = _cell_text(cells[col_title]) if col_title is not None and col_title < len(cells) else ""
        raw_date = _cell_text(cells[col_date]) if col_date is not None and col_date < len(cells) else ""
        m = DATE_DMY.search(raw_date)
        listing_date = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None
        for url in links:
            out.append({"title": title, "listing_date": listing_date, "file_url": url})
    return out
