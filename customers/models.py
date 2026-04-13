from django.db import models
from django.contrib.auth.models import User
from core.soft_delete import SoftDeleteModel


class CustomerGroup(SoftDeleteModel):
    """Nhóm khách hàng"""
    name = models.CharField(max_length=255, verbose_name='Tên nhóm')
    description = models.TextField(blank=True, null=True, verbose_name='Mô tả')
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                            verbose_name='Chiết khấu (%)')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'customer_groups'
        verbose_name = 'Nhóm khách hàng'
        verbose_name_plural = 'Nhóm khách hàng'
        ordering = ['name']

    def __str__(self):
        return self.name


class Customer(SoftDeleteModel):
    """Khách hàng"""
    CUSTOMER_TYPE_CHOICES = (
        (1, 'Cá nhân'),
        (2, 'Công ty'),
        (3, 'Hộ kinh doanh'),
    )
    store = models.ForeignKey('system_management.Store', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='customers', verbose_name='Cửa hàng')
    customer_type = models.IntegerField(choices=CUSTOMER_TYPE_CHOICES, default=1, verbose_name='Loại khách hàng')
    code = models.CharField(max_length=50, unique=True, verbose_name='Mã khách hàng')
    name = models.CharField(max_length=255, verbose_name='Tên khách hàng')
    avatar = models.ImageField(upload_to='customers/avatars/', blank=True, null=True, verbose_name='Ảnh đại diện')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='Số điện thoại')
    email = models.EmailField(blank=True, null=True, verbose_name='Email')
    address = models.TextField(blank=True, null=True, verbose_name='Địa chỉ')
    # Cá nhân
    id_number = models.CharField(max_length=20, blank=True, null=True, verbose_name='CCCD/CMND')
    # Công ty
    company = models.CharField(max_length=255, blank=True, null=True, verbose_name='Tên công ty')
    tax_code = models.CharField(max_length=20, blank=True, null=True, verbose_name='Mã số thuế')
    company_address = models.TextField(blank=True, null=True, verbose_name='Địa chỉ công ty')
    # Hộ kinh doanh
    owner_tax_code = models.CharField(max_length=20, blank=True, null=True, verbose_name='MST cá nhân chủ hộ')
    group = models.ForeignKey(CustomerGroup, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='customers', verbose_name='Nhóm khách hàng')
    total_purchased = models.DecimalField(max_digits=18, decimal_places=0, default=0,
                                           verbose_name='Tổng mua hàng')
    total_debt = models.DecimalField(max_digits=18, decimal_places=0, default=0,
                                      verbose_name='Công nợ')
    # Tích điểm & thành viên
    MEMBERSHIP_CHOICES = (
        (0, 'Thường'),
        (1, 'Bạc'),
        (2, 'Vàng'),
        (3, 'Bạch kim'),
        (4, 'Kim cương'),
    )
    points = models.IntegerField(default=0, verbose_name='Điểm tích lũy')
    membership_level = models.IntegerField(choices=MEMBERSHIP_CHOICES, default=0, verbose_name='Hạng thành viên')
    date_of_birth = models.DateField(blank=True, null=True, verbose_name='Ngày sinh')
    GENDER_CHOICES = ((0, 'Khác'), (1, 'Nam'), (2, 'Nữ'))
    gender = models.IntegerField(choices=GENDER_CHOICES, default=0, verbose_name='Giới tính')

    sapo_id = models.CharField(max_length=100, blank=True, null=True, verbose_name='Mã SAPO')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='customers_created')

    class Meta:
        db_table = 'customers'
        verbose_name = 'Khách hàng'
        verbose_name_plural = 'Khách hàng'
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}"


class PointTransaction(models.Model):
    """Lịch sử tích/đổi điểm"""
    TYPE_CHOICES = (
        (1, 'Cộng điểm'),
        (2, 'Đổi điểm'),
        (3, 'Điều chỉnh'),
    )
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='point_transactions',
                                  verbose_name='Khách hàng')
    order = models.ForeignKey('orders.Order', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='point_transactions', verbose_name='Đơn hàng')
    transaction_type = models.IntegerField(choices=TYPE_CHOICES, default=1, verbose_name='Loại')
    points = models.IntegerField(default=0, verbose_name='Số điểm')
    balance_after = models.IntegerField(default=0, verbose_name='Điểm sau GD')
    description = models.CharField(max_length=500, blank=True, null=True, verbose_name='Mô tả')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='point_txns_created')

    class Meta:
        db_table = 'point_transactions'
        verbose_name = 'Giao dịch điểm'
        verbose_name_plural = 'Giao dịch điểm'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.customer.name}: {'+' if self.transaction_type == 1 else '-'}{self.points} điểm"


class CafeTable(models.Model):
    """Quản lý bàn quán cafe"""
    STATUS_CHOICES = (
        (0, 'Trống'),
        (1, 'Đang phục vụ'),
        (2, 'Đã đặt trước'),
        (3, 'Bảo trì'),
    )
    AREA_CHOICES = (
        ('indoor', 'Trong nhà'),
        ('outdoor', 'Ngoài trời'),
        ('vip', 'Phòng VIP'),
        ('bar', 'Quầy bar'),
    )
    store = models.ForeignKey('system_management.Store', on_delete=models.CASCADE,
                               related_name='cafe_tables', verbose_name='Cửa hàng')
    number = models.CharField(max_length=20, verbose_name='Số bàn')
    name = models.CharField(max_length=100, blank=True, null=True, verbose_name='Tên bàn')
    area = models.CharField(max_length=20, choices=AREA_CHOICES, default='indoor', verbose_name='Khu vực')
    capacity = models.IntegerField(default=4, verbose_name='Số ghế')
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name='Trạng thái')
    current_order = models.ForeignKey('orders.Order', on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='tables', verbose_name='Đơn hiện tại')
    note = models.CharField(max_length=255, blank=True, null=True, verbose_name='Ghi chú')
    is_active = models.BooleanField(default=True, verbose_name='Hoạt động')
    sort_order = models.IntegerField(default=0, verbose_name='Thứ tự')

    class Meta:
        db_table = 'cafe_tables'
        verbose_name = 'Bàn cafe'
        verbose_name_plural = 'Bàn cafe'
        ordering = ['sort_order', 'number']
        unique_together = ['store', 'number']

    def __str__(self):
        return f"Bàn {self.number} ({self.get_area_display()})"
