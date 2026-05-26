from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('system_management', '0015_printtemplate_show_print_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='printtemplate',
            name='show_combo_components',
            field=models.BooleanField(default=True, verbose_name='Hiện thành phần combo'),
        ),
    ]
