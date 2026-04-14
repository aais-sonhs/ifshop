from django.db import models

# Reports app không cần models riêng vì báo cáo sẽ query từ các app khác
# Tuy nhiên, có thể tạo bảng cấu hình cảnh báo


class StockAlert(models.Model):
    """Cấu hình cảnh báo hạn mức tồn kho"""
    email_recipients = models.TextField(verbose_name='Danh sách email nhận cảnh báo',
                                        help_text='Nhiều email phân cách bởi dấu phẩy')
    alert_on_min = models.BooleanField(default=True, verbose_name='Cảnh báo khi dưới tồn kho tối thiểu')
    alert_on_max = models.BooleanField(default=True, verbose_name='Cảnh báo khi trên tồn kho tối đa')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    last_sent = models.DateTimeField(blank=True, null=True, verbose_name='Lần gửi cuối')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stock_alerts'
        verbose_name = 'Cấu hình cảnh báo tồn kho'
        verbose_name_plural = 'Cấu hình cảnh báo tồn kho'

    def __str__(self):
        return f"Alert Config - {'Active' if self.is_active else 'Inactive'}"
