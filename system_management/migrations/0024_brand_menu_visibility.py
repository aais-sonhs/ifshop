from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('system_management', '0023_add_packing_print_template_choice'),
    ]

    operations = [
        migrations.AddField(
            model_name='brand',
            name='menu_visibility',
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name='Cấu hình hiển thị menu',
            ),
        ),
    ]
