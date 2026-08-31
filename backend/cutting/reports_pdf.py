"""PDF rendering of the cutting report (A4/A5 landscape, Arabic RTL)."""
import html as html_lib
from io import BytesIO

from weasyprint import HTML

from .reports import COLUMNS


def _esc(value) -> str:
    return html_lib.escape(str(value if value is not None else "—"))


FILTER_LABELS = {
    "code": "الكود",
    "model_name": "الموديل",
    "color": "اللون",
    "production_order_no": "أمر الإنتاج",
    "date_from": "من",
    "date_to": "إلى",
    "roll_number": "رقم التوب",
    "lot_number": "رقم اللوط",
}


def build_cutting_pdf(report: dict, size: str = "a4") -> BytesIO:
    size = "a5" if str(size).lower() == "a5" else "a4"
    font_size = "9px" if size == "a4" else "7px"

    head = "".join(f"<th>{_esc(title)}</th>" for _, title in COLUMNS)
    rows = []
    for row in report["rows"]:
        cells = "".join(f"<td>{_esc(row.get(key))}</td>" for key, _ in COLUMNS)
        rows.append(f"<tr>{cells}</tr>")
    if not rows:
        rows.append(f"<tr><td colspan='{len(COLUMNS)}' class='empty'>لا توجد نتائج</td></tr>")

    t = report["totals"]
    totals_line = (
        f"إجمالي القصات: {report['count']} — الأتواب: {_esc(t.get('rolls'))} — "
        f"الأمتار: {_esc(t.get('meters'))} — القطع: {_esc(t.get('pieces'))} — "
        f"البواقي: {_esc(t.get('remnants'))} — العجز: {_esc(t.get('shortage'))}"
    )

    filters = report.get("filters") or {}
    filter_line = " — ".join(
        f"{FILTER_LABELS.get(k, k)}: {_esc(v)}" for k, v in filters.items() if k in FILTER_LABELS
    )

    doc = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head><meta charset="utf-8"><style>
  @page {{ size: {size.upper()} landscape; margin: 8mm; }}
  * {{ font-family: 'Amiri', 'Arial'; box-sizing: border-box; }}
  body {{ margin: 0; color: #1e293b; }}
  .title {{ text-align: center; font-size: {"15px" if size == "a4" else "12px"}; font-weight: bold; margin-bottom: 2mm; }}
  .sub {{ text-align: center; font-size: {"10px" if size == "a4" else "8px"}; color: #475569; margin-bottom: 3mm; }}
  table {{ width: 100%; border-collapse: collapse; font-size: {font_size}; }}
  th, td {{ border: 0.5px solid #94a3b8; padding: {"3px" if size == "a4" else "1.5px"}; text-align: center; vertical-align: middle; }}
  thead th {{ background: #b91c1c; color: #fff; }}
  tbody tr:nth-child(even) td {{ background-color: #fef2f2; }}
  .empty {{ padding: 10mm; color: #64748b; }}
  .totals {{ margin-top: 3mm; font-size: {"10px" if size == "a4" else "8px"}; font-weight: bold; text-align: center; }}
</style></head>
<body>
  <div class="title">MR.Mekawy Factory ERP — تقرير مرحلة القص</div>
  <div class="sub">{filter_line or "كل القصات"}</div>
  <table>
    <thead><tr>{head}</tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <div class="totals">{totals_line}</div>
</body>
</html>"""

    buf = BytesIO()
    HTML(string=doc).write_pdf(buf)
    buf.seek(0)
    return buf
