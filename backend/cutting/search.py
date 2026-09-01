"""Free-text and shorthand search for the lay list (SRS 7.1.1).

The supervisor types one box. It may hold plain words — a model name, a lot
number, a shade — or shorthand tokens that mean a filter:

    ميتراج>1.2   عجز:نعم   مقاس:32   لون:أسود   خامة:MEGAN   حالة:مستنية-ترقيم

`parse_query` splits the two apart and turns the tokens into the very same
query parameters `LayFilter` already accepts, so there is one filtering
implementation and the shorthand is only a shorter way to type it.
"""
import re

# token name (Arabic, plus an English alias) -> the filter parameter it feeds.
# A pair means (min_param, max_param) for the comparison operators.
RANGE_TOKENS = {
    "ميتراج": ("real_metrage_min", "real_metrage_max"),
    "metrage": ("real_metrage_min", "real_metrage_max"),
    "متوقع": ("expected_metrage_min", "expected_metrage_max"),
    "انحراف": ("deviation_min", "deviation_max"),
    "deviation": ("deviation_min", "deviation_max"),
    "قطع": ("theoretical_pieces_min", "theoretical_pieces_max"),
    "pieces": ("theoretical_pieces_min", "theoretical_pieces_max"),
    "فعلي": ("actual_pieces_min", "actual_pieces_max"),
    "راق": ("total_plies_min", "total_plies_max"),
    "plies": ("total_plies_min", "total_plies_max"),
    "طول": ("lay_length_min", "lay_length_max"),
    "عرض": ("lay_width_min", "lay_width_max"),
    "أمتار": ("total_roll_length_min", "total_roll_length_max"),
    "امتار": ("total_roll_length_min", "total_roll_length_max"),
    "بواقي": ("total_remnant_min", "total_remnant_max"),
}

EQUALITY_TOKENS = {
    "مقاس": "size",
    "size": "size",
    "لون": "shade_note",
    "color": "shade_note",
    "خامة": "article",
    "article": "article",
    "لوط": "lot_no",
    "lot": "lot_no",
    "بنك": "bank_code",
    "bank": "bank_code",
    "موديل": "model_code",
    "model": "model_code",
    "قسم": "category",
    "فئة": "category",
    "كود": "code",
}

BOOLEAN_TOKENS = {
    "عجز": "has_shortage",
    "shortage": "has_shortage",
    "فرق": "has_length_mismatch",
    "وصل": "has_splice",
    "مرحلة": "is_backfill",
    "مرحّلة": "is_backfill",
    "backfill": "is_backfill",
    "صورة": "has_sheet_image",
    "سريع": "quick_entry",
}

# حالة:مستنية-ترقيم and friends. The dash form is what a user can type without
# a space breaking the token.
STATUS_VALUES = {
    "مفتوحة": "open",
    "مقفولة": "closed",
    "مترقمة": "counted",
    "مترقّمة": "counted",
    "معتمدة": "approved",
    "open": "open",
    "closed": "closed",
    "counted": "counted",
    "approved": "approved",
}
AWAITING_COUNT = {"مستنية-ترقيم", "مستنية ترقيم", "awaiting-count"}

TRUE_WORDS = {"نعم", "أيوه", "ايوه", "yes", "true", "1"}
FALSE_WORDS = {"لا", "لأ", "no", "false", "0"}

# name>value / name>=value / name:value — the value runs to the next space.
_TOKEN = re.compile(
    r"(?P<name>[^\s:<>=]+)\s*(?P<op>>=|<=|>|<|:|=)\s*(?P<value>[^\s]+)"
)

# Arabic-Indic digits, so a phone keyboard set to Arabic still filters.
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _boolean(value: str):
    low = value.strip().lower()
    if low in TRUE_WORDS:
        return "true"
    if low in FALSE_WORDS:
        return "false"
    return None


def parse_query(text: str):
    """Return (free_text, params).

    `params` is a plain dict of the same query parameters LayFilter takes, so
    the caller feeds it straight to the filterset. Anything unrecognised is
    left in `free_text` rather than silently dropped — a token that turns out
    to be a lot number should still find the lay.
    """
    text = (text or "").translate(_DIGITS).strip()
    if not text:
        return "", {}

    params = {}
    consumed = []

    for match in _TOKEN.finditer(text):
        name = match.group("name").strip()
        op = match.group("op")
        value = match.group("value").strip()
        if not value:
            continue

        handled = False

        if name in RANGE_TOKENS:
            low, high = RANGE_TOKENS[name]
            if op in (">", ">="):
                params[low] = value
                handled = True
            elif op in ("<", "<="):
                params[high] = value
                handled = True
            elif op in (":", "="):
                # an exact number is a range of one
                params[low] = value
                params[high] = value
                handled = True

        elif name in BOOLEAN_TOKENS and op in (":", "="):
            flag = _boolean(value)
            if flag is not None:
                params[BOOLEAN_TOKENS[name]] = flag
                handled = True

        elif name in EQUALITY_TOKENS and op in (":", "="):
            params[EQUALITY_TOKENS[name]] = value
            handled = True

        elif name in ("حالة", "status") and op in (":", "="):
            key = value.replace("_", "-")
            if key in AWAITING_COUNT:
                params["awaiting_count"] = "true"
                handled = True
            elif key in STATUS_VALUES:
                params["status"] = STATUS_VALUES[key]
                handled = True

        if handled:
            consumed.append(match.span())

    # Whatever the tokens did not claim stays as free text.
    free = text
    for start, end in reversed(consumed):
        free = free[:start] + " " + free[end:]
    return " ".join(free.split()), params


def describe(params: dict) -> list:
    """Human labels for the parsed filters, for the chips above the list."""
    labels = {
        "real_metrage_min": "الميتراج الحقيقي ≥",
        "real_metrage_max": "الميتراج الحقيقي ≤",
        "expected_metrage_min": "الميتراج المتوقع ≥",
        "expected_metrage_max": "الميتراج المتوقع ≤",
        "deviation_min": "الانحراف ≥",
        "deviation_max": "الانحراف ≤",
        "theoretical_pieces_min": "القطع النظرية ≥",
        "theoretical_pieces_max": "القطع النظرية ≤",
        "actual_pieces_min": "القطع الفعلية ≥",
        "actual_pieces_max": "القطع الفعلية ≤",
        "total_plies_min": "إجمالي الراق ≥",
        "total_plies_max": "إجمالي الراق ≤",
        "lay_length_min": "طول الفرشة ≥",
        "lay_length_max": "طول الفرشة ≤",
        "lay_width_min": "عرض الفرشة ≥",
        "lay_width_max": "عرض الفرشة ≤",
        "total_roll_length_min": "إجمالي الأمتار ≥",
        "total_roll_length_max": "إجمالي الأمتار ≤",
        "total_remnant_min": "إجمالي البواقي ≥",
        "total_remnant_max": "إجمالي البواقي ≤",
        "size": "مقاس",
        "shade_note": "لون",
        "article": "خامة",
        "lot_no": "لوط",
        "bank_code": "بنك",
        "model_code": "موديل",
        "category": "القسم",
        "code": "كود القصة",
        "has_shortage": "فيها عجز",
        "has_length_mismatch": "فيها فرق أطوال",
        "has_splice": "فيها وصل",
        "is_backfill": "مرحّلة",
        "has_sheet_image": "فيها صورة",
        "quick_entry": "إدخال سريع",
        "awaiting_count": "مستنية ترقيم",
        "status": "الحالة",
    }
    out = []
    for key, value in params.items():
        label = labels.get(key, key)
        if value in ("true", "false"):
            out.append({"key": key, "label": label, "value": "نعم" if value == "true" else "لا"})
        else:
            out.append({"key": key, "label": label, "value": value})
    return out
