"""PDF rendering of the weekly attendance report (A4 with photos, A5 compact).

WeasyPrint shapes/bidi-lays Arabic natively via Pango, so we just build an
HTML table and let it render. Photos are embedded as base64 data URIs.
"""
import base64
import html as html_lib
import mimetypes
from io import BytesIO

from weasyprint import HTML

from .models import Employee


def _photo_data_uri(path) -> str | None:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except (OSError, TypeError):
        return None
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def _esc(value) -> str:
    return html_lib.escape(str(value if value is not None else ""))


def build_weekly_pdf(report: dict, size: str = "a4") -> BytesIO:
    size = "a5" if str(size).lower() == "a5" else "a4"
    with_photos = size == "a4"

    photos = {}
    if with_photos:
        for emp in Employee.objects.filter(is_active=True).exclude(photo=""):
            if emp.photo:
                uri = _photo_data_uri(emp.photo.path)
                if uri:
                    photos[emp.id] = uri

    workdays = report["workdays"]
    font_size = "9px" if size == "a4" else "7px"
    photo_col = "<th class='ph'>الصورة</th>" if with_photos else ""

    head_cells = [photo_col, "<th>الكود</th>", "<th class='nm'>الاسم</th>"]
    for d in workdays:
        head_cells.append(f"<th>{_esc(d['name'])}<br><span class='dt'>{_esc(d['date'][5:])}</span></th>")
    head_cells += [
        "<th>أيام الحضور</th>",
        "<th>أيام الغياب</th>",
        "<th>إجمالي الساعات</th>",
    ]

    rows = []
    for emp in report["employees"]:
        cells = []
        if with_photos:
            uri = photos.get(emp["id"])
            if uri:
                cells.append(f"<td class='ph'><img src='{uri}'></td>")
            else:
                cells.append("<td class='ph'><div class='noimg'>—</div></td>")
        cells.append(f"<td>{_esc(emp['employee_code'])}</td>")
        cells.append(f"<td class='nm'>{_esc(emp['full_name'])}</td>")
        for d in workdays:
            cell = emp["days"][d["date"]]
            if cell["status"] == "present":
                if cell["out"]:
                    inner = (
                        f"<span class='io'>{_esc(cell['in'])} - {_esc(cell['out'])}</span>"
                        f"<br><span class='hr'>{_esc(cell['hours'])} س</span>"
                    )
                else:
                    inner = f"<span class='io'>{_esc(cell['in'])}</span><br><span class='hr'>بصمة واحدة</span>"
                cells.append(f"<td class='present'>{inner}</td>")
            elif cell["status"] == "absent":
                cells.append("<td class='absent'>غياب</td>")
            else:
                cells.append("<td class='none'>—</td>")
        cells.append(f"<td class='tot ok'>{emp['totals']['present']}</td>")
        cells.append(f"<td class='tot bad'>{emp['totals']['absent']}</td>")
        cells.append(f"<td class='tot'>{emp['totals']['hours']}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")

    if not rows:
        span = len(workdays) + (5 if with_photos else 4)
        rows.append(f"<tr><td colspan='{span}' class='empty'>لا يوجد موظفون نشطون</td></tr>")

    doc = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head><meta charset="utf-8"><style>
  @page {{ size: {size.upper()} landscape; margin: 8mm; }}
  * {{ font-family: 'Amiri', 'Arial'; box-sizing: border-box; }}
  body {{ margin: 0; color: #1e293b; }}
  .title {{ text-align: center; font-size: {"15px" if size=="a4" else "12px"}; font-weight: bold; margin-bottom: 2mm; }}
  .sub {{ text-align: center; font-size: {"10px" if size=="a4" else "8px"}; color: #475569; margin-bottom: 3mm; }}
  table {{ width: 100%; border-collapse: collapse; font-size: {font_size}; }}
  th, td {{ border: 0.5px solid #94a3b8; padding: {"3px" if size=="a4" else "1.5px"}; text-align: center; vertical-align: middle; }}
  thead th {{ background: #1e3a5f; color: #fff; }}
  .dt {{ font-weight: normal; font-size: 0.8em; color: #cbd5e1; }}
  td.nm, th.nm {{ text-align: right; white-space: nowrap; font-weight: bold; }}
  .io {{ font-weight: bold; direction: ltr; unicode-bidi: embed; }}
  .hr {{ color: #64748b; font-size: 0.85em; }}
  .present {{ background: #ecfdf5; }}
  .absent {{ background: #fef2f2; color: #b91c1c; font-weight: bold; }}
  .none {{ color: #cbd5e1; }}
  .tot {{ font-weight: bold; }}
  .tot.ok {{ color: #047857; }}
  .tot.bad {{ color: #dc2626; }}
  .ph {{ width: {"11mm" if size=="a4" else "0"}; }}
  .ph img {{ width: 9mm; height: 9mm; border-radius: 50%; object-fit: cover; }}
  .noimg {{ width: 9mm; height: 9mm; border-radius: 50%; background: #e2e8f0; color: #94a3b8; line-height: 9mm; margin: 0 auto; }}
  .empty {{ padding: 10mm; color: #64748b; }}
  tbody tr:nth-child(even) td {{ background-color: #f8fafc; }}
  tbody tr:nth-child(even) td.present {{ background-color: #ecfdf5; }}
  tbody tr:nth-child(even) td.absent {{ background-color: #fef2f2; }}
</style></head>
<body>
  <div class="title">MR.Mekawy Factory ERP — تقرير الحضور الأسبوعي</div>
  <div class="sub">من {_esc(report['week_start'])} إلى {_esc(report['week_end'])} — الدوام {_esc(report['schedule']['work_start'])} إلى {_esc(report['schedule']['work_end'])}، الجمعة إجازة</div>
  <table>
    <thead><tr>{''.join(head_cells)}</tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>"""

    buf = BytesIO()
    HTML(string=doc).write_pdf(buf)
    buf.seek(0)
    return buf
