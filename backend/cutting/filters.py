import django_filters

from .models import CuttingOrder


class CuttingOrderFilter(django_filters.FilterSet):
    code = django_filters.CharFilter(lookup_expr="icontains")
    model_name = django_filters.CharFilter(lookup_expr="icontains")
    color = django_filters.CharFilter(lookup_expr="icontains")
    production_order_no = django_filters.CharFilter(lookup_expr="icontains")
    date_from = django_filters.DateFilter(field_name="cutting_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="cutting_date", lookup_expr="lte")
    created_by = django_filters.NumberFilter()
    roll_number = django_filters.CharFilter(
        field_name="rolls__roll_number", lookup_expr="icontains", distinct=True
    )
    lot_number = django_filters.CharFilter(
        field_name="rolls__lot_number", lookup_expr="icontains", distinct=True
    )

    class Meta:
        model = CuttingOrder
        fields = []
