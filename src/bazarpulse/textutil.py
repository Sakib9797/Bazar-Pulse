import re
import unicodedata

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


def ascii_digits(s):
    return nfc(s).translate(BN_DIGITS)


def clean(s):
    """NFC, ASCII digits, single spaces. Bengali text that looks identical can differ in
    composition (য় as one code point or two), so every comparison goes through here."""
    return re.sub(r"\s+", " ", ascii_digits(str(s))).strip()
