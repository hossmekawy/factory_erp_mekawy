"""`category` stops being a fixed three-value choices list and becomes a
catalogue the factory extends itself (رجالي · حريمي · مواليد · رجالي جامبو …).

Every model must carry one: it is the axis the reports are read along, and a
model without a section drops out of every filter.

The old column's values are carried across rather than dropped, so an install
that already has models keeps them classified.
"""
from django.db import migrations, models
import django.db.models.deletion

SEED = [
    "رجالي", "رجالي خاص", "رجالي جامبو",
    "حريمي", "بناتي", "أولادي", "أطفال", "مواليد",
]
LEGACY = {"men": "رجالي", "women": "حريمي", "kids": "أطفال"}


def build_categories(apps, schema_editor):
    Category = apps.get_model("cutting", "Category")
    GarmentModel = apps.get_model("cutting", "GarmentModel")

    for order, name in enumerate(SEED, start=1):
        Category.objects.get_or_create(name=name, defaults={"order": order})

    for raw in set(
        GarmentModel.objects.exclude(category_text="")
        .values_list("category_text", flat=True)
        .distinct()
    ):
        name = LEGACY.get(raw, raw)
        category, _ = Category.objects.get_or_create(
            name=name, defaults={"order": len(SEED) + 1}
        )
        GarmentModel.objects.filter(category_text=raw).update(category=category)


def restore_text(apps, schema_editor):
    GarmentModel = apps.get_model("cutting", "GarmentModel")
    reverse = {v: k for k, v in LEGACY.items()}
    for model in GarmentModel.objects.select_related("category"):
        name = model.category.name if model.category_id else ""
        GarmentModel.objects.filter(pk=model.pk).update(
            category_text=reverse.get(name, name)
        )


class Migration(migrations.Migration):
    dependencies = [("cutting", "0005_notification")]

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=50, unique=True, verbose_name="القسم")),
                ("notes", models.CharField(blank=True, max_length=200, verbose_name="ملاحظات")),
                ("is_active", models.BooleanField(default=True, verbose_name="نشط")),
                ("order", models.PositiveSmallIntegerField(default=0, verbose_name="الترتيب")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "قسم", "verbose_name_plural": "الأقسام",
                     "ordering": ["order", "name"]},
        ),
        migrations.RenameField(
            model_name="garmentmodel", old_name="category", new_name="category_text",
        ),
        migrations.AddField(
            model_name="garmentmodel",
            name="category",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name="models", to="cutting.category",
                                    verbose_name="القسم"),
        ),
        migrations.RunPython(build_categories, restore_text),
    ]
