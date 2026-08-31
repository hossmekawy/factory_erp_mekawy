"""V1 → V9 from SRS 5.5, checked on the backend and never only in the UI.

Two tiers:

* `LayLine.clean()` / `Lay.clean()` in models.py hold the row-local rules
  (V2, V3) so no write path can dodge them.
* Everything here is whole-lay: it needs the lines, the breakdown, or the
  attendance history, so it runs at closing (`validate_for_close`) and at
  counting (`validate_output`).

Each check returns `Issue`s rather than raising, so a caller can show all the
problems at once. `ERROR` blocks the transition; `WARNING` is overridable with
a reason; `INFO` is just told to the user.
"""
from dataclasses import dataclass
from decimal import Decimal

from hr.attendance import attendance_data_start, present_codes

ERROR = "error"
WARNING = "warning"
INFO = "info"


@dataclass(frozen=True)
class Issue:
    code: str  # "V4"
    level: str  # ERROR | WARNING | INFO
    message: str
    field: str = ""
    line_no: int = None

    def __str__(self):
        where = f" (سطر {self.line_no})" if self.line_no else ""
        return f"[{self.code}] {self.message}{where}"


def errors_in(issues):
    return [i for i in issues if i.level == ERROR]


def has_errors(issues) -> bool:
    return any(i.level == ERROR for i in issues)


# --- individual rules ----------------------------------------------------

def check_v1_lay_width(lay, lines) -> list:
    """Lay width cannot exceed the narrowest roll on the table."""
    widths = [ln.width_cm for ln in lines if ln.width_cm is not None]
    if not widths:
        return []
    narrowest = min(widths)
    if lay.lay_width_cm > narrowest:
        return [
            Issue(
                "V1",
                WARNING,
                f"عرض الفرشة ({lay.lay_width_cm}) أكبر من أضيق توب ({narrowest})",
                field="lay_width_cm",
            )
        ]
    return []


def check_v2_line_positives(lines) -> list:
    """Plies and roll length must be positive. Also enforced by CheckConstraint."""
    issues = []
    for ln in lines:
        if ln.plies is None or ln.plies <= 0:
            issues.append(Issue("V2", ERROR, "الراق لازم يكون أكبر من صفر", "plies", ln.line_no))
        if ln.roll_length_m is None or ln.roll_length_m <= 0:
            issues.append(
                Issue("V2", ERROR, "طول التوب لازم يكون أكبر من صفر", "roll_length_m", ln.line_no)
            )
    return issues


def check_v3_remnant(lay, lines) -> list:
    """A remnant at or beyond one lay length means a whole extra ply was left."""
    issues = []
    for ln in lines:
        if ln.remnant_m is not None and ln.remnant_m >= lay.lay_length_m:
            issues.append(
                Issue(
                    "V3",
                    ERROR,
                    "الباقي أكبر من طول الفرشة — كان ينفع راق زيادة",
                    "remnant_m",
                    ln.line_no,
                )
            )
    return issues


def check_v4_roll_arithmetic(lay, lines, tolerance_pct: Decimal) -> list:
    """roll_length ≈ plies × lay_length + remnant, within tolerance.

    Skipped for spliced rows (the roll ran out mid-ply, so the arithmetic is
    shared with the next row) and for the quick mode's aggregate row.

    **Always a warning, never a block, in either entry mode.** A supervisor who
    cannot close is not going to go back and re-measure the roll — he is going
    to change the number until the screen lets him through. Blocking here buys
    tidy rows and costs true ones. The lay is flagged `has_length_mismatch`
    instead, and the reports surface it.
    """
    issues = []
    level = WARNING
    for ln in lines:
        if ln.has_splice or ln.is_aggregate:
            continue
        expected = ln.plies * lay.lay_length_m + ln.remnant_m
        if expected <= 0:
            continue
        drift = abs(ln.roll_length_m - expected)
        allowed = expected * tolerance_pct / Decimal("100")
        if drift > allowed:
            issues.append(
                Issue(
                    "V4",
                    level,
                    f"أطوال التوب مش مظبوطة: {ln.roll_length_m} م والمفروض {expected} م",
                    "roll_length_m",
                    ln.line_no,
                )
            )
    return issues


def check_v5_has_lines(lines) -> list:
    if not lines:
        return [Issue("V5", ERROR, "مفيش سطر واحد في الفرشة — مينفعش تتقفل")]
    return []


def check_v6_breakdown_total(lay, breakdown) -> list:
    """The size breakdown must add up to the pieces in one ply."""
    if not breakdown:
        return [Issue("V6", ERROR, "مفيش مقاسات مسجّلة على الفرشة", "size_breakdown")]
    total = sum(b.pieces_in_ply for b in breakdown)
    if total != lay.pieces_per_ply:
        return [
            Issue(
                "V6",
                ERROR,
                f"مجموع المقاسات ({total}) مش مطابق لعدد القطع في الراق ({lay.pieces_per_ply})",
                "size_breakdown",
            )
        ]
    return []


def check_v7_team_leader_present(lay) -> list:
    """The team leader should have punched on some day inside the lay period.

    Skipped without complaint for a backfilled lay, and for any lay older than
    the first punch on record — that history simply does not exist (SRS 6).
    """
    if lay.is_backfill:
        return []
    data_start = attendance_data_start()
    if data_start is None or lay.end_date < data_start:
        return []
    codes = present_codes(lay.start_date, lay.end_date)
    if lay.team_leader.employee_code in codes:
        return []
    return [
        Issue(
            "V7",
            WARNING,
            f"{lay.team_leader.full_name} مش مسجّل حضور في أي يوم من أيام الفرشة",
            "team_leader",
        )
    ]


def check_v8_shade_mix(lines) -> list:
    """More than one shade on one lay is allowed and normal — just say so."""
    shades = {ln.shade_note.strip() for ln in lines if ln.shade_note.strip()}
    if len(shades) > 1:
        return [
            Issue(
                "V8",
                INFO,
                "الفرشة فيها أكتر من درجة لون: " + " / ".join(sorted(shades)),
                "shade_note",
            )
        ]
    return []


def check_v9_actual_not_above_theoretical(lay, actual_pieces: int) -> list:
    if actual_pieces > lay.theoretical_pieces:
        return [
            Issue(
                "V9",
                ERROR,
                f"القطع الفعلية ({actual_pieces}) أكتر من النظرية "
                f"({lay.theoretical_pieces}) — راجع الراق",
                "actual_pieces",
            )
        ]
    return []


# --- entry points --------------------------------------------------------

def validate_for_close(lay, settings=None) -> list:
    """Everything that must hold before a lay can be closed."""
    from .models import CuttingSettings

    settings = settings or CuttingSettings.get_solo()
    lines = list(lay.lines.all())
    breakdown = list(lay.size_breakdown.all())

    issues = []
    issues += check_v5_has_lines(lines)
    issues += check_v2_line_positives(lines)
    issues += check_v3_remnant(lay, lines)
    issues += check_v4_roll_arithmetic(lay, lines, settings.fabric_tolerance_pct)
    issues += check_v1_lay_width(lay, lines)
    issues += check_v6_breakdown_total(lay, breakdown)
    issues += check_v7_team_leader_present(lay)
    issues += check_v8_shade_mix(lines)

    # SRS 4.6: the notebook page is the original record — no closing without it.
    if not lay.sheet_image:
        issues.append(
            Issue("V10", ERROR, "صورة ورقة الدفتر مطلوبة قبل القفل", "sheet_image")
        )
    return issues


def validate_output(lay, actual_pieces: int) -> list:
    """Everything that must hold before a count can be recorded."""
    issues = []
    if lay.status not in (lay.STATUS_CLOSED, lay.STATUS_COUNTED, lay.STATUS_APPROVED):
        issues.append(Issue("V5", ERROR, "الفرشة لازم تتقفل قبل تسجيل القطع", "status"))
    issues += check_v9_actual_not_above_theoretical(lay, actual_pieces)
    return issues
