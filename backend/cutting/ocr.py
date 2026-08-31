"""OCR for fabric roll labels (ليبل التوب).

Reads a photographed printed label and extracts the roll fields. Designed to
be error-tolerant, never authoritative: the result only pre-fills a form the
user reviews before saving. Unknown/implausible values are dropped with an
Arabic warning instead of being guessed.
"""
import difflib
import re

import pytesseract
from PIL import Image, ImageOps

KEY_ALIASES = {
    "article_name": ["article name", "article"],
    "lot_number": ["lot no", "lot"],
    "roll_number": ["roll no", "roll"],
    "width": ["width"],
    "length": ["length"],
    "weight": ["weight", "net weight", "gross weight"],
    "color": ["color", "colour"],
    "grade": ["grade"],
}
# NOTE: deliberately no aliases for "patch no", "order no", "pieces",
# "shrinkage", "type", "comp" — those exist on real labels and must NOT
# fuzzy-match into our fields (cutoff 0.72 keeps "order no" away from
# "roll no" and "lot no").
ALIAS_TO_FIELD = {alias: field for field, aliases in KEY_ALIASES.items() for alias in aliases}
ALL_ALIASES = list(ALIAS_TO_FIELD)

NUMERIC_FIELDS = {"width", "length", "weight"}
PLAUSIBLE = {
    "width": (50, 400),    # cm
    "length": (1, 2000),   # m
    "weight": (1, 500),    # kg
}
AR_LABEL = {"width": "العرض", "length": "الطول", "weight": "الوزن"}

# OCR letter→digit confusions, applied only inside numeric values
_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "B": "8"})
_UNIT_RE = re.compile(r"\s*(cm|mm|m|kg|kgs|yd|yds)\b\.?", re.IGNORECASE)


def _preprocess(django_file) -> Image.Image:
    img = Image.open(django_file)
    img = ImageOps.exif_transpose(img)
    img = img.convert("L")
    img = ImageOps.autocontrast(img)
    if max(img.size) < 1600:
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    return img


def _match_field(raw_key: str):
    key = re.sub(r"[^a-z ]", "", raw_key.lower())
    key = re.sub(r"\s+", " ", key).strip()
    if not key:
        return None
    hits = difflib.get_close_matches(key, ALL_ALIASES, n=1, cutoff=0.72)
    return ALIAS_TO_FIELD[hits[0]] if hits else None


def _clean_number(raw: str):
    v = _UNIT_RE.sub("", raw.strip())
    v = v.translate(_DIGIT_FIX)
    v = v.replace(",", ".")
    m = re.search(r"\d+(?:\.\d+)?", v)
    return float(m.group()) if m else None


# "KEY : VALUE" — the separator is often OCR-mangled into | ( { = on noisy
# photos, so accept those too; a second pair may follow on the same line.
_INLINE_PAIR = re.compile(r"([A-Za-z_][A-Za-z ]{1,20})[.\s]*[:;|({=]+\s*(.+)$")

_VALUE_JUNK = " .:;|(){}[]—=–\\-_!~'\""


def _split_pairs(line: str):
    """Yield (key, value) pairs from one OCR line, handling labels that print
    two fields side by side (e.g. "LENGTH: 100.06   WEIGHT: 64.28")."""
    m = _INLINE_PAIR.search(line)
    if not m:
        return
    key, rest = m.group(1), m.group(2)
    # does the remainder contain another pair?
    m2 = _INLINE_PAIR.search(rest)
    if m2:
        value = rest[: m2.start()].strip()
        yield key, value
        yield from _split_pairs(rest)
    else:
        yield key, rest.strip()


def _parse_text(text: str):
    fields, warnings = {}, []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for raw_key, raw_value in _split_pairs(line) or []:
            field = _match_field(raw_key)
            if field is None or field in fields or not raw_value:
                continue
            if field in NUMERIC_FIELDS:
                num = _clean_number(raw_value)
                if num is None:
                    continue
                lo, hi = PLAUSIBLE[field]
                if not (lo <= num <= hi):
                    warnings.append(
                        f"{AR_LABEL[field]} المقروء غير منطقي ({num:g}) — راجِع الصورة"
                    )
                    continue
                fields[field] = num
            else:
                value = re.sub(r"\s+", " ", raw_value).strip(_VALUE_JUNK)
                if not value:
                    continue
                value = value.upper()
                # grade "A1" is routinely misread as "AL"/"AI"
                if field == "grade" and re.fullmatch(r"[A-Z][LI]", value):
                    value = value[0] + "1"
                fields[field] = value
    return fields, warnings


def ocr_label_image(django_file) -> dict:
    img = _preprocess(django_file)
    # Two segmentation modes see noisy labels differently; run both and merge,
    # psm 6 (uniform block) winning any conflicts.
    text = pytesseract.image_to_string(img, lang="eng", config="--psm 6")
    fields, warnings = _parse_text(text)
    alt_text = pytesseract.image_to_string(img, lang="eng", config="--psm 4")
    alt_fields, _ = _parse_text(alt_text)
    for key, value in alt_fields.items():
        fields.setdefault(key, value)
    return {
        "fields": fields,
        "found": sorted(fields),
        "warnings": warnings,
        "raw_text": text.strip(),
    }
