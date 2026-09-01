"""Every calculation in the cutting module. Views and serializers call in here
and never do arithmetic of their own.

**Why the results are stored on `Lay` instead of being properties:** SRS 7.1.2
asks for range filters on deviation % and real metrage and a "has shortage"
filter, and `django-filter` cannot filter a Python property — it needs a
column. On top of that a property would re-run over every lay's lines on every
list page (N+1), and it would silently rewrite the numbers on an approved lay
if a formula ever changed. A closed lay's figures are a snapshot.

The frontend recomputes the same formulas live for display; this module is the
authority, and the tests pin these numbers, not the frontend's.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from hr.attendance import hours_for

from . import sizes as size_utils
from . import validators
from .models import CuttingSettings, Lay, LayAudit, LayOutput, LaySizeBreakdown, RemnantLog

M2 = Decimal("0.01")     # metres, percentages
M4 = Decimal("0.0001")   # metrage per piece


class LayValidationError(Exception):
    """Raised when a transition is blocked. `issues` carries every problem."""

    def __init__(self, issues):
        self.issues = issues
        super().__init__(" · ".join(str(i) for i in issues))


def _q(value: Decimal, exp: Decimal) -> Decimal:
    return Decimal(value).quantize(exp, rounding=ROUND_HALF_UP)


# --- the formulas --------------------------------------------------------

def total_plies(lines) -> int:
    """Σ plies, minus one per splice.

    A spliced roll finishes a ply that the next roll continues, so that ply
    got written on both notebook rows. Counting it twice would inflate every
    downstream number (SRS 4.8).
    """
    plies = sum(ln.plies for ln in lines)
    splices = sum(1 for ln in lines if ln.has_splice)
    return max(plies - splices, 0)


def calculate(lay, lines=None, output=None, settings=None) -> dict:
    """All derived figures for one lay. Pure: reads, never writes.

    `output` is the counted result, or None while the lay is still awaiting
    numbering — in which case real metrage and deviation stay None rather
    than falling back to the theoretical count. SRS 5.2 is explicit that real
    metrage uses the pieces that were actually counted.
    """
    if lines is None:
        lines = list(lay.lines.all())
    if output is None:
        output = getattr(lay, "output", None)
    settings = settings or CuttingSettings.get_solo()

    plies = total_plies(lines)
    theoretical_pieces = plies * lay.pieces_per_ply
    roll_length = sum((ln.roll_length_m for ln in lines), Decimal("0"))
    remnant = sum((ln.remnant_m for ln in lines), Decimal("0"))
    consumed = plies * lay.lay_length_m
    shortage = roll_length - (consumed + remnant)

    expected_metrage = _q(lay.lay_length_m / lay.pieces_per_ply, M4)

    real_metrage = deviation_pct = None
    actual_pieces = output.actual_pieces if output else None
    if actual_pieces:
        real_metrage = _q(roll_length / actual_pieces, M4)
        if expected_metrage > 0:
            deviation_pct = _q(
                (real_metrage - expected_metrage) / expected_metrage * 100, M2
            )

    # Tolerance is a share of the fabric that went onto the table. A surplus
    # is not a shortage, so only the positive direction raises the flag.
    has_shortage = False
    if roll_length > 0 and shortage > 0:
        shortage_pct = shortage / roll_length * 100
        has_shortage = shortage_pct > settings.fabric_tolerance_pct

    # V4 drift is recorded as a flag rather than blocking the close, so it has
    # to be a column: SRS 9.2 reports on it and 7.1.2 filters by it.
    has_length_mismatch = bool(
        validators.check_v4_roll_arithmetic(lay, lines, settings.fabric_tolerance_pct)
    )

    return {
        "total_plies": plies,
        "theoretical_pieces": theoretical_pieces,
        "total_roll_length_m": _q(roll_length, M2),
        "total_remnant_m": _q(remnant, M2),
        "consumed_m": _q(consumed, M2),
        "fabric_shortage_m": _q(shortage, M2),
        "expected_metrage": expected_metrage,
        "real_metrage": real_metrage,
        "deviation_pct": deviation_pct,
        "has_shortage": has_shortage,
        "has_length_mismatch": has_length_mismatch,
        "has_splice": any(ln.has_splice for ln in lines),
    }


def recalculate(lay, save: bool = True) -> dict:
    """Recompute and write the stored columns. Returns what it wrote."""
    values = calculate(lay)
    if save:
        Lay.objects.filter(pk=lay.pk).update(**values)
        for field, value in values.items():
            setattr(lay, field, value)
    return values


def pieces_loss_for(lay, actual_pieces: int) -> dict:
    """Theoretical minus a given count, and whether it breaks the tolerance.

    Split out from `pieces_loss` so the counting screen can show the loss for a
    number the supervisor is still typing, before anything is stored.
    """
    settings = CuttingSettings.get_solo()
    loss = lay.theoretical_pieces - actual_pieces
    loss_pct = None
    exceeds = False
    if lay.theoretical_pieces:
        loss_pct = _q(Decimal(loss) / lay.theoretical_pieces * 100, M2)
        exceeds = loss_pct > settings.pieces_tolerance_pct
    return {"pieces_loss": loss, "pieces_loss_pct": loss_pct, "exceeds_tolerance": exceeds}


def pieces_loss(lay, output=None) -> dict:
    """Theoretical minus counted, and whether it breaks the pieces tolerance."""
    output = output if output is not None else getattr(lay, "output", None)
    if output is None:
        return {"pieces_loss": None, "pieces_loss_pct": None, "exceeds_tolerance": False}
    return pieces_loss_for(lay, output.actual_pieces)


# --- size breakdown ------------------------------------------------------

def sync_breakdown_from_size_set(lay, size_set=None):
    """Snapshot the size set onto the lay, and set pieces_per_ply from it.

    A snapshot, not a live reference: re-pointing the model at a different
    size set later must not rewrite lays that are already closed (SRS 4.9).
    """
    size_set = size_set or lay.size_set
    if size_set is None:
        return []

    pairs = size_set.parsed()
    lay.size_breakdown.all().delete()
    rows = [
        LaySizeBreakdown(lay=lay, size=size, pieces_in_ply=pieces, order=i)
        for i, (size, pieces) in enumerate(pairs)
    ]
    LaySizeBreakdown.objects.bulk_create(rows)

    total = sum(pieces for _size, pieces in pairs)
    if lay.pieces_per_ply != total:
        Lay.objects.filter(pk=lay.pk).update(pieces_per_ply=total)
        lay.pieces_per_ply = total
    return rows


def distribute_actual_pieces(lay, actual_pieces: int, manual: dict = None) -> dict:
    """Spread the counted total across the sizes and store it.

    Automatic by largest remainder. `manual` overrides it size-by-size, and
    then the parts must still add to the total exactly — the SRS calls any
    other outcome a bug (4.9).
    """
    breakdown = list(lay.size_breakdown.all())
    if not breakdown:
        return {}

    if manual:
        result = {str(k): int(v) for k, v in manual.items()}
        known = {b.size for b in breakdown}
        if set(result) != known:
            raise ValueError("التوزيع اليدوي لازم يشمل كل مقاسات الفرشة ومحدش زيادة")
        if sum(result.values()) != actual_pieces:
            raise ValueError(
                f"مجموع المقاسات ({sum(result.values())}) مش مطابق "
                f"لإجمالي القطع ({actual_pieces})"
            )
    else:
        result = size_utils.distribute(
            actual_pieces, [(b.size, b.pieces_in_ply) for b in breakdown]
        )

    for row in breakdown:
        row.actual_pieces = result[row.size]
        row.is_manually_adjusted = bool(manual)
    LaySizeBreakdown.objects.bulk_update(breakdown, ["actual_pieces", "is_manually_adjusted"])
    return result


# --- remnants ------------------------------------------------------------

def sync_remnant_logs(lay):
    """Write one RemnantLog per line that left fabric behind (SRS 4.3.1).

    Informational only — no balance, no stock movement.
    """
    threshold = CuttingSettings.get_solo().remnant_waste_threshold_m
    logs = []
    for line in lay.lines.all():
        RemnantLog.objects.filter(lay_line=line).delete()
        if line.remnant_m and line.remnant_m > 0:
            logs.append(
                RemnantLog(
                    lay_line=line,
                    length_m=line.remnant_m,
                    shade_note=line.shade_note,
                    lot_no=line.lot_no,
                    article=line.article,
                    disposition=line.classify_remnant(threshold),
                )
            )
    RemnantLog.objects.bulk_create(logs)
    return logs


# --- transitions ---------------------------------------------------------

@transaction.atomic
def close_lay(lay, user, override_reason: str = "") -> dict:
    """Run every closing check, freeze the numbers, mark the lay closed.

    Warnings are allowed through only with a reason, which is recorded.
    """
    issues = validators.validate_for_close(lay)
    if validators.has_errors(issues):
        raise LayValidationError(validators.errors_in(issues))

    warnings = [i for i in issues if i.level == validators.WARNING]
    if warnings and not override_reason:
        raise LayValidationError(warnings)

    values = recalculate(lay)
    sync_remnant_logs(lay)

    now = timezone.now()
    Lay.objects.filter(pk=lay.pk).update(
        status=Lay.STATUS_CLOSED, closed_at=now, closed_by=user, end_date=lay.end_date
    )
    lay.status, lay.closed_at, lay.closed_by = Lay.STATUS_CLOSED, now, user

    LayAudit.objects.create(
        lay=lay,
        user=user,
        action="close",
        reason=override_reason,
        new_value="; ".join(str(w) for w in warnings),
    )
    return {"values": values, "issues": issues}


@transaction.atomic
def record_output(
    lay, user, actual_pieces: int, rejected_pieces: int = 0, notes: str = "", manual: dict = None
) -> LayOutput:
    """Record the count from the numbering screen and recompute real metrage."""
    issues = validators.validate_output(lay, actual_pieces)
    if validators.has_errors(issues):
        raise LayValidationError(validators.errors_in(issues))

    output, _created = LayOutput.objects.update_or_create(
        lay=lay,
        defaults={
            "actual_pieces": actual_pieces,
            "rejected_pieces": rejected_pieces,
            "recorded_by": user,
            "notes": notes,
        },
    )
    lay.output = output
    distribute_actual_pieces(lay, actual_pieces, manual=manual)
    recalculate(lay)

    if lay.status == Lay.STATUS_CLOSED:
        Lay.objects.filter(pk=lay.pk).update(status=Lay.STATUS_COUNTED)
        lay.status = Lay.STATUS_COUNTED

    LayAudit.objects.create(
        lay=lay,
        user=user,
        action="output",
        field="actual_pieces",
        new_value=str(actual_pieces),
        reason=notes,
    )
    return output


# --- querying ------------------------------------------------------------

def lays_intersecting(queryset, start, end):
    """Lays whose period overlaps [start, end] — not just those that began in it.

    A lay spread across two days belongs to both (SRS 5.6). `end_date` is
    never null precisely so this stays a plain indexed comparison.
    """
    if start is not None:
        queryset = queryset.filter(end_date__gte=start)
    if end is not None:
        queryset = queryset.filter(start_date__lte=end)
    return queryset


# --- productivity --------------------------------------------------------

def team_leader_productivity(lay) -> dict:
    """Pieces per hour for the lay's team leader across the lay's days.

    Days where the leader punched once and never punched out score zero hours;
    they are dropped from the denominator rather than counted as a zero, and
    the coverage that remains is reported next to the number. A missing figure
    beats a made-up one — see SRS section 6.
    """
    output = getattr(lay, "output", None)
    period = hours_for(lay.team_leader.employee_code, lay.start_date, lay.end_date)

    pieces = output.actual_pieces if output else None
    hours = period.total_hours
    pieces_per_hour = None
    if pieces and hours > 0:
        pieces_per_hour = round(pieces / hours, 2)

    return {
        "employee_code": lay.team_leader.employee_code,
        "full_name": lay.team_leader.full_name,
        "actual_pieces": pieces,
        "total_hours": hours,
        "pieces_per_hour": pieces_per_hour,
        "measured_days": period.measured_days,
        "days_present": period.days_present,
        "total_days": period.total_days,
        "coverage_pct": period.coverage_pct,
        "coverage_label": period.coverage_label,
        "is_reliable": period.is_reliable,
        "unavailable_reason": None if pieces_per_hour is not None else _why_unavailable(pieces, period),
    }


def _why_unavailable(pieces, period) -> str:
    if pieces is None:
        return "الفرشة لسه مستنية ترقيم"
    if period.days_present == 0:
        return "مفيش بصمة لرئيس الفريق في أيام الفرشة"
    return "كل أيام رئيس الفريق فيها بصمة واحدة — الساعات مش متاحة"
