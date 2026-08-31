"""Cutting report: one dict built once, rendered as JSON / Excel / PDF."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .services import compute_summary

COLUMNS = [
    ("code", "كود القصة"),
    ("model_name", "الموديل"),
    ("color", "اللون"),
    ("production_order_no", "أمر الإنتاج"),
    ("cutting_date", "التاريخ"),
    ("employee", "موظف القص"),
    ("rolls_count", "عدد الأتواب"),
    ("total_meters", "إجمالي الأمتار"),
    ("total_lays", "الراقات"),
    ("total_pieces", "القطع"),
    ("sizes", "المقاسات"),
    ("expected_metraj", "الميتراج المتوقع"),
    ("real_metraj", "الميتراج الحقيقي"),
    ("total_remnants", "البواقي"),
    ("shortage", "العجز"),
    ("waste_pct", "الهالك %"),
]


def _round(v, places=2):
    return None if v is None else round(v, places)


def build_cutting_report(queryset, filters: dict) -> dict:
    rows = []
    totals = {"meters": 0.0, "pieces": 0, "lays": 0, "remnants": 0.0, "shortage": 0.0, "rolls": 0}
    for cutting in queryset.prefetch_related("markers", "rolls").select_related("created_by"):
        s = compute_summary(cutting)
        u = cutting.created_by
        rows.append({
            "id": cutting.id,
            "code": cutting.code,
            "model_name": cutting.model_name,
            "color": cutting.color,
            "production_order_no": cutting.production_order_no,
            "cutting_date": cutting.cutting_date.isoformat(),
            "employee": u.first_name or u.username,
            "rolls_count": s["rolls_count"],
            "total_meters": _round(s["total_meters"]),
            "total_lays": s["total_lays"],
            "total_pieces": s["total_pieces"],
            "sizes": " ".join(f"{z['label']}×{z['pieces']}" for z in s["sizes"]) or None,
            "expected_metraj": _round(s["expected_metraj"], 3),
            "real_metraj": _round(s["real_metraj"], 3),
            "total_remnants": _round(s["total_remnants"]),
            "shortage": _round(s["shortage_quantity"]),
            "waste_pct": _round(s["waste_pct"], 1),
        })
        totals["meters"] += s["total_meters"] or 0
        totals["pieces"] += s["total_pieces"] or 0
        totals["lays"] += s["total_lays"] or 0
        totals["remnants"] += s["total_remnants"] or 0
        totals["shortage"] += s["shortage_quantity"] or 0
        totals["rolls"] += s["rolls_count"] or 0
    return {
        "filters": {k: v for k, v in filters.items() if v},
        "rows": rows,
        "totals": {k: _round(v) for k, v in totals.items()},
        "count": len(rows),
    }


def cutting_report_xlsx(report: dict) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "تقرير القص"
    ws.sheet_view.rightToLeft = True

    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="B91C1C")
    center = Alignment(horizontal="center", vertical="center")
    thin = Side(style="thin", color="94A3B8")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for col, (_, title) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.font = head_font
        cell.fill = head_fill
        cell.alignment = center
        cell.border = border
        key = COLUMNS[col - 1][0]
        ws.column_dimensions[get_column_letter(col)].width = 26 if key == "sizes" else 14

    for r, row in enumerate(report["rows"], start=2):
        for c, (key, _) in enumerate(COLUMNS, start=1):
            cell = ws.cell(row=r, column=c, value=row.get(key))
            cell.alignment = center
            cell.border = border

    total_row = len(report["rows"]) + 2
    t = report["totals"]
    ws.cell(row=total_row, column=1, value="الإجمالي").font = Font(bold=True)
    for key, col_key in [
        ("rolls", "rolls_count"), ("meters", "total_meters"),
        ("lays", "total_lays"), ("pieces", "total_pieces"),
        ("remnants", "total_remnants"), ("shortage", "shortage"),
    ]:
        idx = next(i for i, (k, _) in enumerate(COLUMNS, start=1) if k == col_key)
        cell = ws.cell(row=total_row, column=idx, value=t.get(key))
        cell.font = Font(bold=True)
        cell.alignment = center

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
