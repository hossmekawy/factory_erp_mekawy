"""django-filter definitions covering SRS 7.1.2, group by group.

Filters combine with AND; several values inside one filter combine with OR
(pick three shades and you get lays matching any of them).

The date filter is an **intersection**, not a start-date match: a lay spread
over two days belongs to any window either day touches (SRS 5.6). That is why
`Lay.end_date` is never null — the comparison stays indexable.
"""
import django_filters as df
from django.db.models import Count, F, FloatField, Q, Value
from django.db.models.functions import Cast, NullIf

from .models import Lay, LayLine, RemnantLog


class CharInFilter(df.BaseInFilter, df.CharFilter):
    """?article=MEGAN,BLACK MIMAS — OR within the one filter."""


class NumberInFilter(df.BaseInFilter, df.NumberFilter):
    pass


class LayFilter(df.FilterSet):
    # --- time -----------------------------------------------------------
    date_from = df.DateFilter(method="filter_date_from", label="من تاريخ")
    date_to = df.DateFilter(method="filter_date_to", label="إلى تاريخ")

    # --- model ----------------------------------------------------------
    garment_model = NumberInFilter(field_name="garment_model_id", lookup_expr="in")
    model_code = CharInFilter(field_name="garment_model__code", lookup_expr="in")
    category = CharInFilter(field_name="garment_model__category__name", lookup_expr="in")
    category_id = NumberInFilter(field_name="garment_model__category_id", lookup_expr="in")
    code = CharInFilter(field_name="code", lookup_expr="in")

    # --- sizes ----------------------------------------------------------
    size = CharInFilter(field_name="size_breakdown__size", lookup_expr="in",
                        distinct=True, label="مقاس موجود في الفرشة")
    size_set = NumberInFilter(field_name="size_set_id", lookup_expr="in")
    size_count_min = df.NumberFilter(method="filter_size_count_min")
    size_count_max = df.NumberFilter(method="filter_size_count_max")

    # --- measurements ---------------------------------------------------
    lay_length_min = df.NumberFilter(field_name="lay_length_m", lookup_expr="gte")
    lay_length_max = df.NumberFilter(field_name="lay_length_m", lookup_expr="lte")
    lay_width_min = df.NumberFilter(field_name="lay_width_cm", lookup_expr="gte")
    lay_width_max = df.NumberFilter(field_name="lay_width_cm", lookup_expr="lte")
    total_plies_min = df.NumberFilter(field_name="total_plies", lookup_expr="gte")
    total_plies_max = df.NumberFilter(field_name="total_plies", lookup_expr="lte")

    # --- pieces ---------------------------------------------------------
    theoretical_pieces_min = df.NumberFilter(field_name="theoretical_pieces", lookup_expr="gte")
    theoretical_pieces_max = df.NumberFilter(field_name="theoretical_pieces", lookup_expr="lte")
    actual_pieces_min = df.NumberFilter(field_name="output__actual_pieces", lookup_expr="gte")
    actual_pieces_max = df.NumberFilter(field_name="output__actual_pieces", lookup_expr="lte")
    pieces_loss_pct_min = df.NumberFilter(field_name="pieces_loss_pct", lookup_expr="gte")
    pieces_loss_pct_max = df.NumberFilter(field_name="pieces_loss_pct", lookup_expr="lte")

    # --- metrage --------------------------------------------------------
    expected_metrage_min = df.NumberFilter(field_name="expected_metrage", lookup_expr="gte")
    expected_metrage_max = df.NumberFilter(field_name="expected_metrage", lookup_expr="lte")
    real_metrage_min = df.NumberFilter(field_name="real_metrage", lookup_expr="gte")
    real_metrage_max = df.NumberFilter(field_name="real_metrage", lookup_expr="lte")
    deviation_min = df.NumberFilter(field_name="deviation_pct", lookup_expr="gte")
    deviation_max = df.NumberFilter(field_name="deviation_pct", lookup_expr="lte")

    # --- fabric ---------------------------------------------------------
    # Only the shade. Article and lot have no input anywhere, so filtering on
    # them could only ever return nothing.
    shade_note = CharInFilter(field_name="lines__shade_note", lookup_expr="in", distinct=True)
    total_roll_length_min = df.NumberFilter(field_name="total_roll_length_m", lookup_expr="gte")
    total_roll_length_max = df.NumberFilter(field_name="total_roll_length_m", lookup_expr="lte")

    # --- remnants -------------------------------------------------------
    has_remnants = df.BooleanFilter(method="filter_has_remnants")
    has_waste_remnants = df.BooleanFilter(method="filter_has_waste_remnants")
    total_remnant_min = df.NumberFilter(field_name="total_remnant_m", lookup_expr="gte")
    total_remnant_max = df.NumberFilter(field_name="total_remnant_m", lookup_expr="lte")

    # --- people ---------------------------------------------------------
    bank_code = CharInFilter(field_name="bank__code", lookup_expr="in")
    team_leader_name = df.CharFilter(
        field_name="team_leader__full_name", lookup_expr="icontains"
    )
    team_leader = NumberInFilter(field_name="team_leader_id", lookup_expr="in")
    entered_by = NumberInFilter(field_name="entered_by_id", lookup_expr="in")
    bank = NumberInFilter(field_name="bank_id", lookup_expr="in")

    # --- state ----------------------------------------------------------
    status = CharInFilter(field_name="status", lookup_expr="in")
    entry_mode = CharInFilter(field_name="entry_mode", lookup_expr="in")
    has_sheet_image = df.BooleanFilter(method="filter_has_sheet_image")
    quick_entry = df.BooleanFilter(method="filter_quick_entry")
    awaiting_count = df.BooleanFilter(method="filter_awaiting_count")

    class Meta:
        model = Lay
        fields = ["has_shortage", "has_length_mismatch", "has_splice", "is_backfill"]

    # --- methods --------------------------------------------------------

    def filter_date_from(self, queryset, name, value):
        """A lay whose period reaches into the window, even if it began before."""
        return queryset.filter(end_date__gte=value)

    def filter_date_to(self, queryset, name, value):
        return queryset.filter(start_date__lte=value)

    def filter_size_count_min(self, queryset, name, value):
        return queryset.annotate(_size_count=Count("size_breakdown", distinct=True)).filter(
            _size_count__gte=value
        )

    def filter_size_count_max(self, queryset, name, value):
        return queryset.annotate(_size_count=Count("size_breakdown", distinct=True)).filter(
            _size_count__lte=value
        )

    def filter_has_remnants(self, queryset, name, value):
        lookup = Q(total_remnant_m__gt=0)
        return queryset.filter(lookup) if value else queryset.exclude(lookup)

    def filter_has_waste_remnants(self, queryset, name, value):
        """Lays that left fabric too short to reuse (SRS 5.4)."""
        lookup = Q(lines__remnant_log__disposition=RemnantLog.DISPOSITION_WASTE)
        matched = queryset.filter(lookup) if value else queryset.exclude(lookup)
        return matched.distinct()

    def filter_has_sheet_image(self, queryset, name, value):
        blank = Q(sheet_image="") | Q(sheet_image__isnull=True)
        return queryset.exclude(blank) if value else queryset.filter(blank)

    def filter_quick_entry(self, queryset, name, value):
        """SRS 9.7: how much is being entered in a hurry."""
        lookup = Q(entry_mode=Lay.MODE_QUICK)
        return queryset.filter(lookup) if value else queryset.exclude(lookup)

    def filter_awaiting_count(self, queryset, name, value):
        """Closed but not yet numbered — the numbering screen's worklist."""
        lookup = Q(status=Lay.STATUS_CLOSED, output__isnull=True)
        return queryset.filter(lookup) if value else queryset.exclude(lookup)


def annotate_lay_queryset(queryset):
    """Add the columns that only exist as a ratio, so they can be filtered.

    `pieces_loss_pct` is theoretical minus counted over theoretical. It is not
    stored because it is a plain function of two stored columns; NullIf keeps
    a lay with no plies from dividing by zero.
    """
    return queryset.annotate(
        pieces_loss_pct=(
            Cast(F("theoretical_pieces") - F("output__actual_pieces"), FloatField())
            * Value(100.0)
            / NullIf(Cast(F("theoretical_pieces"), FloatField()), Value(0.0))
        )
    )


class RemnantLogFilter(df.FilterSet):
    date_from = df.DateFilter(field_name="lay_line__lay__end_date", lookup_expr="gte")
    date_to = df.DateFilter(field_name="lay_line__lay__start_date", lookup_expr="lte")
    shade_note = CharInFilter(field_name="shade_note", lookup_expr="in")
    length_min = df.NumberFilter(field_name="length_m", lookup_expr="gte")
    length_max = df.NumberFilter(field_name="length_m", lookup_expr="lte")

    class Meta:
        model = RemnantLog
        fields = ["disposition"]
