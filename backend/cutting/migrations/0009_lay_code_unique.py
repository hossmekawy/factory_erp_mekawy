"""Make the cutting-run code unique, now that 0008 has given every row one."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cutting", "0008_fill_codes")]

    operations = [
        migrations.AlterField(
            model_name="lay",
            name="code",
            field=models.CharField(db_index=True, max_length=30, unique=True,
                                   verbose_name="كود القصة"),
        ),
    ]
