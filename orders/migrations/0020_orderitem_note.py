from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0019_order_issuing_brand_quotation_issuing_brand'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderitem',
            name='note',
            field=models.TextField(blank=True, default=None, null=True, verbose_name='Ghi chú theo đơn'),
        ),
    ]
