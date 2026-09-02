"""A printable sheet for one lay — A4 or A5, Arabic, black and white.

The detail screen used to be printed with the browser's own print, which put
the navigation, the buttons and the colours on the paper. This builds a real
document instead: the factory's name and logo at the top, the numbers laid out
to be read, and room to sign at the bottom.

Deliberately grey-scale. These come off an office laser printer and get filed;
colour that survives on screen turns into indistinguishable grey on paper, so
the emphasis is carried by weight and rules rather than by hue.

WeasyPrint shapes and lays out Arabic natively through Pango, so this is plain
HTML — the same approach as hr/reports_pdf.py.
"""
import base64
import html as html_lib
from io import BytesIO

from django.utils import timezone
from weasyprint import HTML

from hr.models import SiteSettings

from . import services


def _esc(value) -> str:
    return html_lib.escape(str(value if value is not None else ""))


def _num(value, places: int = 2) -> str:
    """Latin digits, trailing zeros trimmed — SRS section 10."""
    if value is None:
        return "—"
    text = f"{float(value):.{places}f}".rstrip("0").rstrip(".")
    return text or "0"


def _grey_logo_uri(path) -> str | None:
    """The logo, converted to greyscale and flattened onto white.

    The sheet is printed on an office laser printer, so the colour would come
    out as an indeterminate grey anyway — converting it here means we choose
    which grey rather than letting the driver guess, and the result looks the
    same on every printer. Flattened onto white because a transparent PNG
    prints as a black box on some drivers.
    """
    try:
        from PIL import Image

        with Image.open(path) as img:
            rgba = img.convert("RGBA")
            white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            flat = Image.alpha_composite(white, rgba).convert("L")
            buf = BytesIO()
            flat.save(buf, format="PNG", optimize=True)
    except Exception:  # noqa: BLE001 — a missing logo must not stop the sheet
        return None
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"


def _branding() -> tuple[str, str | None]:
    """The factory's name and logo, from the same settings the site header uses."""
    site = SiteSettings.get_solo()
    logo = None
    for field in (site.icon_512, site.icon_192, site.apple_touch_icon):
        if field:
            logo = _grey_logo_uri(field.path)
            if logo:
                break
    return site.company_name, logo


def _table(headers, rows, widths=None) -> str:
    if not rows:
        return ""
    cols = "".join(
        f'<col style="width:{w}">' for w in widths
    ) if widths else ""
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
    )
    return (
        f"<table><colgroup>{cols}</colgroup>"
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    )


def build_lay_pdf(lay, size: str = "a4") -> BytesIO:
    size = "a5" if str(size).lower() == "a5" else "a4"
    company, logo = _branding()
    model = lay.garment_model
    output = getattr(lay, "output", None)
    loss = services.pieces_loss(lay)

    date = (
        f"{lay.start_date} ← {lay.end_date}" if lay.is_multi_day else str(lay.start_date)
    )

    # --- the six figures everyone looks at first ------------------------
    figures = [
        ("طول القصة", f"{_num(lay.lay_length_m)} م"),
        ("عرض الفرشة", f"{_num(lay.lay_width_cm)} سم"),
        ("إجمالي الراق", str(lay.total_plies)),
        ("القطع", str(output.actual_pieces) if output else str(lay.theoretical_pieces)),
        ("الميتراج المتوقع", _num(lay.expected_metrage, 4)),
        ("الميتراج الحقيقي", _num(lay.real_metrage, 4) if lay.real_metrage else "—"),
    ]
    figures_html = "".join(
        f'<div class="fig"><span class="k">{_esc(k)}</span>'
        f'<span class="v">{_esc(v)}</span></div>'
        for k, v in figures
    )

    # --- sizes -----------------------------------------------------------
    sizes = _table(
        ["المقاس", "في الراق", "النظرية", "الفعلية"],
        [
            [
                _esc(b.size),
                str(b.pieces_in_ply),
                str(b.theoretical_pieces),
                str(b.actual_pieces) if b.actual_pieces is not None else "—",
            ]
            for b in lay.size_breakdown.all()
        ],
    )

    # --- shades ----------------------------------------------------------
    shades = _table(
        ["اللون", "الراق", "القطع", "النسبة"],
        [
            [_esc(r["shade"]), str(r["plies"]), str(r["pieces"]),
             f'{r["pct"]}%' if r["pct"] is not None else "—"]
            for r in services.shade_totals(lay)
        ],
    )

    # --- roll lines ------------------------------------------------------
    lines = _table(
        ["#", "طول التوب", "الراق", "الباقي", "اللون"],
        [
            [
                str(l.line_no), _num(l.roll_length_m), str(l.plies),
                _num(l.remnant_m), _esc(l.shade_note) or "—",
            ]
            for l in lay.lines.all()
        ],
        widths=["8%", "24%", "18%", "20%", "30%"],
    )

    # --- consumption -----------------------------------------------------
    consumption = _table(
        ["أطوال الأتواب", "المستهلك", "البواقي", "العجز"],
        [[
            f"{_num(lay.total_roll_length_m)} م",
            f"{_num(lay.consumed_m)} م",
            f"{_num(lay.total_remnant_m)} م",
            f'<strong>{_num(lay.fabric_shortage_m)} م</strong>',
        ]],
    )

    count_note = ""
    if output:
        pieces_loss = loss["pieces_loss"]
        count_note = (
            f'<p class="note">القطع الفعلية {output.actual_pieces} · '
            f'التالف {output.rejected_pieces} · فاقد {pieces_loss} قطعة'
            + (f' ({_num(loss["pieces_loss_pct"])}%)' if loss["pieces_loss_pct"] is not None else "")
            + (f' · {_esc(output.notes)}' if output.notes else "")
            + "</p>"
        )

    flags = []
    if lay.entry_mode == lay.MODE_QUICK:
        flags.append("إدخال سريع")
    if lay.is_backfill:
        flags.append("مرحّلة")
    if lay.has_shortage:
        flags.append("فيها عجز")
    if lay.has_length_mismatch:
        flags.append("فرق في الأطوال")
    flags_html = (
        '<p class="flags">' + " · ".join(_esc(f) for f in flags) + "</p>" if flags else ""
    )

    logo_html = f'<img class="logo" src="{logo}">' if logo else ""

    # A5 is the same document at a smaller scale, not a different one.
    scale = {
        "a4": {"base": "10px", "fig": "17px", "h1": "16px", "pad": "4px 6px"},
        "a5": {"base": "8px", "fig": "13px", "h1": "13px", "pad": "2px 4px"},
    }[size]

    html = f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">
<style>
  @page {{
    size: {size.upper()} portrait;
    margin: 12mm 10mm 14mm;
    @bottom-center {{
      content: "صفحة " counter(page) " من " counter(pages);
      font-family: 'Amiri', 'DejaVu Sans'; font-size: 8px; color: #555;
    }}
  }}
  * {{ font-family: 'Amiri', 'DejaVu Sans', sans-serif; box-sizing: border-box; }}
  body {{ font-size: {scale['base']}; color: #000; margin: 0; }}

  header {{
    display: flex; align-items: center; gap: 8px;
    border-bottom: 2px solid #000; padding-bottom: 6px; margin-bottom: 8px;
  }}
  .logo {{ width: 42px; height: 42px; object-fit: contain; }}
  .brand {{ flex: 1; }}
  .company {{ font-size: {scale['h1']}; font-weight: 700; line-height: 1.2; }}
  .doc {{ font-size: 9px; color: #444; }}
  .idbox {{ text-align: left; }}
  .code {{ font-size: {scale['h1']}; font-weight: 700; }}
  .status {{
    font-size: 8px; border: 1px solid #000; padding: 1px 6px;
    display: inline-block; margin-top: 2px;
  }}

  .meta {{
    display: flex; flex-wrap: wrap; gap: 0 14px;
    border-bottom: 1px solid #999; padding-bottom: 5px; margin-bottom: 8px;
    font-size: 9px;
  }}
  .meta span strong {{ font-weight: 700; }}

  .figs {{ display: flex; gap: 4px; margin-bottom: 9px; }}
  .fig {{
    flex: 1; border: 1px solid #999; padding: 4px 3px; text-align: center;
  }}
  .fig .k {{ display: block; font-size: 7.5px; color: #444; }}
  .fig .v {{ display: block; font-size: {scale['fig']}; font-weight: 700; }}

  h2 {{
    font-size: 9.5px; margin: 9px 0 3px; padding-bottom: 2px;
    border-bottom: 1px solid #000; font-weight: 700;
  }}
  .cols {{ display: flex; gap: 10px; }}
  .cols > div {{ flex: 1; }}

  table {{ width: 100%; border-collapse: collapse; }}
  th {{
    background: #e8e8e8; border: 1px solid #666; padding: {scale['pad']};
    font-weight: 700; text-align: center;
  }}
  td {{ border: 1px solid #999; padding: {scale['pad']}; text-align: center; }}
  tbody tr:nth-child(even) td {{ background: #f4f4f4; }}

  .note {{ margin: 4px 0 0; font-size: 8.5px; }}
  .flags {{ margin: 3px 0 0; font-size: 8.5px; font-weight: 700; }}
  .notes {{ margin-top: 6px; font-size: 8.5px; }}

  .sign {{
    margin-top: 16px; display: flex; gap: 24px;
    border-top: 1px solid #999; padding-top: 10px;
  }}
  .sign div {{ flex: 1; font-size: 8.5px; }}
  .sign .line {{ border-bottom: 1px dotted #000; height: 22px; margin-top: 2px; }}
  .printed {{ margin-top: 8px; font-size: 7.5px; color: #555; text-align: left; }}
</style></head><body>

<header>
  {logo_html}
  <div class="brand">
    <div class="company">{_esc(company)}</div>
    <div class="doc">تقرير قصة قص</div>
  </div>
  <div class="idbox">
    <div class="code">قصة {_esc(lay.code)}</div>
    <div class="status">{_esc(lay.get_status_display())}</div>
  </div>
</header>

<div class="meta">
  <span>التاريخ: <strong>{_esc(date)}</strong></span>
  <span>الموديل: <strong>{_esc(model.name)}</strong></span>
  <span>القسم: <strong>{_esc(model.category.name if model.category_id else "—")}</strong></span>
  <span>البنك: <strong>{_esc(lay.bank.name)}</strong></span>
  <span>رئيس الفريق: <strong>{_esc(lay.team_leader.full_name)}</strong></span>
  <span>عدد القطع في الراق: <strong>{lay.pieces_per_ply}</strong></span>
</div>

<div class="figs">{figures_html}</div>
{flags_html}

<div class="cols">
  <div><h2>المقاسات</h2>{sizes or '<p class="note">—</p>'}</div>
  <div><h2>الراق لكل لون</h2>{shades or '<p class="note">—</p>'}</div>
</div>

<h2>سطور الأتواب</h2>
{lines or '<p class="note">مفيش سطور</p>'}

<h2>الاستهلاك والعجز</h2>
{consumption}
{count_note}
{f'<p class="notes">ملاحظات: {_esc(lay.notes)}</p>' if lay.notes else ''}

<div class="sign">
  <div>مشرف القص<div class="line"></div></div>
  <div>مدير الإنتاج<div class="line"></div></div>
</div>
<p class="printed">اتطبع في {_esc(timezone.localtime().strftime("%Y-%m-%d %H:%M"))}</p>

</body></html>"""

    buf = BytesIO()
    HTML(string=html).write_pdf(buf)
    buf.seek(0)
    return buf
