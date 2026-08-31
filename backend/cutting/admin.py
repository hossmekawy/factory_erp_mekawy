from django.contrib import admin

from .models import CuttingOrder, FabricRoll, Marker


class MarkerInline(admin.TabularInline):
    model = Marker
    extra = 0


class FabricRollInline(admin.TabularInline):
    model = FabricRoll
    extra = 0


@admin.register(CuttingOrder)
class CuttingOrderAdmin(admin.ModelAdmin):
    list_display = ["code", "model_name", "color", "cutting_date", "created_by"]
    search_fields = ["code", "model_name", "production_order_no"]
    inlines = [MarkerInline, FabricRollInline]
