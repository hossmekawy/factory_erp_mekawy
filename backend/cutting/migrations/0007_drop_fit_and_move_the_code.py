"""The number in the notebook header belongs to the **cutting run**, not to the
garment model.

The same model is cut many times and each run gets a fresh code so two runs
never get mixed up. So `Lay.code` is new, and `GarmentModel.code` stops being
something anyone types — models are found by name ("كارل رجالي") and their code
becomes a generated handle.

`Fit` (سليم / واسع) goes too. It was in the SRS but is not wanted.

The schema changes live here and the data that fills them lives in 0008:
Postgres refuses to rebuild an index in the same transaction that updated the
rows underneath it.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cutting", "0006_category")]

    operations = [
        migrations.RemoveField(model_name="garmentmodel", name="category_text"),
        migrations.RemoveField(model_name="garmentmodel", name="fit"),
        migrations.DeleteModel(name="Fit"),
        migrations.AlterField(
            model_name="garmentmodel",
            name="code",
            field=models.CharField(blank=True, db_index=True, max_length=30, unique=True,
                                   verbose_name="كود الموديل"),
        ),
        migrations.AddField(
            model_name="lay",
            name="code",
            field=models.CharField(db_index=True, default="", max_length=30,
                                   verbose_name="كود القصة"),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name="garmentmodel",
            options={"ordering": ["name"], "verbose_name": "موديل",
                     "verbose_name_plural": "الموديلات"},
        ),
    ]
