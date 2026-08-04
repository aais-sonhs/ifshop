import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('system_management', '0026_serviceprice_billing_month'),
    ]

    operations = [
        migrations.AddField(
            model_name='businessconfig',
            name='financial_period_start_day',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='Áp dụng chung cho báo cáo bán hàng và báo cáo tài chính.',
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(28),
                ],
                verbose_name='Ngày bắt đầu kỳ báo cáo',
            ),
        ),
    ]
