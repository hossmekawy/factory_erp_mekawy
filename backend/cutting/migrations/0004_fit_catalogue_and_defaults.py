"""Turn GarmentModel.fit from free text into a Fit catalogue, and add the
new-lay defaults to the settings singleton.

The straightforward AlterField from CharField to ForeignKey does not work:
Postgres would have to cast 'سليم' to an integer. So the text column is
renamed aside, the FK added beside it, the values carried across, and the old
column dropped — which also means the reverse migration can put the text back.
"""
from django.db import migrations, models
import django.db.models.deletion


def text_to_catalogue(apps, schema_editor):
    """One Fit row per distinct cut already written, then repoint the models."""
    GarmentModel = apps.get_model("cutting", "GarmentModel")
    Fit = apps.get_model("cutting", "Fit")

    names = (
        GarmentModel.objects.exclude(fit_text="")
        .exclude(fit_text__isnull=True)
        .values_list("fit_text", flat=True)
        .distinct()
    )
    for raw in names:
        name = (raw or "").strip()
        if not name:
            continue
        fit, _ = Fit.objects.get_or_create(name=name)
        GarmentModel.objects.filter(fit_text=raw).update(fit=fit)


def catalogue_to_text(apps, schema_editor):
    GarmentModel = apps.get_model("cutting", "GarmentModel")
    for model in GarmentModel.objects.select_related("fit"):
        GarmentModel.objects.filter(pk=model.pk).update(
            fit_text=model.fit.name if model.fit_id else ""
        )


class Migration(migrations.Migration):
    dependencies = [
        ("hr", "0003_employee_is_team_leader"),
        ("cutting", "0003_savedfilter"),
    ]

    operations = [
        migrations.CreateModel(
            name="Fit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=50, unique=True, verbose_name="القَصّة")),
                ("notes", models.CharField(blank=True, max_length=200, verbose_name="ملاحظات")),
                ("is_active", models.BooleanField(default=True, verbose_name="نشط")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "قَصّة",
                "verbose_name_plural": "القَصّات",
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="cuttingsettings",
            name="default_bank",
            field=models.ForeignKey(blank=True, null=True,
                                    on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="+", to="cutting.bank",
                                    verbose_name="البنك الافتراضي"),
        ),
        migrations.AddField(
            model_name="cuttingsettings",
            name="default_team_leader",
            field=models.ForeignKey(blank=True, null=True,
                                    on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="+", to="hr.employee",
                                    verbose_name="رئيس الفريق الافتراضي"),
        ),
        migrations.RenameField(
            model_name="garmentmodel", old_name="fit", new_name="fit_text",
        ),
        migrations.AddField(
            model_name="garmentmodel",
            name="fit",
            field=models.ForeignKey(blank=True, null=True,
                                    on_delete=django.db.models.deletion.PROTECT,
                                    related_name="models", to="cutting.fit",
                                    verbose_name="القَصّة"),
        ),
        migrations.RunPython(text_to_catalogue, catalogue_to_text),
        migrations.RemoveField(model_name="garmentmodel", name="fit_text"),
    ]
