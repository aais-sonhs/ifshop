from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0022_backfill_order_item_cost_price'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='discount_mode',
            field=models.CharField(
                choices=[('amount', 'Số tiền'), ('percent', 'Phần trăm')],
                default='amount',
                max_length=10,
                verbose_name='Cách chiết khấu',
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='discount_percent',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                verbose_name='Chiết khấu tổng đơn (%)',
            ),
        ),
        migrations.AddField(
            model_name='quotation',
            name='discount_mode',
            field=models.CharField(
                choices=[('amount', 'Số tiền'), ('percent', 'Phần trăm')],
                default='amount',
                max_length=10,
                verbose_name='Cách chiết khấu',
            ),
        ),
        migrations.AddField(
            model_name='quotation',
            name='discount_percent',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                verbose_name='Chiết khấu tổng đơn (%)',
            ),
        ),
    ]
