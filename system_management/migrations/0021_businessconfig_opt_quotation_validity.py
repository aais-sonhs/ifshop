from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('system_management', '0020_brand_brand_type_and_constraints'),
    ]

    operations = [
        migrations.AddField(
            model_name='businessconfig',
            name='opt_quotation_validity',
            field=models.BooleanField(default=True, verbose_name='Hiện hiệu lực báo giá'),
        ),
    ]
