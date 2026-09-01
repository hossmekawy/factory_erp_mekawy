"""Fill the two code columns 0007 added. Data only — the unique constraint on
Lay.code lands in 0009, because Postgres will not build the index in the same
transaction as the updates that make it valid.
"""
from django.db import migrations


def number_the_models(apps, schema_editor):
    """Renumber every model from 1 in creation order. Whatever was in there was
    a cutting-run number typed by hand, which means nothing on a model."""
    GarmentModel = apps.get_model("cutting", "GarmentModel")
    for i, model in enumerate(GarmentModel.objects.order_by("id"), start=1):
        GarmentModel.objects.filter(pk=model.pk).update(code=str(i))


def seed_lay_codes(apps, schema_editor):
    """A new install has no lays and this does nothing. One that already has
    them predates the field, so there is no real code to recover — the row id
    is used, which is at least unique and traceable."""
    Lay = apps.get_model("cutting", "Lay")
    for lay in Lay.objects.filter(code="").only("id"):
        Lay.objects.filter(pk=lay.pk).update(code=str(lay.pk))


class Migration(migrations.Migration):
    dependencies = [("cutting", "0007_drop_fit_and_move_the_code")]

    operations = [
        migrations.RunPython(number_the_models, migrations.RunPython.noop),
        migrations.RunPython(seed_lay_codes, migrations.RunPython.noop),
    ]
