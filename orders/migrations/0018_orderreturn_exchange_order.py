from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0017_order_return_exchange'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderreturn',
            name='exchange_order',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='source_return_exchange', to='orders.order', verbose_name='Đơn hàng đổi phát sinh'),
        ),
    ]
