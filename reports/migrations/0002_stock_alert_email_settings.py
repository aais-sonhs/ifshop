import datetime

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('products', '0019_recalculate_weighted_purchase_cost'),
        ('reports', '0001_initial'),
        ('system_management', '0023_add_packing_print_template_choice'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockalert',
            name='brand',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='stock_alert_config',
                to='system_management.brand',
                verbose_name='Thương hiệu',
            ),
        ),
        migrations.AddField(
            model_name='stockalert',
            name='categories',
            field=models.ManyToManyField(
                blank=True,
                related_name='stock_alert_configs',
                to='products.productcategory',
                verbose_name='Danh mục cần cảnh báo',
            ),
        ),
        migrations.AddField(
            model_name='stockalert',
            name='include_child_categories',
            field=models.BooleanField(default=True, verbose_name='Bao gồm danh mục con'),
        ),
        migrations.AddField(
            model_name='stockalert',
            name='last_error',
            field=models.TextField(blank=True, default='', verbose_name='Lỗi gửi gần nhất'),
        ),
        migrations.AddField(
            model_name='stockalert',
            name='last_run_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Lần chạy gần nhất'),
        ),
        migrations.AddField(
            model_name='stockalert',
            name='last_status',
            field=models.CharField(blank=True, default='', max_length=30, verbose_name='Trạng thái gần nhất'),
        ),
        migrations.AddField(
            model_name='stockalert',
            name='last_test_sent',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Lần gửi thử cuối'),
        ),
        migrations.AddField(
            model_name='stockalert',
            name='recipient_users',
            field=models.ManyToManyField(
                blank=True,
                related_name='stock_alert_configs',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Người nhận trong hệ thống',
            ),
        ),
        migrations.AddField(
            model_name='stockalert',
            name='send_time',
            field=models.TimeField(default=datetime.time(21, 0), verbose_name='Giờ gửi hằng ngày'),
        ),
        migrations.AlterField(
            model_name='stockalert',
            name='email_recipients',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Nhiều email phân cách bởi dấu phẩy hoặc xuống dòng',
                verbose_name='Danh sách email nhận cảnh báo bổ sung',
            ),
        ),
        migrations.AlterField(
            model_name='stockalert',
            name='alert_on_max',
            field=models.BooleanField(default=False, verbose_name='Cảnh báo khi trên tồn kho tối đa'),
        ),
        migrations.AlterField(
            model_name='stockalert',
            name='is_active',
            field=models.BooleanField(default=False, verbose_name='Đang hoạt động'),
        ),
    ]
