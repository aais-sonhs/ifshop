from datetime import time

from django.conf import settings
from django.db import models

# Reports app không cần models riêng vì báo cáo sẽ query từ các app khác
# Tuy nhiên, có thể tạo bảng cấu hình cảnh báo


class StockAlert(models.Model):
    """Cấu hình cảnh báo hạn mức tồn kho"""
    brand = models.OneToOneField(
        'system_management.Brand',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='stock_alert_config',
        verbose_name='Thương hiệu',
    )
    recipient_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='stock_alert_configs',
        verbose_name='Người nhận trong hệ thống',
    )
    email_recipients = models.TextField(
        blank=True,
        default='',
        verbose_name='Danh sách email nhận cảnh báo bổ sung',
        help_text='Nhiều email phân cách bởi dấu phẩy hoặc xuống dòng',
    )
    categories = models.ManyToManyField(
        'products.ProductCategory',
        blank=True,
        related_name='stock_alert_configs',
        verbose_name='Danh mục cần cảnh báo',
    )
    include_child_categories = models.BooleanField(
        default=True,
        verbose_name='Bao gồm danh mục con',
    )
    send_time = models.TimeField(default=time(21, 0), verbose_name='Giờ gửi hằng ngày')
    alert_on_min = models.BooleanField(default=True, verbose_name='Cảnh báo khi dưới tồn kho tối thiểu')
    alert_on_max = models.BooleanField(default=False, verbose_name='Cảnh báo khi trên tồn kho tối đa')
    is_active = models.BooleanField(default=False, verbose_name='Đang hoạt động')
    last_run_at = models.DateTimeField(blank=True, null=True, verbose_name='Lần chạy gần nhất')
    last_sent = models.DateTimeField(blank=True, null=True, verbose_name='Lần gửi cuối')
    last_test_sent = models.DateTimeField(blank=True, null=True, verbose_name='Lần gửi thử cuối')
    last_status = models.CharField(max_length=30, blank=True, default='', verbose_name='Trạng thái gần nhất')
    last_error = models.TextField(blank=True, default='', verbose_name='Lỗi gửi gần nhất')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stock_alerts'
        verbose_name = 'Cấu hình cảnh báo tồn kho'
        verbose_name_plural = 'Cấu hình cảnh báo tồn kho'

    def __str__(self):
        brand_name = self.brand.name if self.brand_id else 'Chưa gán thương hiệu'
        return f"{brand_name} - {'Đang bật' if self.is_active else 'Đang tắt'}"


class StockAlertEmailRecipient(models.Model):
    """Phạm vi danh mục riêng của từng địa chỉ nhận cảnh báo tồn kho."""
    stock_alert = models.ForeignKey(
        StockAlert,
        on_delete=models.CASCADE,
        related_name='email_recipient_scopes',
        verbose_name='Cấu hình cảnh báo',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='stock_alert_email_scopes',
        verbose_name='Tài khoản hệ thống',
    )
    email = models.EmailField(verbose_name='Email nhận cảnh báo')
    categories = models.ManyToManyField(
        'products.ProductCategory',
        blank=True,
        related_name='stock_alert_email_recipient_scopes',
        verbose_name='Danh mục được nhận',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stock_alert_email_recipients'
        verbose_name = 'Người nhận email cảnh báo tồn kho'
        verbose_name_plural = 'Người nhận email cảnh báo tồn kho'
        constraints = [
            models.UniqueConstraint(
                fields=['stock_alert', 'user'],
                condition=models.Q(user__isnull=False),
                name='uniq_stock_alert_recipient_user',
            ),
            models.UniqueConstraint(
                fields=['stock_alert', 'email'],
                condition=models.Q(user__isnull=True),
                name='uniq_stock_alert_recipient_extra_email',
            ),
        ]

    def __str__(self):
        return self.email
