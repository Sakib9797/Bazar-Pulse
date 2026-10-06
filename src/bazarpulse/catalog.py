"""Map TCB's raw product names to stable product ids.

TCB renames products over the years ("চাল (মাঝারী)পাইজাম/লতা" became "পাইজাম/আটাশ",
"মশুর" is sometimes spelled "মশূর"). catalog/aliases.csv lists every raw spelling seen
and the product it belongs to; catalog/products.csv describes each product once.
A spelling that is not in aliases.csv is reported as unmapped, never guessed.
"""
import csv
import os
import re

from bazarpulse.textutil import clean

CATALOG_DIR = "catalog"
PRODUCTS = os.path.join(CATALOG_DIR, "products.csv")
ALIASES = os.path.join(CATALOG_DIR, "aliases.csv")


def key(text):
    """Normalise a raw name or unit for matching: NFC, ASCII digits, tidy spaces and stars."""
    s = clean(text).replace("*", "")
    s = re.sub(r"\s*\(\s*", " (", s)
    s = re.sub(r"\s*\)\s*", ") ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_products(path=PRODUCTS):
    with open(path, encoding="utf-8", newline="") as f:
        return {r["product_id"]: r for r in csv.DictReader(f)}


def load_aliases(path=ALIASES):
    with open(path, encoding="utf-8", newline="") as f:
        return {(r["name_key"], r["unit_key"]): r["product_id"] for r in csv.DictReader(f)}


def lookup(aliases, product_raw, unit_raw):
    return aliases.get((key(product_raw), key(unit_raw)))
