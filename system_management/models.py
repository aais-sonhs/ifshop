from django.db import models
from django.contrib.auth.models import User, Group


class UserProfile(models.Model):
    """Hồ sơ người dùng mở rộng"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    store = models.ForeignKey('Store', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='staff_profiles', verbose_name='Cửa hàng')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='Số điện thoại')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name='Ảnh đại diện')
    address = models.TextField(blank=True, null=True, verbose_name='Địa chỉ')
    department = models.CharField(max_length=100, blank=True, null=True, verbose_name='Phòng ban')
    position = models.CharField(max_length=100, blank=True, null=True, verbose_name='Chức vụ')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_profiles'
        verbose_name = 'Hồ sơ người dùng'
        verbose_name_plural = 'Hồ sơ người dùng'

    def __str__(self):
        return f"Profile: {self.user.username}"


class RoleGroup(models.Model):
    """Nhóm vai trò sử dụng"""
    name = models.CharField(max_length=100, unique=True, verbose_name='Tên nhóm vai trò')
    description = models.TextField(blank=True, null=True, verbose_name='Mô tả')
    group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name='role_group',
                                  verbose_name='Django Group')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'role_groups'
        verbose_name = 'Nhóm vai trò'
        verbose_name_plural = 'Nhóm vai trò'
        ordering = ['name']

    def __str__(self):
        return self.name


class ModulePermission(models.Model):
    """Phân quyền theo module"""
    MODULE_CHOICES = [
        ('orders', 'Quản lý đơn hàng'),
        ('products', 'Quản lý sản phẩm'),
        ('customers', 'Quản lý khách hàng'),
        ('finance', 'Thu chi'),
        ('reports', 'Báo cáo'),
        ('system', 'Quản lý hệ thống'),
    ]
    ACTION_CHOICES = [
        ('view', 'Xem'),
        ('add', 'Thêm'),
        ('edit', 'Sửa'),
        ('delete', 'Xóa'),
        ('export', 'Xuất'),
        ('approve', 'Duyệt'),
    ]
    role_group = models.ForeignKey(RoleGroup, on_delete=models.CASCADE, related_name='permissions',
                                    verbose_name='Nhóm vai trò')
    module = models.CharField(max_length=50, choices=MODULE_CHOICES, verbose_name='Module')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, verbose_name='Hành động')
    is_allowed = models.BooleanField(default=False, verbose_name='Cho phép')

    class Meta:
        db_table = 'module_permissions'
        verbose_name = 'Phân quyền module'
        verbose_name_plural = 'Phân quyền module'
        unique_together = ['role_group', 'module', 'action']

    def __str__(self):
        return f"{self.role_group.name} - {self.module} - {self.action}"


class DataPermission(models.Model):
    """Phân quyền dữ liệu"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='data_permissions',
                              verbose_name='Người dùng')
    module = models.CharField(max_length=50, verbose_name='Module')
    data_scope = models.CharField(max_length=50, verbose_name='Phạm vi dữ liệu',
                                   help_text='all, own, warehouse, etc.')
    warehouse_ids = models.TextField(blank=True, null=True, verbose_name='Danh sách ID kho (phân cách bởi dấu phẩy)')

    class Meta:
        db_table = 'data_permissions'
        verbose_name = 'Phân quyền dữ liệu'
        verbose_name_plural = 'Phân quyền dữ liệu'

    def __str__(self):
        return f"{self.user.username} - {self.module} - {self.data_scope}"


class ServicePrice(models.Model):
    """Danh mục giá dịch vụ"""
    name = models.CharField(max_length=255, verbose_name='Tên dịch vụ')
    price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Giá')
    unit = models.CharField(max_length=50, blank=True, null=True, verbose_name='Đơn vị')
    description = models.TextField(blank=True, null=True, verbose_name='Mô tả')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'service_prices'
        verbose_name = 'Giá dịch vụ'
        verbose_name_plural = 'Giá dịch vụ'
        ordering = ['name']

    def __str__(self):
        return f"{self.name}: {self.price}"


class SystemLog(models.Model):
    """Log hệ thống"""
    ACTION_CHOICES = [
        ('create', 'Tạo mới'),
        ('update', 'Cập nhật'),
        ('delete', 'Xóa'),
        ('login', 'Đăng nhập'),
        ('logout', 'Đăng xuất'),
        ('export', 'Xuất dữ liệu'),
        ('import', 'Nhập dữ liệu'),
    ]
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='system_logs',
                              verbose_name='Người dùng')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, verbose_name='Hành động')
    module = models.CharField(max_length=50, verbose_name='Module')
    description = models.TextField(blank=True, null=True, verbose_name='Mô tả')
    object_id = models.CharField(max_length=100, blank=True, null=True, verbose_name='ID đối tượng')
    old_data = models.JSONField(blank=True, null=True, verbose_name='Dữ liệu cũ')
    new_data = models.JSONField(blank=True, null=True, verbose_name='Dữ liệu mới')
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name='Địa chỉ IP')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'system_logs'
        verbose_name = 'Log hệ thống'
        verbose_name_plural = 'Log hệ thống'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.action} - {self.module} - {self.created_at}"


class PrinterSetting(models.Model):
    """Cài đặt máy in"""
    PRINTER_TYPE_CHOICES = [
        ('lan', 'Máy in LAN (Mạng)'),
        ('usb', 'Máy in USB'),
        ('bluetooth', 'Máy in Bluetooth'),
    ]
    PAPER_SIZE_CHOICES = [
        ('A4', 'A4 (210 x 297 mm)'),
        ('A5', 'A5 (148 x 210 mm)'),
        ('80mm', 'Giấy nhiệt 80mm'),
        ('58mm', 'Giấy nhiệt 58mm'),
        ('letter', 'Letter (216 x 279 mm)'),
    ]
    name = models.CharField(max_length=255, verbose_name='Tên máy in')
    printer_type = models.CharField(max_length=20, choices=PRINTER_TYPE_CHOICES, default='lan',
                                     verbose_name='Loại kết nối')
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name='Địa chỉ IP')
    port = models.IntegerField(default=9100, verbose_name='Cổng (Port)')
    paper_size = models.CharField(max_length=20, choices=PAPER_SIZE_CHOICES, default='A4',
                                   verbose_name='Khổ giấy')
    description = models.TextField(blank=True, null=True, verbose_name='Mô tả')
    is_default = models.BooleanField(default=False, verbose_name='Máy in mặc định')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'printer_settings'
        verbose_name = 'Cài đặt máy in'
        verbose_name_plural = 'Cài đặt máy in'
        ordering = ['-is_default', 'name']

    def __str__(self):
        return f"{self.name} ({self.ip_address}:{self.port})"


class BusinessConfig(models.Model):
    """Cấu hình mô hình kinh doanh — per-brand (mỗi thương hiệu có config riêng)"""
    BUSINESS_TYPE_CHOICES = [
        ('retail', 'Bán lẻ / Siêu thị'),
        ('spa', 'Spa / Massage'),
        ('fashion', 'Thời trang / Giày dép'),
        ('fnb', 'Nhà hàng / Quán café'),
        ('pharmacy', 'Nhà thuốc'),
        ('custom', 'Tùy chỉnh'),
    ]
    brand = models.OneToOneField('Brand', on_delete=models.CASCADE, null=True, blank=True,
                                  related_name='business_config', verbose_name='Thương hiệu')
    business_type = models.CharField(max_length=20, choices=BUSINESS_TYPE_CHOICES, default='custom',
                                      verbose_name='Mô hình kinh doanh')
    business_name = models.CharField(max_length=255, default='Doanh nghiệp', verbose_name='Tên doanh nghiệp')
    # Module toggles
    mod_orders = models.BooleanField(default=True, verbose_name='Đơn hàng')
    mod_quotations = models.BooleanField(default=True, verbose_name='Báo giá')
    mod_returns = models.BooleanField(default=True, verbose_name='Trả hàng')
    mod_packaging = models.BooleanField(default=True, verbose_name='Đóng gói')
    mod_products = models.BooleanField(default=True, verbose_name='Sản phẩm & Kho')
    mod_customers = models.BooleanField(default=True, verbose_name='Khách hàng')
    mod_finance = models.BooleanField(default=True, verbose_name='Thu chi')
    mod_reports = models.BooleanField(default=True, verbose_name='Báo cáo')
    mod_spa = models.BooleanField(default=False, verbose_name='Spa & Dịch vụ')
    mod_cafe_tables = models.BooleanField(default=False, verbose_name='Quản lý bàn (Cafe)')
    mod_pos = models.BooleanField(default=False, verbose_name='POS bán hàng nhanh')
    # Options
    opt_quotation_salesperson = models.BooleanField(default=False, verbose_name='Hiện người báo giá')
    opt_order_salesperson = models.BooleanField(default=False, verbose_name='Hiện NV bán hàng trên hóa đơn')
    opt_order_server_staff = models.BooleanField(default=False, verbose_name='Hiện NV phục vụ trên hóa đơn')
    opt_order_approver = models.BooleanField(default=False, verbose_name='Hiện người duyệt trên hóa đơn')
    opt_order_bonus = models.BooleanField(default=False, verbose_name='Hiện tiền bonus trên hóa đơn')
    opt_loyalty_points = models.BooleanField(default=False, verbose_name='Tích điểm khách hàng')
    opt_loyalty_rate = models.IntegerField(default=10000, verbose_name='Mỗi X đồng = 1 điểm')
    opt_commission = models.BooleanField(default=False, verbose_name='Hoa hồng nhân viên')
    opt_allow_negative_stock = models.BooleanField(default=False, verbose_name='Cho phép tồn âm (bán khi hết hàng)')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_config'
        verbose_name = 'Cấu hình mô hình KD'
        verbose_name_plural = 'Cấu hình mô hình KD'

    def __str__(self):
        brand_name = self.brand.name if self.brand else 'Mặc định'
        return f"{brand_name} — {self.business_name} ({self.get_business_type_display()})"

    @classmethod
    def get_config(cls, brand=None):
        """Lấy config theo brand. Nếu không có, fallback về config mặc định (pk=1)"""
        if brand:
            try:
                return cls.objects.get(brand=brand)
            except cls.DoesNotExist:
                pass
        # Fallback to default singleton
        config, _ = cls.objects.get_or_create(pk=1, defaults={
            'business_type': 'custom',
            'business_name': 'Doanh nghiệp',
        })
        return config


class Brand(models.Model):
    """Thương hiệu"""
    BUSINESS_TYPE_CHOICES = (
        ('retail', 'Bán lẻ'),
        ('restaurant', 'Quán ăn'),
        ('cafe', 'Cafe'),
        ('spa', 'Spa'),
    )
    name = models.CharField(max_length=255, unique=True, verbose_name='Tên thương hiệu')
    business_type = models.CharField(max_length=20, choices=BUSINESS_TYPE_CHOICES, default='retail',
                                      verbose_name='Mô hình kinh doanh')
    logo = models.ImageField(upload_to='brands/', blank=True, null=True, verbose_name='Logo')
    description = models.TextField(blank=True, null=True, verbose_name='Mô tả')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='Hotline')
    email = models.EmailField(blank=True, null=True, verbose_name='Email')
    website = models.URLField(blank=True, null=True, verbose_name='Website')
    address = models.TextField(blank=True, null=True, verbose_name='Địa chỉ trụ sở')
    tax_code = models.CharField(max_length=20, blank=True, null=True, verbose_name='Mã số thuế')
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='owned_brands', verbose_name='Chủ sở hữu')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'brands'
        verbose_name = 'Thương hiệu'
        verbose_name_plural = 'Thương hiệu'
        ordering = ['name']

    def __str__(self):
        return self.name


class Store(models.Model):
    """Cửa hàng"""
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name='stores', verbose_name='Thương hiệu')
    name = models.CharField(max_length=255, verbose_name='Tên cửa hàng')
    code = models.CharField(max_length=20, unique=True, verbose_name='Mã cửa hàng')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='SĐT')
    email = models.EmailField(blank=True, null=True, verbose_name='Email')
    address = models.TextField(blank=True, null=True, verbose_name='Địa chỉ')
    city = models.CharField(max_length=100, blank=True, null=True, verbose_name='Tỉnh/Thành')
    district = models.CharField(max_length=100, blank=True, null=True, verbose_name='Quận/Huyện')
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='managed_stores', verbose_name='Quản lý')
    open_time = models.TimeField(blank=True, null=True, verbose_name='Giờ mở cửa')
    close_time = models.TimeField(blank=True, null=True, verbose_name='Giờ đóng cửa')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stores'
        verbose_name = 'Cửa hàng'
        verbose_name_plural = 'Cửa hàng'
        ordering = ['brand__name', 'name']

    def __str__(self):
        return f"{self.brand.name} - {self.name}"
