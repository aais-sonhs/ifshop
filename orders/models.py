from django.db import models
from django.contrib.auth.models import User
from customers.models import Customer
from products.models import Product, Warehouse
from core.soft_delete import SoftDeleteModel


DISCOUNT_MODE_CHOICES = (
    ('amount', 'Số tiền'),
    ('percent', 'Phần trăm'),
)


class Quotation(SoftDeleteModel):
    """Báo giá"""
    STATUS_CHOICES = [
        (0, 'Nháp'),
        (1, 'Đã gửi'),
        (2, 'Đã duyệt'),
        (3, 'Đã tạo đơn hàng'),
        (4, 'Hủy'),
    ]
    code = models.CharField(max_length=50, unique=True, verbose_name='Mã báo giá')
    store = models.ForeignKey('system_management.Store', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='quotations', verbose_name='Cửa hàng')
    issuing_brand = models.ForeignKey(
        'system_management.Brand', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='quotations_issued', verbose_name='Nhãn hiệu in'
    )
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, related_name='quotations',
                                 verbose_name='Khách hàng')
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name='Trạng thái')
    total_amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Tổng tiền')
    discount_amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Chiết khấu')
    discount_mode = models.CharField(
        max_length=10, choices=DISCOUNT_MODE_CHOICES, default='amount', verbose_name='Cách chiết khấu'
    )
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, verbose_name='Chiết khấu tổng đơn (%)'
    )
    shipping_fee = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Phí vận chuyển')
    other_fee = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Chi phí khác')
    final_amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Thành tiền')
    tags = models.CharField(max_length=255, blank=True, null=True, verbose_name='Tags')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    valid_until = models.DateField(blank=True, null=True, verbose_name='Hiệu lực đến')
    quotation_date = models.DateField(verbose_name='Ngày báo giá')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='quotations_created')
    salesperson = models.CharField(max_length=100, blank=True, null=True, verbose_name='Người báo giá')

    class Meta:
        db_table = 'quotations'
        verbose_name = 'Báo giá'
        verbose_name_plural = 'Báo giá'
        ordering = ['-quotation_date']

    def __str__(self):
        return self.code


class QuotationItem(models.Model):
    """Chi tiết báo giá"""
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='items',
                                  verbose_name='Báo giá')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name='quotation_items',
                                verbose_name='Sản phẩm')
    variant = models.ForeignKey('products.ProductVariant', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='quotation_items', verbose_name='Biến thể')
    item_name = models.CharField(max_length=255, blank=True, null=True, verbose_name='Tên dòng')
    unit = models.CharField(max_length=50, blank=True, null=True, verbose_name='Đơn vị tính')
    is_service_line = models.BooleanField(default=False, verbose_name='Dòng dịch vụ/thẻ trống')
    quantity = models.DecimalField(max_digits=15, decimal_places=2, default=1, verbose_name='Số lượng')
    unit_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Đơn giá')
    discount_mode = models.CharField(
        max_length=10, choices=DISCOUNT_MODE_CHOICES, default='percent', verbose_name='Cách chiết khấu dòng'
    )
    discount_amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Chiết khấu dòng')
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Chiết khấu (%)')
    total_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Thành tiền')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')

    class Meta:
        db_table = 'quotation_items'
        verbose_name = 'Chi tiết báo giá'
        verbose_name_plural = 'Chi tiết báo giá'

    @property
    def display_code(self):
        return self.product.code if self.product else 'DV'

    @property
    def display_name(self):
        return self.product.name if self.product else (self.item_name or 'Dịch vụ')

    @property
    def display_unit(self):
        return self.product.unit if self.product else (self.unit or '')

    @property
    def display_note(self):
        if self.note is not None:
            return self.note
        return self.product.note if self.product else ''


class Order(SoftDeleteModel):
    """Đơn hàng"""
    STATUS_CHOICES = [
        (0, 'Báo giá'),
        (1, 'Đơn hàng'),
        (2, 'Đang xử lý'),
        (3, 'Đang đóng gói'),
        (4, 'Đã xuất kho'),
        (5, 'Hoàn thành'),
        (6, 'Hủy'),
    ]
    PAYMENT_STATUS_CHOICES = [
        (0, 'Chưa thanh toán'),
        (1, 'Thanh toán một phần'),
        (2, 'Đã thanh toán'),
    ]
    code = models.CharField(max_length=50, unique=True, verbose_name='Mã đơn hàng')
    store = models.ForeignKey('system_management.Store', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='orders', verbose_name='Cửa hàng')
    issuing_brand = models.ForeignKey(
        'system_management.Brand', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='orders_issued', verbose_name='Nhãn hiệu in'
    )
    quotation = models.ForeignKey(Quotation, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='orders', verbose_name='Báo giá')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, related_name='orders',
                                 verbose_name='Khách hàng')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, related_name='orders',
                                  verbose_name='Kho xuất')
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name='Trạng thái')
    payment_status = models.IntegerField(choices=PAYMENT_STATUS_CHOICES, default=0,
                                         verbose_name='Trạng thái thanh toán')
    total_amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Tổng tiền hàng')
    discount_amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Chiết khấu')
    discount_mode = models.CharField(
        max_length=10, choices=DISCOUNT_MODE_CHOICES, default='amount', verbose_name='Cách chiết khấu'
    )
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, verbose_name='Chiết khấu tổng đơn (%)'
    )
    shipping_fee = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Phí vận chuyển')
    other_fee = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Chi phí khác')
    tax_amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Thuế')
    final_amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Tổng thanh toán')
    paid_amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Đã thanh toán')
    shipping_address = models.TextField(blank=True, null=True, verbose_name='Địa chỉ giao')
    tags = models.CharField(max_length=255, blank=True, null=True, verbose_name='Tags')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    order_date = models.DateField(verbose_name='Ngày đặt hàng')
    delivery_date = models.DateField(blank=True, null=True, verbose_name='Ngày giao hàng')

    # Cảnh báo bán dưới giá niêm yết
    below_listed_price_warning = models.BooleanField(default=False, verbose_name='Cảnh báo dưới giá niêm yết')
    warning_email_sent = models.BooleanField(default=False, verbose_name='Đã gửi mail cảnh báo')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='orders_created')

    # Thông tin nhân sự
    creator_name = models.CharField(max_length=100, blank=True, null=True, verbose_name='Người tạo hóa đơn')
    salesperson = models.CharField(max_length=100, blank=True, null=True, verbose_name='Nhân viên bán hàng')
    server_staff = models.CharField(max_length=500, blank=True, null=True, verbose_name='Nhân viên phục vụ')
    approver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='orders_approved', verbose_name='Người duyệt')
    APPROVAL_STATUS_CHOICES = [
        (0, 'Không cần duyệt'),
        (1, 'Chờ duyệt'),
        (2, 'Đã duyệt'),
        (3, 'Từ chối'),
    ]
    approval_status = models.IntegerField(choices=APPROVAL_STATUS_CHOICES, default=0, verbose_name='Trạng thái duyệt')
    approved_at = models.DateTimeField(blank=True, null=True, verbose_name='Thời gian duyệt')
    bonus_amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Tiền bonus')

    class Meta:
        db_table = 'orders'
        verbose_name = 'Đơn hàng'
        verbose_name_plural = 'Đơn hàng'
        ordering = ['-order_date']

    def __str__(self):
        return self.code


class OrderItem(models.Model):
    """Chi tiết đơn hàng"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name='Đơn hàng')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name='order_items',
                                verbose_name='Sản phẩm')
    variant = models.ForeignKey('products.ProductVariant', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='order_items', verbose_name='Biến thể')
    item_name = models.CharField(max_length=255, blank=True, null=True, verbose_name='Tên dòng')
    unit = models.CharField(max_length=50, blank=True, null=True, verbose_name='Đơn vị tính')
    is_service_line = models.BooleanField(default=False, verbose_name='Dòng dịch vụ/thẻ trống')
    quantity = models.DecimalField(max_digits=15, decimal_places=2, default=1, verbose_name='Số lượng')
    unit_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Đơn giá')
    cost_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Giá vốn')
    discount_mode = models.CharField(
        max_length=10, choices=DISCOUNT_MODE_CHOICES, default='percent', verbose_name='Cách chiết khấu dòng'
    )
    discount_amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Chiết khấu dòng')
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Chiết khấu (%)')
    total_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Thành tiền')
    is_below_listed = models.BooleanField(default=False, verbose_name='Dưới giá niêm yết')
    note = models.TextField(blank=True, null=True, default=None, verbose_name='Ghi chú theo đơn')

    class Meta:
        db_table = 'order_items'
        verbose_name = 'Chi tiết đơn hàng'
        verbose_name_plural = 'Chi tiết đơn hàng'

    @property
    def display_code(self):
        return self.product.code if self.product else 'DV'

    @property
    def display_name(self):
        return self.product.name if self.product else (self.item_name or 'Dịch vụ')

    @property
    def display_unit(self):
        return self.product.unit if self.product else (self.unit or '')

    @property
    def display_note(self):
        if self.note is not None:
            return self.note
        return self.product.note if self.product else ''


class WarrantyCertificate(SoftDeleteModel):
    """Phiếu bảo hành chính thức được lưu theo đơn đã xuất kho."""

    code = models.CharField(max_length=80, unique=True, verbose_name='Mã phiếu bảo hành')
    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name='warranty_certificate',
        verbose_name='Đơn hàng',
    )
    issue_date = models.DateField(verbose_name='Ngày lập phiếu')
    customer_name = models.CharField(max_length=255, blank=True, verbose_name='Tên khách hàng')
    customer_phone = models.CharField(max_length=30, blank=True, verbose_name='Số điện thoại')
    customer_address = models.TextField(blank=True, verbose_name='Địa chỉ')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='warranty_certificates_created',
        verbose_name='Người tạo',
    )

    class Meta:
        db_table = 'warranty_certificates'
        verbose_name = 'Phiếu bảo hành'
        verbose_name_plural = 'Phiếu bảo hành'
        ordering = ['-issue_date', '-id']

    def __str__(self):
        return self.code


class WarrantyCertificateItem(models.Model):
    """Bản chụp thông tin bảo hành của sản phẩm tại thời điểm lập phiếu."""

    certificate = models.ForeignKey(
        WarrantyCertificate,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Phiếu bảo hành',
    )
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='warranty_items',
        verbose_name='Dòng đơn hàng',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='warranty_certificate_items',
        verbose_name='Sản phẩm',
    )
    product_code = models.CharField(max_length=80, blank=True, verbose_name='Mã sản phẩm')
    product_name = models.CharField(max_length=255, verbose_name='Tên sản phẩm')
    unit = models.CharField(max_length=50, blank=True, verbose_name='Đơn vị tính')
    quantity = models.DecimalField(max_digits=15, decimal_places=2, default=1, verbose_name='Số lượng')
    serial = models.CharField(max_length=255, blank=True, verbose_name='Serial / lô')
    warranty_period_months = models.PositiveIntegerField(default=0, verbose_name='Kỳ hạn bảo hành (tháng)')
    warranty_term = models.CharField(max_length=120, blank=True, verbose_name='Thời hạn bảo hành')
    warranty_policy = models.TextField(blank=True, verbose_name='Chính sách bảo hành')
    warranty_start_date = models.DateField(verbose_name='Ngày bắt đầu bảo hành')
    warranty_end_date = models.DateField(null=True, blank=True, verbose_name='Ngày hết hạn bảo hành')
    note = models.CharField(max_length=255, blank=True, verbose_name='Ghi chú')

    class Meta:
        db_table = 'warranty_certificate_items'
        verbose_name = 'Chi tiết phiếu bảo hành'
        verbose_name_plural = 'Chi tiết phiếu bảo hành'
        ordering = ['id']


class OrderEditHistory(models.Model):
    """Lịch sử thao tác trên đơn hàng"""
    ACTION_CHOICES = [
        ('create', 'Tạo đơn'),
        ('update', 'Cập nhật đơn'),
        ('note', 'Sửa ghi chú'),
        ('cancel', 'Hủy đơn'),
        ('approve', 'Duyệt đơn'),
        ('reject', 'Từ chối duyệt'),
        ('status', 'Đổi trạng thái'),
        ('payment', 'Thu tiền'),
        ('stock_export', 'Xuất kho'),
        ('warranty', 'Phiếu bảo hành'),
        ('return', 'Hoàn hàng'),
        ('bulk_collect', 'Thanh toán nhanh'),
        ('bulk_cancel', 'Hủy nhanh'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='history_entries', verbose_name='Đơn hàng')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES, verbose_name='Hành động')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='order_edit_histories', verbose_name='Người thực hiện')
    status_before = models.IntegerField(blank=True, null=True, verbose_name='Trạng thái trước')
    status_after = models.IntegerField(blank=True, null=True, verbose_name='Trạng thái sau')
    summary = models.TextField(blank=True, null=True, verbose_name='Diễn giải')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời gian')

    class Meta:
        db_table = 'order_edit_histories'
        verbose_name = 'Lịch sử đơn hàng'
        verbose_name_plural = 'Lịch sử đơn hàng'
        ordering = ['-created_at', '-id']


class OrderReturn(SoftDeleteModel):
    """Khách trả hàng"""
    STATUS_CHOICES = [
        (0, 'Nháp'),
        (1, 'Xác nhận'),
        (2, 'Hoàn thành'),
        (3, 'Hủy'),
    ]
    code = models.CharField(max_length=50, unique=True, verbose_name='Mã phiếu trả')
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, related_name='returns',
                              verbose_name='Đơn hàng gốc')
    exchange_order = models.OneToOneField(Order, on_delete=models.SET_NULL, null=True, blank=True,
                                          related_name='source_return_exchange',
                                          verbose_name='Đơn hàng đổi phát sinh')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, related_name='returns',
                                 verbose_name='Khách hàng')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, related_name='returns',
                                  verbose_name='Kho nhận')
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name='Trạng thái')
    return_amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Tổng hàng trả')
    exchange_amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Tổng hàng đổi')
    compensation_amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Hoàn tiền/đền bù riêng')
    total_refund = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Tổng hoàn trả')
    amount_due = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Còn phải thu')
    reason = models.TextField(blank=True, null=True, verbose_name='Lý do trả hàng')
    exchange_note = models.TextField(blank=True, null=True, verbose_name='Ghi chú đổi hàng')
    return_date = models.DateField(verbose_name='Ngày trả hàng')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='returns_created')

    class Meta:
        db_table = 'order_returns'
        verbose_name = 'Phiếu trả hàng'
        verbose_name_plural = 'Phiếu trả hàng'
        ordering = ['-return_date']

    def __str__(self):
        return self.code


class OrderReturnItem(models.Model):
    """Chi tiết phiếu trả hàng"""
    order_return = models.ForeignKey(OrderReturn, on_delete=models.CASCADE, related_name='items',
                                     verbose_name='Phiếu trả')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='return_items',
                                verbose_name='Sản phẩm')
    quantity = models.IntegerField(default=0, verbose_name='Số lượng trả')
    unit_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Đơn giá')
    total_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Thành tiền')
    reason = models.TextField(blank=True, null=True, verbose_name='Lý do')

    class Meta:
        db_table = 'order_return_items'
        verbose_name = 'Chi tiết trả hàng'
        verbose_name_plural = 'Chi tiết trả hàng'


class OrderReturnExchangeItem(models.Model):
    """Chi tiết hàng đổi mới trong phiếu trả/đổi hàng"""
    order_return = models.ForeignKey(OrderReturn, on_delete=models.CASCADE, related_name='exchange_items',
                                     verbose_name='Phiếu trả')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='return_exchange_items',
                                verbose_name='Sản phẩm đổi')
    variant = models.ForeignKey('products.ProductVariant', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='return_exchange_items', verbose_name='Biến thể')
    quantity = models.DecimalField(max_digits=15, decimal_places=2, default=1, verbose_name='Số lượng đổi')
    unit_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Đơn giá')
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Chiết khấu (%)')
    total_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Thành tiền')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')

    class Meta:
        db_table = 'order_return_exchange_items'
        verbose_name = 'Chi tiết đổi hàng'
        verbose_name_plural = 'Chi tiết đổi hàng'


class Packaging(SoftDeleteModel):
    """Quản lý đóng gói"""
    STATUS_CHOICES = [
        (0, 'Chờ đóng gói'),
        (1, 'Đang đóng gói'),
        (2, 'Hoàn thành'),
        (3, 'Hủy'),
    ]
    code = models.CharField(max_length=50, unique=True, verbose_name='Mã đóng gói')
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='packagings',
                              verbose_name='Đơn hàng')
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name='Trạng thái')
    packed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='packagings', verbose_name='Người đóng gói')
    weight = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Trọng lượng (kg)')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    packed_at = models.DateTimeField(blank=True, null=True, verbose_name='Thời gian đóng gói')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'packagings'
        verbose_name = 'Đóng gói'
        verbose_name_plural = 'Đóng gói'
        ordering = ['-created_at']

    def __str__(self):
        return self.code
