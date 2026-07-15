import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0024_line_item_discount_mode'),
        ('products', '0018_product_warranty_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WarrantyCertificate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_deleted', models.BooleanField(default=False, verbose_name='Đã xóa')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='Ngày xóa')),
                ('code', models.CharField(max_length=80, unique=True, verbose_name='Mã phiếu bảo hành')),
                ('issue_date', models.DateField(verbose_name='Ngày lập phiếu')),
                ('customer_name', models.CharField(blank=True, max_length=255, verbose_name='Tên khách hàng')),
                ('customer_phone', models.CharField(blank=True, max_length=30, verbose_name='Số điện thoại')),
                ('customer_address', models.TextField(blank=True, verbose_name='Địa chỉ')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='warranty_certificates_created', to=settings.AUTH_USER_MODEL, verbose_name='Người tạo')),
                ('order', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='warranty_certificate', to='orders.order', verbose_name='Đơn hàng')),
            ],
            options={
                'verbose_name': 'Phiếu bảo hành',
                'verbose_name_plural': 'Phiếu bảo hành',
                'db_table': 'warranty_certificates',
                'ordering': ['-issue_date', '-id'],
            },
        ),
        migrations.CreateModel(
            name='WarrantyCertificateItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('product_code', models.CharField(blank=True, max_length=80, verbose_name='Mã sản phẩm')),
                ('product_name', models.CharField(max_length=255, verbose_name='Tên sản phẩm')),
                ('unit', models.CharField(blank=True, max_length=50, verbose_name='Đơn vị tính')),
                ('quantity', models.DecimalField(decimal_places=2, default=1, max_digits=15, verbose_name='Số lượng')),
                ('serial', models.CharField(blank=True, max_length=255, verbose_name='Serial / lô')),
                ('warranty_period_months', models.PositiveIntegerField(default=0, verbose_name='Kỳ hạn bảo hành (tháng)')),
                ('warranty_term', models.CharField(blank=True, max_length=120, verbose_name='Thời hạn bảo hành')),
                ('warranty_policy', models.TextField(blank=True, verbose_name='Chính sách bảo hành')),
                ('warranty_start_date', models.DateField(verbose_name='Ngày bắt đầu bảo hành')),
                ('warranty_end_date', models.DateField(blank=True, null=True, verbose_name='Ngày hết hạn bảo hành')),
                ('note', models.CharField(blank=True, max_length=255, verbose_name='Ghi chú')),
                ('certificate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='orders.warrantycertificate', verbose_name='Phiếu bảo hành')),
                ('order_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='warranty_items', to='orders.orderitem', verbose_name='Dòng đơn hàng')),
                ('product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='warranty_certificate_items', to='products.product', verbose_name='Sản phẩm')),
            ],
            options={
                'verbose_name': 'Chi tiết phiếu bảo hành',
                'verbose_name_plural': 'Chi tiết phiếu bảo hành',
                'db_table': 'warranty_certificate_items',
                'ordering': ['id'],
            },
        ),
        migrations.AlterField(
            model_name='orderedithistory',
            name='action',
            field=models.CharField(choices=[('create', 'Tạo đơn'), ('update', 'Cập nhật đơn'), ('note', 'Sửa ghi chú'), ('cancel', 'Hủy đơn'), ('approve', 'Duyệt đơn'), ('reject', 'Từ chối duyệt'), ('status', 'Đổi trạng thái'), ('payment', 'Thu tiền'), ('stock_export', 'Xuất kho'), ('warranty', 'Phiếu bảo hành'), ('return', 'Hoàn hàng'), ('bulk_collect', 'Thanh toán nhanh'), ('bulk_cancel', 'Hủy nhanh')], max_length=30, verbose_name='Hành động'),
        ),
    ]
