from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0016_stockcheck_stock_applied'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PurchaseReturn',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_deleted', models.BooleanField(default=False, verbose_name='Đã xóa')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='Ngày xóa')),
                ('code', models.CharField(max_length=50, unique=True, verbose_name='Mã phiếu trả nhập')),
                ('status', models.IntegerField(choices=[(0, 'Nháp'), (1, 'Hoàn thành'), (2, 'Hủy')], default=0, verbose_name='Trạng thái')),
                ('stock_applied', models.BooleanField(default=False, verbose_name='Đã trừ tồn kho')),
                ('total_amount', models.DecimalField(decimal_places=0, default=0, max_digits=15, verbose_name='Tổng tiền trả')),
                ('reason', models.TextField(blank=True, null=True, verbose_name='Lý do trả')),
                ('note', models.TextField(blank=True, null=True, verbose_name='Ghi chú')),
                ('return_date', models.DateField(verbose_name='Ngày trả')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchase_returns_created', to=settings.AUTH_USER_MODEL)),
                ('goods_receipt', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='purchase_returns', to='products.goodsreceipt', verbose_name='Phiếu nhập gốc')),
                ('supplier', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchase_returns', to='products.supplier', verbose_name='Nhà cung cấp')),
                ('warehouse', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchase_returns', to='products.warehouse', verbose_name='Kho trả')),
            ],
            options={
                'verbose_name': 'Phiếu trả hàng nhập',
                'verbose_name_plural': 'Phiếu trả hàng nhập',
                'db_table': 'purchase_returns',
                'ordering': ['-return_date', '-id'],
            },
        ),
        migrations.CreateModel(
            name='PurchaseReturnItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Số lượng trả')),
                ('unit_price', models.DecimalField(decimal_places=0, default=0, max_digits=15, verbose_name='Đơn giá trả')),
                ('total_price', models.DecimalField(decimal_places=0, default=0, max_digits=15, verbose_name='Thành tiền')),
                ('note', models.TextField(blank=True, null=True, verbose_name='Ghi chú')),
                ('goods_receipt_item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='purchase_return_items', to='products.goodsreceiptitem', verbose_name='Dòng phiếu nhập')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='purchase_return_items', to='products.product')),
                ('purchase_return', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='products.purchasereturn', verbose_name='Phiếu trả nhập')),
                ('variant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchase_return_items', to='products.productvariant', verbose_name='Biến thể')),
            ],
            options={
                'verbose_name': 'Chi tiết trả hàng nhập',
                'verbose_name_plural': 'Chi tiết trả hàng nhập',
                'db_table': 'purchase_return_items',
                'unique_together': {('purchase_return', 'goods_receipt_item')},
            },
        ),
    ]
