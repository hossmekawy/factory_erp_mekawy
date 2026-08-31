"""Size-set text parsing and the actual-pieces distribution (SRS 4.5, 4.9).

Two jobs, both pure functions with no model imports:

1. Turn the supervisor's free text (`"30 32 32 34 34 36"`, or `"(32)(34)"` as
   the notebook writes it) into ordered (size, count) pairs plus a total.
2. Split a counted total across those sizes by largest remainder (Hamilton),
   so the parts always add back to the total exactly.
"""
import re
from fractions import Fraction

# Arabic-Indic and Eastern Arabic-Indic digits → ASCII. The notebook and the
# phone keyboard both produce these.
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# Anything that is not a digit or a letter separates one size from the next:
# spaces, slashes, dashes, parentheses, and both commas — the Arabic comma
# (U+060C) sits inside the Arabic block, so the block cannot be kept whole.
_SEPARATORS = re.compile(r"[^0-9A-Za-z\u0621-\u064A]+")


class SizeParseError(ValueError):
    """Raised when the size text cannot be read as a list of sizes."""


def normalize_digits(text: str) -> str:
    return (text or "").translate(_DIGITS)


def size_sort_key(size: str):
    """Order sizes numerically when they are numbers, alphabetically otherwise.

    Used only to break ties in the distribution, where the rule is
    "smallest size first" (SRS 4.9).
    """
    s = normalize_digits(str(size)).strip()
    try:
        return (0, float(s), "")
    except ValueError:
        return (1, 0.0, s.upper())


def parse_sizes(raw: str):
    """`"30 32 32 34 34 36"` -> `[("30", 1), ("32", 2), ("34", 2), ("36", 1)]`.

    Repetition is meaningful: a size may appear more than once in one ply.
    Order follows first appearance in the text, which is the notebook's order.
    """
    tokens = [t for t in _SEPARATORS.split(normalize_digits(raw or "").strip()) if t]
    if not tokens:
        raise SizeParseError("مفيش مقاسات مكتوبة")

    counts = {}
    order = []
    for token in tokens:
        size = token.upper() if token.isalpha() else token
        if size not in counts:
            counts[size] = 0
            order.append(size)
        counts[size] += 1
    return [(size, counts[size]) for size in order]


def total_pieces(raw: str) -> int:
    """Pieces per ply implied by the size text — the count of tokens, not of
    distinct sizes."""
    return sum(count for _size, count in parse_sizes(raw))


def format_sizes(pairs) -> str:
    """Inverse of `parse_sizes`, for round-tripping a stored breakdown."""
    return " ".join(size for size, count in pairs for _ in range(count))


def distribute(total: int, breakdown) -> dict:
    """Split `total` across sizes in proportion to their share of one ply.

    `breakdown` is an iterable of (size, pieces_in_ply). Returns
    {size: pieces}, and **the values always sum to exactly `total`** — the SRS
    calls any other outcome a bug (4.9).

    Largest remainder (Hamilton): take each size's whole part, then hand the
    leftover units out one each to the largest fractional remainders. Ties go
    to the smaller size first. Fractions, not floats, so a tie is a real tie
    and not a rounding accident.
    """
    pairs = [(str(size), int(pieces)) for size, pieces in breakdown]
    if any(pieces < 0 for _size, pieces in pairs):
        raise ValueError("عدد القطع في الراق ماينفعش يكون بالسالب")

    denominator = sum(pieces for _size, pieces in pairs)
    if not pairs or denominator <= 0:
        raise ValueError("مجموع المقاسات لازم يكون أكبر من صفر")
    if total < 0:
        raise ValueError("إجمالي القطع ماينفعش يكون بالسالب")

    quotas = {size: Fraction(total * pieces, denominator) for size, pieces in pairs}
    result = {size: int(q) for size, q in quotas.items()}  # Fraction -> floor for q >= 0

    leftover = total - sum(result.values())
    if leftover:
        ranked = sorted(
            quotas,
            key=lambda size: (-(quotas[size] - result[size]), size_sort_key(size)),
        )
        for size in ranked[:leftover]:
            result[size] += 1

    assert sum(result.values()) == total, "التوزيع مش مطابق للإجمالي"
    return result
