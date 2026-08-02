import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0015_recalculate_draft_goods_receipt_payments'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FinancialPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_deleted', models.BooleanField(default=False, verbose_name='Đã xóa')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='Ngày xóa')),
                ('code', models.CharField(max_length=50, unique=True, verbose_name='Mã kế hoạch')),
                ('name', models.CharField(max_length=255, verbose_name='Tên kế hoạch')),
                ('period_type', models.CharField(choices=[('month', 'Tháng'), ('year', 'Năm')], default='month', max_length=10, verbose_name='Loại kỳ')),
                ('start_date', models.DateField(verbose_name='Từ ngày')),
                ('end_date', models.DateField(verbose_name='Đến ngày')),
                ('status', models.IntegerField(choices=[(0, 'Nháp'), (1, 'Đang áp dụng'), (2, 'Đã khóa')], default=1, verbose_name='Trạng thái')),
                ('note', models.TextField(blank=True, null=True, verbose_name='Ghi chú')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='financial_plans_created', to=settings.AUTH_USER_MODEL, verbose_name='Người tạo')),
                ('store', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='financial_plans', to='system_management.store', verbose_name='Cửa hàng')),
            ],
            options={
                'verbose_name': 'Kế hoạch tài chính',
                'verbose_name_plural': 'Kế hoạch tài chính',
                'db_table': 'financial_plans',
                'ordering': ['-start_date', '-id'],
            },
        ),
        migrations.CreateModel(
            name='FinancialPlanItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_deleted', models.BooleanField(default=False, verbose_name='Đã xóa')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='Ngày xóa')),
                ('direction', models.IntegerField(choices=[(1, 'Thu'), (2, 'Chi')], verbose_name='Loại')),
                ('planned_amount', models.DecimalField(decimal_places=0, default=0, max_digits=18, verbose_name='Số tiền kế hoạch')),
                ('expected_date', models.DateField(blank=True, null=True, verbose_name='Ngày dự kiến')),
                ('include_in_forecast', models.BooleanField(default=True, verbose_name='Đưa vào dự báo')),
                ('note', models.TextField(blank=True, null=True, verbose_name='Ghi chú')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('cash_book', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='financial_plan_items', to='finance.cashbook', verbose_name='Quỹ dự kiến')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='financial_plan_items', to='finance.financecategory', verbose_name='Danh mục')),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='finance.financialplan', verbose_name='Kế hoạch')),
            ],
            options={
                'verbose_name': 'Khoản kế hoạch tài chính',
                'verbose_name_plural': 'Khoản kế hoạch tài chính',
                'db_table': 'financial_plan_items',
                'ordering': ['direction', 'category__name', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='financialplanitem',
            constraint=models.UniqueConstraint(fields=('plan', 'direction', 'category'), name='uniq_financial_plan_direction_category'),
        ),
        migrations.CreateModel(
            name='SupplierPaymentSchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_deleted', models.BooleanField(default=False, verbose_name='Đã xóa')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='Ngày xóa')),
                ('code', models.CharField(max_length=50, unique=True, verbose_name='Mã lịch chi')),
                ('due_date', models.DateField(verbose_name='Ngày dự kiến thanh toán')),
                ('gross_amount', models.DecimalField(decimal_places=0, default=0, max_digits=18, verbose_name='Số tiền trước khuyến mãi')),
                ('promotion_mode', models.CharField(choices=[('amount', 'Số tiền'), ('percent', 'Phần trăm')], default='amount', max_length=10, verbose_name='Cách tính khuyến mãi')),
                ('promotion_amount', models.DecimalField(decimal_places=0, default=0, max_digits=18, verbose_name='Tiền khuyến mãi')),
                ('promotion_percent', models.DecimalField(decimal_places=2, default=0, max_digits=5, verbose_name='Khuyến mãi (%)')),
                ('amount', models.DecimalField(decimal_places=0, default=0, max_digits=18, verbose_name='Số tiền dự chi')),
                ('priority', models.IntegerField(choices=[(1, 'Khẩn cấp'), (2, 'Cao'), (3, 'Bình thường'), (4, 'Thấp')], default=3, verbose_name='Mức ưu tiên')),
                ('status', models.IntegerField(choices=[(0, 'Chờ thanh toán'), (1, 'Đã thanh toán'), (2, 'Đã hủy')], default=0, verbose_name='Trạng thái')),
                ('note', models.TextField(blank=True, null=True, verbose_name='Ghi chú')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('cash_book', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='supplier_payment_schedules', to='finance.cashbook', verbose_name='Quỹ dự kiến')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='supplier_payment_schedules_created', to=settings.AUTH_USER_MODEL, verbose_name='Người tạo')),
                ('goods_receipt', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payment_schedules', to='products.goodsreceipt', verbose_name='Phiếu nhập')),
                ('payment', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='supplier_schedule', to='finance.payment', verbose_name='Phiếu chi')),
                ('plan', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='supplier_schedules', to='finance.financialplan', verbose_name='Kế hoạch')),
                ('plan_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='supplier_schedules', to='finance.financialplanitem', verbose_name='Khoản ngân sách')),
                ('store', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='supplier_payment_schedules', to='system_management.store', verbose_name='Cửa hàng')),
                ('supplier', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payment_schedules', to='products.supplier', verbose_name='Nhà cung cấp')),
            ],
            options={
                'verbose_name': 'Lịch thanh toán nhà cung cấp',
                'verbose_name_plural': 'Lịch thanh toán nhà cung cấp',
                'db_table': 'supplier_payment_schedules',
                'ordering': ['status', 'due_date', 'priority', 'id'],
                'indexes': [
                    models.Index(fields=['status', 'due_date'], name='supplier_pay_due_idx'),
                    models.Index(fields=['store', 'due_date'], name='supplier_pay_store_idx'),
                ],
            },
        ),
    ]
