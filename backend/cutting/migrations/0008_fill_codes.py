"""Fill the two code columns 0007 added. Data only — the unique constraint on
Lay.code lands in 0009, because Postgres will not build the index in the same
transaction as the updates that make it valid.
"""
from django.db import migrations


def number_the_models(apps, schema_editor):
    """Renumber every model from 1 in creation order.

    Runs AFTER the lay codes are recovered, because those are read out of this
    very column: whatever is in here is a cutting-run number typed by hand,
    which means nothing on a model but everything on the run it came from.
    """
    GarmentModel = apps.get_model("cutting", "GarmentModel")
    for i, model in enumerate(GarmentModel.objects.order_by("id"), start=1):
        GarmentModel.objects.filter(pk=model.pk).update(code=str(i))


def seed_lay_codes(apps, schema_editor):
    """Recover each lay's real cutting-run code from the model it points at.

    Before this change there was nowhere to write the number from the notebook
    header, so it was typed into the model's `code` — which is why the live
    catalogue holds one "model" per cut, named things like "مواليد karl" with
    code 1688. That code is the run's, so it moves to the run.

    Where two lays share a model the second cannot take the same code (it is
    about to become unique), so it gets a suffix rather than being dropped. A
    lay whose model has no usable code falls back to its row id.
    """
    Lay = apps.get_model("cutting", "Lay")
    taken = set(
        Lay.objects.exclude(code="").values_list("code", flat=True)
    )

    for lay in Lay.objects.filter(code="").select_related("garment_model").order_by("id"):
        candidate = (lay.garment_model.code or "").strip() or str(lay.pk)
        code = candidate
        suffix = 1
        while code in taken:
            suffix += 1
            code = f"{candidate}-{suffix}"
        taken.add(code)
        Lay.objects.filter(pk=lay.pk).update(code=code)


class Migration(migrations.Migration):
    dependencies = [("cutting", "0007_drop_fit_and_move_the_code")]

    operations = [
        # Order is load-bearing: the lay codes are read out of the model codes
        # before the model codes are overwritten.
        migrations.RunPython(seed_lay_codes, migrations.RunPython.noop),
        migrations.RunPython(number_the_models, migrations.RunPython.noop),
    ]
