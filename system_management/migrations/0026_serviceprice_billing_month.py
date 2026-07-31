from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('system_management', '0025_serviceprice_brand'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviceprice',
            name='billing_month',
            field=models.DateField(
                help_text='Lưu ngày đầu tháng, ví dụ 2026-07-01.',
                null=True,
                verbose_name='Tháng áp dụng',
            ),
        ),
        migrations.AddConstraint(
            model_name='serviceprice',
            constraint=models.UniqueConstraint(
                fields=('brand', 'billing_month'),
                name='uniq_service_price_brand_month',
            ),
        ),
    ]
