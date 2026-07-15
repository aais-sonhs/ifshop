from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0023_order_quotation_discount_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderitem',
            name='discount_amount',
            field=models.DecimalField(
                decimal_places=0,
                default=0,
                max_digits=18,
                verbose_name='Chiết khấu dòng',
            ),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='discount_mode',
            field=models.CharField(
                choices=[('amount', 'Số tiền'), ('percent', 'Phần trăm')],
                default='percent',
                max_length=10,
                verbose_name='Cách chiết khấu dòng',
            ),
        ),
        migrations.AddField(
            model_name='quotationitem',
            name='discount_amount',
            field=models.DecimalField(
                decimal_places=0,
                default=0,
                max_digits=18,
                verbose_name='Chiết khấu dòng',
            ),
        ),
        migrations.AddField(
            model_name='quotationitem',
            name='discount_mode',
            field=models.CharField(
                choices=[('amount', 'Số tiền'), ('percent', 'Phần trăm')],
                default='percent',
                max_length=10,
                verbose_name='Cách chiết khấu dòng',
            ),
        ),
    ]
