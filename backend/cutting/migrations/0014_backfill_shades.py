"""Fill in the shade split for lays that already exist.

0013 added the table but it is written by `services.recalculate`, so a lay
entered before that has lines with shades on them and no breakdown to show.
This derives it once, using the same rule the service uses — including the
splice subtraction, so the shades add up to the ply count already stored.

Quick-mode lays are skipped: they have no per-roll shades to derive from, and
whatever their supervisor may type later is his, not ours to invent.
"""
from django.db import migrations


def backfill(apps, schema_editor):
    Lay = apps.get_model("cutting", "Lay")
    LayShadeBreakdown = apps.get_model("cutting", "LayShadeBreakdown")

    made = 0
    for lay in Lay.objects.exclude(entry_mode="quick").prefetch_related("lines"):
        if lay.shade_breakdown.exists():
            continue
        totals = {}
        for line in lay.lines.all():
            shade = (line.shade_note or "").strip()
            if not shade:
                continue
            spliced = 1 if line.roll_end_action == "splice" else 0
            totals[shade] = totals.get(shade, 0) + line.plies - spliced

        rows = [
            LayShadeBreakdown(lay=lay, shade=shade, plies=plies, order=i, is_manual=False)
            for i, (shade, plies) in enumerate(totals.items())
            if plies > 0
        ]
        LayShadeBreakdown.objects.bulk_create(rows)
        made += len(rows)
    print(f"  backfilled {made} shade rows")


class Migration(migrations.Migration):
    dependencies = [("cutting", "0013_shade_breakdown")]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
