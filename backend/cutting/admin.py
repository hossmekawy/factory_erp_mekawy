from django.contrib import admin

from .models import (
    Bank,
    CuttingSettings,
    GarmentModel,
    Lay,
    LayAudit,
    LayLine,
    LayOutput,
    LaySizeBreakdown,
    RemnantLog,
    SizeSet,
)


@admin.register(Bank)
class BankAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "is_active"]
    search_fields = ["code", "name"]


@admin.register(SizeSet)
class SizeSetAdmin(admin.ModelAdmin):
    list_display = ["name", "sizes_raw", "total_pieces", "is_active"]
    search_fields = ["name", "sizes_raw"]
    readonly_fields = ["total_pieces"]


@admin.register(GarmentModel)
class GarmentModelAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "category", "fit", "is_active"]
    search_fields = ["code", "name", "fit"]
    list_filter = ["category", "is_active"]


class LayLineInline(admin.TabularInline):
    model = LayLine
    extra = 0


class LaySizeBreakdownInline(admin.TabularInline):
    model = LaySizeBreakdown
    extra = 0


@admin.register(Lay)
class LayAdmin(admin.ModelAdmin):
    list_display = [
        "id", "start_date", "end_date", "garment_model", "bank", "team_leader",
        "total_plies", "theoretical_pieces", "real_metrage", "deviation_pct", "status",
    ]
    list_filter = ["status", "entry_mode", "is_backfill", "has_shortage", "bank"]
    search_fields = ["garment_model__code", "garment_model__name", "team_leader__full_name"]
    date_hierarchy = "start_date"
    inlines = [LaySizeBreakdownInline, LayLineInline]
    # Written by services.recalculate — editing them by hand would be a lie.
    readonly_fields = [
        "total_plies", "theoretical_pieces", "total_roll_length_m", "total_remnant_m",
        "consumed_m", "fabric_shortage_m", "expected_metrage", "real_metrage",
        "deviation_pct", "has_shortage", "has_splice", "closed_at", "closed_by",
    ]


@admin.register(LayOutput)
class LayOutputAdmin(admin.ModelAdmin):
    list_display = ["lay", "actual_pieces", "rejected_pieces", "recorded_by", "recorded_at"]


@admin.register(RemnantLog)
class RemnantLogAdmin(admin.ModelAdmin):
    list_display = ["lay_line", "length_m", "disposition", "article", "lot_no", "logged_at"]
    list_filter = ["disposition"]


@admin.register(LayAudit)
class LayAuditAdmin(admin.ModelAdmin):
    list_display = ["lay", "action", "field", "user", "at"]
    list_filter = ["action"]


admin.site.register(CuttingSettings)
