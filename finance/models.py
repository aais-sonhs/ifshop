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
        # Giữ thứ tự ổn định khi nhiều phiếu có cùng ngày thu. Nếu chỉ sắp theo
        # receipt_date, database có thể trả các dòng cùng ngày theo thứ tự khác
        # sau mỗi lần cập nhật và khiến dòng vừa sửa bị "nhảy" vị trí.
        ordering = ['-receipt_date', '-id']

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
    PROMOTION_MODE_CHOICES = (
        ('amount', 'Số tiền'),
        ('percent', 'Phần trăm'),
    )
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
    # `amount` là tiền thực tế ra khỏi quỹ. Khuyến mãi từ nhà cung cấp được
    # lưu riêng trên phiếu chi để không làm thay đổi giá trị phiếu nhập.
    amount = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name='Số tiền thực chi')
    promotion_mode = models.CharField(
        max_length=10,
        choices=PROMOTION_MODE_CHOICES,
        default='amount',
        verbose_name='Cách tính khuyến mãi',
    )
    promotion_amount = models.DecimalField(
        max_digits=18,
        decimal_places=0,
        default=0,
        verbose_name='Tiền khuyến mãi',
    )
    promotion_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name='Khuyến mãi (%)',
    )
    description = models.TextField(blank=True, null=True, verbose_name='Diễn giải')
    payment_date = models.DateField(verbose_name='Ngày chi')
    reference = models.CharField(max_length=100, blank=True, null=True, verbose_name='Số tham chiếu')
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name='Trạng thái')
    payment_method = models.IntegerField(choices=PAYMENT_METHOD_CHOICES, default=2, verbose_name='Hình thức thanh toán')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='payments_created')
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments_approved',
        verbose_name='Người duyệt',
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='Thời gian duyệt')

    class Meta:
        db_table = 'payments'
        verbose_name = 'Phiếu chi'
        verbose_name_plural = 'Phiếu chi'
        ordering = ['-payment_date', '-created_at', '-id']

    def __str__(self):
        return self.code

    def get_payment_method_label(self):
        return self.payment_method_option.name if self.payment_method_option else self.get_payment_method_display()


class FinancialPlan(SoftDeleteModel):
    """Kế hoạch ngân sách thu/chi theo tháng hoặc năm."""

    PERIOD_CHOICES = (
        ('month', 'Tháng'),
        ('year', 'Năm'),
    )
    STATUS_CHOICES = (
        (0, 'Nháp'),
        (1, 'Đang áp dụng'),
        (2, 'Đã khóa'),
    )

    code = models.CharField(max_length=50, unique=True, verbose_name='Mã kế hoạch')
    name = models.CharField(max_length=255, verbose_name='Tên kế hoạch')
    store = models.ForeignKey(
        'system_management.Store',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='financial_plans',
        verbose_name='Cửa hàng',
    )
    period_type = models.CharField(
        max_length=10,
        choices=PERIOD_CHOICES,
        default='month',
        verbose_name='Loại kỳ',
    )
    start_date = models.DateField(verbose_name='Từ ngày')
    end_date = models.DateField(verbose_name='Đến ngày')
    status = models.IntegerField(choices=STATUS_CHOICES, default=1, verbose_name='Trạng thái')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='financial_plans_created',
        verbose_name='Người tạo',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'financial_plans'
        verbose_name = 'Kế hoạch tài chính'
        verbose_name_plural = 'Kế hoạch tài chính'
        ordering = ['-start_date', '-id']

    def __str__(self):
        return f'{self.code} - {self.name}'


class FinancialPlanItem(SoftDeleteModel):
    """Một ngân sách thu hoặc chi trong kế hoạch tài chính."""

    DIRECTION_CHOICES = (
        (1, 'Thu'),
        (2, 'Chi'),
    )

    plan = models.ForeignKey(
        FinancialPlan,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Kế hoạch',
    )
    direction = models.IntegerField(choices=DIRECTION_CHOICES, verbose_name='Loại')
    category = models.ForeignKey(
        FinanceCategory,
        on_delete=models.PROTECT,
        related_name='financial_plan_items',
        verbose_name='Danh mục',
    )
    cash_book = models.ForeignKey(
        CashBook,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='financial_plan_items',
        verbose_name='Quỹ dự kiến',
    )
    planned_amount = models.DecimalField(
        max_digits=18,
        decimal_places=0,
        default=0,
        verbose_name='Số tiền kế hoạch',
    )
    expected_date = models.DateField(null=True, blank=True, verbose_name='Ngày dự kiến')
    include_in_forecast = models.BooleanField(default=True, verbose_name='Đưa vào dự báo')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'financial_plan_items'
        verbose_name = 'Khoản kế hoạch tài chính'
        verbose_name_plural = 'Khoản kế hoạch tài chính'
        ordering = ['direction', 'category__name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['plan', 'direction', 'category'],
                name='uniq_financial_plan_direction_category',
            ),
        ]

    def __str__(self):
        return f'{self.plan.code} - {self.get_direction_display()} - {self.category.name}'


class SupplierPaymentSchedule(SoftDeleteModel):
    """Lịch dự kiến thanh toán công nợ nhà cung cấp."""

    PRIORITY_CHOICES = (
        (1, 'Khẩn cấp'),
        (2, 'Cao'),
        (3, 'Bình thường'),
        (4, 'Thấp'),
    )
    STATUS_CHOICES = (
        (0, 'Chờ thanh toán'),
        (1, 'Đã thanh toán'),
        (2, 'Đã hủy'),
    )

    code = models.CharField(max_length=50, unique=True, verbose_name='Mã lịch chi')
    plan = models.ForeignKey(
        FinancialPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supplier_schedules',
        verbose_name='Kế hoạch',
    )
    plan_item = models.ForeignKey(
        FinancialPlanItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supplier_schedules',
        verbose_name='Khoản ngân sách',
    )
    store = models.ForeignKey(
        'system_management.Store',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supplier_payment_schedules',
        verbose_name='Cửa hàng',
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='payment_schedules',
        verbose_name='Nhà cung cấp',
    )
    goods_receipt = models.ForeignKey(
        'products.GoodsReceipt',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_schedules',
        verbose_name='Phiếu nhập',
    )
    cash_book = models.ForeignKey(
        CashBook,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supplier_payment_schedules',
        verbose_name='Quỹ dự kiến',
    )
    due_date = models.DateField(verbose_name='Ngày dự kiến thanh toán')
    gross_amount = models.DecimalField(
        max_digits=18,
        decimal_places=0,
        default=0,
        verbose_name='Số tiền trước khuyến mãi',
    )
    promotion_mode = models.CharField(
        max_length=10,
        choices=Payment.PROMOTION_MODE_CHOICES,
        default='amount',
        verbose_name='Cách tính khuyến mãi',
    )
    promotion_amount = models.DecimalField(
        max_digits=18,
        decimal_places=0,
        default=0,
        verbose_name='Tiền khuyến mãi',
    )
    promotion_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name='Khuyến mãi (%)',
    )
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=0,
        default=0,
        verbose_name='Số tiền dự chi',
    )
    priority = models.IntegerField(
        choices=PRIORITY_CHOICES,
        default=3,
        verbose_name='Mức ưu tiên',
    )
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name='Trạng thái')
    payment = models.OneToOneField(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supplier_schedule',
        verbose_name='Phiếu chi',
    )
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='supplier_payment_schedules_created',
        verbose_name='Người tạo',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'supplier_payment_schedules'
        verbose_name = 'Lịch thanh toán nhà cung cấp'
        verbose_name_plural = 'Lịch thanh toán nhà cung cấp'
        ordering = ['status', 'due_date', 'priority', 'id']
        indexes = [
            models.Index(fields=['status', 'due_date'], name='supplier_pay_due_idx'),
            models.Index(fields=['store', 'due_date'], name='supplier_pay_store_idx'),
        ]

    def __str__(self):
        return f'{self.code} - {self.supplier.name}'
