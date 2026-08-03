import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0016_financial_planning'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='cashbook',
            name='minimum_balance',
            field=models.DecimalField(
                decimal_places=0,
                default=0,
                max_digits=18,
                verbose_name='Số dư tối thiểu cần giữ',
            ),
        ),
        migrations.AddField(
            model_name='financialplan',
            name='alert_email_recipients',
            field=models.TextField(blank=True, default='', verbose_name='Email nhận cảnh báo'),
        ),
        migrations.AddField(
            model_name='financialplan',
            name='alert_enabled',
            field=models.BooleanField(default=False, verbose_name='Bật cảnh báo tự động'),
        ),
        migrations.AddField(
            model_name='financialplan',
            name='alert_lead_days',
            field=models.CharField(
                default='3,7,15',
                max_length=50,
                verbose_name='Số ngày cảnh báo trước',
            ),
        ),
        migrations.AddField(
            model_name='financialplan',
            name='last_alert_run_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Lần kiểm tra cảnh báo'),
        ),
        migrations.AddField(
            model_name='financialplan',
            name='last_alert_sent',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Lần gửi cảnh báo'),
        ),
        migrations.AddField(
            model_name='supplierpaymentschedule',
            name='installment_no',
            field=models.PositiveIntegerField(default=1, verbose_name='Đợt thanh toán'),
        ),
        migrations.AddField(
            model_name='supplierpaymentschedule',
            name='source',
            field=models.CharField(
                choices=[
                    ('manual', 'Xếp thủ công'),
                    ('automatic', 'Hệ thống đề xuất'),
                ],
                default='manual',
                max_length=15,
                verbose_name='Nguồn tạo lịch',
            ),
        ),
        migrations.AddField(
            model_name='supplierpaymentschedule',
            name='suggestion_reason',
            field=models.TextField(blank=True, default='', verbose_name='Lý do đề xuất'),
        ),
        migrations.CreateModel(
            name='FinancialPlanAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_deleted', models.BooleanField(default=False, verbose_name='Đã xóa')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='Ngày xóa')),
                ('month', models.DateField(verbose_name='Tháng phân bổ')),
                ('planned_amount', models.DecimalField(decimal_places=0, default=0, max_digits=18, verbose_name='Số tiền phân bổ')),
                ('expected_date', models.DateField(blank=True, null=True, verbose_name='Ngày dự kiến phát sinh')),
                ('note', models.TextField(blank=True, default='', verbose_name='Ghi chú')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='allocations', to='finance.financialplanitem', verbose_name='Khoản ngân sách')),
            ],
            options={
                'verbose_name': 'Phân bổ ngân sách theo tháng',
                'verbose_name_plural': 'Phân bổ ngân sách theo tháng',
                'db_table': 'financial_plan_allocations',
                'ordering': ['month', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='financialplanallocation',
            constraint=models.UniqueConstraint(fields=('item', 'month'), name='uniq_financial_plan_item_month'),
        ),
        migrations.CreateModel(
            name='FinancialPlanRevision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version', models.PositiveIntegerField(verbose_name='Phiên bản')),
                ('reason', models.CharField(blank=True, default='', max_length=500, verbose_name='Lý do điều chỉnh')),
                ('snapshot', models.JSONField(default=dict, verbose_name='Dữ liệu kế hoạch')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='financial_plan_revisions_created', to=settings.AUTH_USER_MODEL, verbose_name='Người điều chỉnh')),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='revisions', to='finance.financialplan', verbose_name='Kế hoạch')),
            ],
            options={
                'verbose_name': 'Lịch sử điều chỉnh kế hoạch',
                'verbose_name_plural': 'Lịch sử điều chỉnh kế hoạch',
                'db_table': 'financial_plan_revisions',
                'ordering': ['-version', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='financialplanrevision',
            constraint=models.UniqueConstraint(fields=('plan', 'version'), name='uniq_financial_plan_revision_version'),
        ),
    ]
