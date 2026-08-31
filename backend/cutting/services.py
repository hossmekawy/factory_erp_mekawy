from decimal import Decimal


def _num(value):
    """Decimal → float for JSON, None stays None."""
    if value is None:
        return None
    return float(value)


def compute_summary(cutting) -> dict:
    """Single source of truth for all القصة computed figures.

    Formulas per the factory owner:
    - الميتراج المتوقع (حسية) = طول الفرشة ÷ عدد القطع في الراقة
    - الميتراج الحقيقي = إجمالي أمتار الأتواب ÷ إجمالي القطع
      (إجمالي القطع = عدد القطع في الراقة × عدد الراقات، مجموعة على كل الفرشات)
    """
    markers = list(cutting.markers.prefetch_related("sizes"))
    rolls = list(cutting.rolls.all())

    total_lays = sum(m.lays_count for m in markers)
    total_pieces = sum(m.pieces_per_lay * m.lays_count for m in markers)

    # Pieces per size across all markers, first-seen order preserved.
    size_totals: dict[str, int] = {}
    for m in markers:
        for s in m.sizes.all():
            size_totals[s.label] = size_totals.get(s.label, 0) + s.ratio * m.lays_count
    sizes = [{"label": k, "pieces": v} for k, v in size_totals.items()]

    rolls_total = sum((r.length for r in rolls), Decimal("0"))
    quick_mode = cutting.quick_total_meters is not None and not rolls
    total_meters = cutting.quick_total_meters if quick_mode else rolls_total

    expected_metraj = None
    if markers:
        # Weighted across markers: total marker meters ÷ total pieces per one lay set
        first = markers[0]
        if first.pieces_per_lay:
            expected_metraj = first.marker_length / first.pieces_per_lay

    real_metraj = None
    if total_pieces and total_meters:
        real_metraj = Decimal(total_meters) / total_pieces

    metraj_diff = None
    if expected_metraj is not None and real_metraj is not None:
        metraj_diff = real_metraj - expected_metraj

    total_remnants = sum(
        (r.actual_remaining for r in rolls if r.actual_remaining is not None),
        Decimal("0"),
    )

    shortage = cutting.shortage_quantity if cutting.has_shortage else None

    # Fabric actually consumed = total - remnants; waste = what expected math
    # says should be left over vs. what really happened.
    consumed = None
    consumption_pct = None
    waste_pct = None
    if total_meters:
        consumed = Decimal(total_meters) - total_remnants
        consumption_pct = consumed / Decimal(total_meters) * 100
        if expected_metraj is not None and total_pieces:
            needed = expected_metraj * total_pieces
            waste = consumed - needed
            waste_pct = waste / Decimal(total_meters) * 100

    return {
        "rolls_count": len(rolls),
        "total_meters": _num(total_meters),
        "total_lays": total_lays,
        "total_pieces": total_pieces,
        "sizes": sizes,
        "expected_metraj": _num(expected_metraj),
        "real_metraj": _num(real_metraj),
        "metraj_diff": _num(metraj_diff),
        "total_remnants": _num(total_remnants),
        "shortage_quantity": _num(shortage),
        "consumed_meters": _num(consumed),
        "consumption_pct": _num(consumption_pct),
        "waste_pct": _num(waste_pct),
        "quick_mode": quick_mode,
    }
