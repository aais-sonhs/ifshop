from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0027_orderitem_sequence'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotationitem',
            name='cost_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=0,
                max_digits=15,
                null=True,
                verbose_name='Giá vốn tại thời điểm báo giá',
            ),
        ),
    ]
