from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('system_management', '0021_businessconfig_opt_quotation_validity'),
    ]

    operations = [
        migrations.AddField(
            model_name='brand',
            name='print_priority',
            field=models.PositiveIntegerField(
                default=100,
                verbose_name='Thứ tự ưu tiên khi in',
            ),
        ),
    ]
