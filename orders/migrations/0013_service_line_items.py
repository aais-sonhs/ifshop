from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0012_order_shipping_fee_order_tags_quotation_shipping_fee_and_more'),
        ('products', '0014_productlocation_and_specification'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderitem',
            name='product',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='order_items', to='products.product', verbose_name='Sản phẩm'),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='item_name',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Tên dòng'),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='unit',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Đơn vị tính'),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='is_service_line',
            field=models.BooleanField(default=False, verbose_name='Dòng dịch vụ/thẻ trống'),
        ),
        migrations.AlterField(
            model_name='quotationitem',
            name='product',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='quotation_items', to='products.product', verbose_name='Sản phẩm'),
        ),
        migrations.AddField(
            model_name='quotationitem',
            name='item_name',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Tên dòng'),
        ),
        migrations.AddField(
            model_name='quotationitem',
            name='unit',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Đơn vị tính'),
        ),
        migrations.AddField(
            model_name='quotationitem',
            name='is_service_line',
            field=models.BooleanField(default=False, verbose_name='Dòng dịch vụ/thẻ trống'),
        ),
    ]
