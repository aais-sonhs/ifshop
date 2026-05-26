from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('system_management', '0014_print_template_options_history'),
    ]

    operations = [
        migrations.AddField(
            model_name='printtemplate',
            name='show_print_time',
            field=models.BooleanField(default=True, verbose_name='Hiện thời gian in tự động'),
        ),
    ]
