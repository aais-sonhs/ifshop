from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0013_payment_approval'),
    ]

    operations = [
        migrations.AlterField(
            model_name='payment',
            name='amount',
            field=models.DecimalField(decimal_places=0, default=0, max_digits=18, verbose_name='Số tiền thực chi'),
        ),
        migrations.AddField(
            model_name='payment',
            name='promotion_amount',
            field=models.DecimalField(decimal_places=0, default=0, max_digits=18, verbose_name='Tiền khuyến mãi'),
        ),
        migrations.AddField(
            model_name='payment',
            name='promotion_mode',
            field=models.CharField(choices=[('amount', 'Số tiền'), ('percent', 'Phần trăm')], default='amount', max_length=10, verbose_name='Cách tính khuyến mãi'),
        ),
        migrations.AddField(
            model_name='payment',
            name='promotion_percent',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5, verbose_name='Khuyến mãi (%)'),
        ),
    ]
