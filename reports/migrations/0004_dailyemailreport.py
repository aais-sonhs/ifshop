import datetime

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('reports', '0003_stockalertemailrecipient'),
        ('system_management', '0023_add_packing_print_template_choice'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailyEmailReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email_recipients', models.TextField(blank=True, default='', help_text='Nhiều email phân cách bởi dấu phẩy hoặc xuống dòng', verbose_name='Danh sách email nhận bổ sung')),
                ('send_time', models.TimeField(default=datetime.time(21, 0), verbose_name='Giờ gửi hằng ngày')),
                ('is_active', models.BooleanField(default=False, verbose_name='Đang hoạt động')),
                ('last_run_at', models.DateTimeField(blank=True, null=True, verbose_name='Lần chạy gần nhất')),
                ('last_sent', models.DateTimeField(blank=True, null=True, verbose_name='Lần gửi cuối')),
                ('last_test_sent', models.DateTimeField(blank=True, null=True, verbose_name='Lần gửi thử cuối')),
                ('last_status', models.CharField(blank=True, default='', max_length=30, verbose_name='Trạng thái gần nhất')),
                ('last_error', models.TextField(blank=True, default='', verbose_name='Lỗi gửi gần nhất')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('brand', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='daily_email_report_config', to='system_management.brand', verbose_name='Thương hiệu')),
                ('recipient_users', models.ManyToManyField(blank=True, related_name='daily_email_report_configs', to=settings.AUTH_USER_MODEL, verbose_name='Người nhận trong hệ thống')),
            ],
            options={
                'verbose_name': 'Báo cáo email hằng ngày',
                'verbose_name_plural': 'Báo cáo email hằng ngày',
                'db_table': 'daily_email_reports',
            },
        ),
    ]
