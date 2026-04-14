from django.db import models
from django.contrib.auth.models import User
from customers.models import Customer
from products.models import Supplier
from core.soft_delete import SoftDeleteModel


class FinanceCategory(SoftDeleteModel):
    """Danh mục nghiệp vụ thu chi"""
    TYPE_CHOICES = [
        (1, 'Thu'),
        (2, 'Chi'),
    ]
    name = models.CharField(max_length=255, verbose_name='Tên danh mục')
    type = models.IntegerField(choices=TYPE_CHOICES, verbose_name='Loại')
    description = models.TextField(blank=True, null=True, verbose_name='Mô tả')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'finance_categories'
        verbose_name = 'Danh mục thu chi'
        verbose_name_plural = 'Danh mục thu chi'
        ordering = ['type', 'name']

    def __str__(self):
        return f"{'Thu' if self.type == 1 else 'Chi'} - {self.name}"


class CashBook(SoftDeleteModel):
    """Danh mục quỹ (Sổ quỹ)"""
    name = models.CharField(max_length=255, verbose_name='Tên quỹ')
    description = models.TextField(blank=True, null=True, verbose_name='Mô tả')
    balance = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Số dư')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cash_books'
        verbose_name = 'Quỹ'
        verbose_name_plural = 'Quỹ'
        ordering = ['name']

    def __str__(self):
        return self.name


class PaymentMethodOption(SoftDeleteModel):
    """Danh mục phương thức nhận/chi tiền mở rộng"""
    LEGACY_CHOICES = [
        (1, 'Tiền mặt'),
        (2, 'Chuyển khoản'),
        (3, 'Khác'),
    ]

    code = models.CharField(max_length=30, unique=True, verbose_name='Mã phương thức')
    name = models.CharField(max_length=255, verbose_name='Tên phương thức')
    description = models.TextField(blank=True, null=True, verbose_name='Mô tả')
    legacy_type = models.IntegerField(choices=LEGACY_CHOICES, default=3, verbose_name='Loại chuẩn')
    default_cash_book = models.ForeignKey(
        CashBook, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payment_method_defaults', verbose_name='Tài khoản mặc định'
    )
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    sort_order = models.IntegerField(default=0, verbose_name='Thứ tự')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payment_method_options'
        verbose_name = 'Phương thức thanh toán'
        verbose_name_plural = 'Phương thức thanh toán'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class Receipt(SoftDeleteModel):
    """Phiếu thu"""
    STATUS_CHOICES = [
        (0, 'Nháp'),
        (1, 'Hoàn thành'),
        (2, 'Hủy'),
    ]
    PAYMENT_METHOD_CHOICES = [
        (1, 'Tiền mặt'),
        (2, 'Chuyển khoản'),
    ]
    code = models.CharField(max_length=50, unique=True, verbose_name='Mã phiếu thu')
    store = models.ForeignKey('system_management.Store', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='receipts', verbose_name='Cửa hàng')
    category = models.ForeignKey(FinanceCategory, on_delete=models.SET_NULL, null=True,
                                  related_name='receipts', verbose_name='Danh mục')
    cash_book = models.ForeignKey(CashBook, on_delete=models.SET_NULL, null=True,
                                   related_name='receipts', verbose_name='Quỹ')
    payment_method_option = models.ForeignKey(
        PaymentMethodOption, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='receipts', verbose_name='Phương thức thanh toán'
    )
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='receipts', verbose_name='Khách hàng')
    order = models.ForeignKey('orders.Order', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='receipts', verbose_name='Đơn hàng')
    amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Số tiền')
    description = models.TextField(blank=True, null=True, verbose_name='Diễn giải')
    receipt_date = models.DateField(verbose_name='Ngày thu')
    reference = models.CharField(max_length=100, blank=True, null=True, verbose_name='Số tham chiếu')
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name='Trạng thái')
    payment_method = models.IntegerField(choices=PAYMENT_METHOD_CHOICES, default=2, verbose_name='Hình thức thanh toán')
    cashbook_applied = models.BooleanField(default=False, verbose_name='Đã ghi sổ quỹ')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='receipts_created')

    class Meta:
        db_table = 'receipts'
        verbose_name = 'Phiếu thu'
        verbose_name_plural = 'Phiếu thu'
        ordering = ['-receipt_date']

    def __str__(self):
        return self.code

    def get_payment_method_label(self):
        return self.payment_method_option.name if self.payment_method_option else self.get_payment_method_display()


class ReceiptItem(models.Model):
    """Chi tiết phiếu thu (sản phẩm bán hàng)"""
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name='items',
                                 verbose_name='Phiếu thu')
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE,
                                 related_name='receipt_sale_items', verbose_name='Sản phẩm')
    quantity = models.IntegerField(default=1, verbose_name='Số lượng')
    unit_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Đơn giá')
    total_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Thành tiền')

    class Meta:
        db_table = 'receipt_items'
        verbose_name = 'Chi tiết phiếu thu'
        verbose_name_plural = 'Chi tiết phiếu thu'

    def __str__(self):
        return f"{self.receipt.code} - {self.product.name}"


class Payment(SoftDeleteModel):
    """Phiếu chi"""
    STATUS_CHOICES = [
        (0, 'Nháp'),
        (1, 'Hoàn thành'),
        (2, 'Hủy'),
    ]
    PAYMENT_METHOD_CHOICES = [
        (1, 'Tiền mặt'),
        (2, 'Chuyển khoản'),
    ]
    code = models.CharField(max_length=50, unique=True, verbose_name='Mã phiếu chi')
    store = models.ForeignKey('system_management.Store', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='payments', verbose_name='Cửa hàng')
    category = models.ForeignKey(FinanceCategory, on_delete=models.SET_NULL, null=True,
                                  related_name='payments', verbose_name='Danh mục')
    cash_book = models.ForeignKey(CashBook, on_delete=models.SET_NULL, null=True,
                                   related_name='payments', verbose_name='Quỹ')
    payment_method_option = models.ForeignKey(
        PaymentMethodOption, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payments', verbose_name='Phương thức thanh toán'
    )
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='payments', verbose_name='Nhà cung cấp')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='payments', verbose_name='Khách hàng')
    goods_receipt = models.ForeignKey('products.GoodsReceipt', on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='payments', verbose_name='Phiếu nhập hàng')
    amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Số tiền')
    description = models.TextField(blank=True, null=True, verbose_name='Diễn giải')
    payment_date = models.DateField(verbose_name='Ngày chi')
    reference = models.CharField(max_length=100, blank=True, null=True, verbose_name='Số tham chiếu')
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name='Trạng thái')
    payment_method = models.IntegerField(choices=PAYMENT_METHOD_CHOICES, default=2, verbose_name='Hình thức thanh toán')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='payments_created')

    class Meta:
        db_table = 'payments'
        verbose_name = 'Phiếu chi'
        verbose_name_plural = 'Phiếu chi'
        ordering = ['-payment_date']

    def __str__(self):
        return self.code

    def get_payment_method_label(self):
        return self.payment_method_option.name if self.payment_method_option else self.get_payment_method_display()
