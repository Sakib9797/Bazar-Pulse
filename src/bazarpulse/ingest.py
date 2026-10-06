"""Download TCB's daily price files into data/raw/ and record them in a manifest.

    python -m bazarpulse.ingest            # daily: stop at the first page with nothing new
    python -m bazarpulse.ingest --all      # backfill: walk every page (resumable)

Raw files are immutable: a file already in the manifest is never fetched again.
"""
import argparse
import csv
import hashlib
import os
import urllib.parse
from datetime import UTC, datetime

from bazarpulse import fetch, listing

RAW_DIR = os.path.join("data", "raw")
MANIFEST = os.path.join(RAW_DIR, "manifest.csv")
FIELDS = ["file_url", "title", "listing_date", "path", "bytes", "sha256", "downloaded_at"]


def load_manifest(path=MANIFEST):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        return {r["file_url"]: r for r in csv.DictReader(f)}


def _append(row, path=MANIFEST):
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def _local_path(entry):
    url_path = urllib.parse.urlsplit(entry["file_url"]).path
    ext = os.path.splitext(url_path)[1].lower() or ".bin"
    key = hashlib.sha1(entry["file_url"].encode()).hexdigest()[:8]
    if entry["listing_date"]:
        return os.path.join(RAW_DIR, entry["listing_date"][:4], f"{entry['listing_date']}_{key}{ext}")
    return os.path.join(RAW_DIR, "undated", f"{key}{ext}")


def download(entry):
    body = fetch.get(entry["file_url"])
    path = _local_path(entry)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(body)
    os.replace(tmp, path)
    row = {**entry, "path": path.replace(os.sep, "/"), "bytes": len(body),
           "sha256": hashlib.sha256(body).hexdigest(),
           "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds")}
    _append(row)
    return row


def sync(walk_all=False, max_pages=None, log=print):
    """Fetch list pages from newest to oldest and download every file not yet in the manifest."""
    known = load_manifest()
    first = fetch.get(listing.page_url(1)).decode("utf-8", errors="replace")
    pages = listing.page_count(first)
    if max_pages:
        pages = min(pages, max_pages)
    log(f"listing reports {listing.total_entries(first)} entries over {pages} page(s)")

    new_rows, failures = [], []
    for n in range(1, pages + 1):
        page_html = first if n == 1 else fetch.get(listing.page_url(n)).decode("utf-8", errors="replace")
        entries = listing.parse_page(page_html)
        fresh = [e for e in entries if e["file_url"] not in known]
        for e in fresh:
            try:
                row = download(e)
            except Exception as ex:
                failures.append((e["file_url"], f"{type(ex).__name__}: {ex}"))
                log(f"  FAILED {e['listing_date']} {type(ex).__name__}: {ex}")
                continue
            known[row["file_url"]] = row
            new_rows.append(row)
            log(f"  page {n:>3}/{pages}  {row['listing_date'] or 'undated'}  {row['bytes']:>7} B")
        if not walk_all and entries and not fresh:
            break
    log(f"done: {len(new_rows)} new file(s), {len(failures)} failure(s), {len(known)} in manifest")
    return new_rows, failures


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true", help="walk every page (backfill)")
    ap.add_argument("--max-pages", type=int, default=None)
    args = ap.parse_args()
    _, failures = sync(walk_all=args.all, max_pages=args.max_pages,
                       log=lambda m: print(m, flush=True))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
