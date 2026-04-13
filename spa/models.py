from django.db import models
from django.contrib.auth.models import User


class Staff(models.Model):
    """Nhân viên / Kỹ thuật viên"""
    POSITION_CHOICES = [
        (1, 'Kỹ thuật viên'),
        (2, 'Quản lý'),
        (3, 'Lễ tân'),
    ]
    code = models.CharField(max_length=20, unique=True, verbose_name='Mã NV')
    name = models.CharField(max_length=255, verbose_name='Họ tên')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='SĐT')
    position = models.IntegerField(choices=POSITION_CHOICES, default=1, verbose_name='Chức vụ')
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='% Hoa hồng')
    avatar = models.ImageField(upload_to='staff/', blank=True, null=True, verbose_name='Ảnh')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    is_active = models.BooleanField(default=True, verbose_name='Đang làm việc')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'spa_staff'
        verbose_name = 'Nhân viên'
        verbose_name_plural = 'Nhân viên'
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Room(models.Model):
    """Phòng / Giường"""
    ROOM_TYPE_CHOICES = [
        (1, 'Phòng thường'),
        (2, 'Phòng VIP'),
        (3, 'Phòng đôi'),
    ]
    STATUS_CHOICES = [
        (0, 'Trống'),
        (1, 'Đang phục vụ'),
        (2, 'Bảo trì'),
    ]
    name = models.CharField(max_length=100, verbose_name='Tên phòng')
    room_type = models.IntegerField(choices=ROOM_TYPE_CHOICES, default=1, verbose_name='Loại phòng')
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name='Trạng thái')
    max_capacity = models.IntegerField(default=1, verbose_name='Sức chứa')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    is_active = models.BooleanField(default=True, verbose_name='Hoạt động')

    class Meta:
        db_table = 'spa_rooms'
        verbose_name = 'Phòng'
        verbose_name_plural = 'Phòng'
        ordering = ['name']

    def __str__(self):
        return self.name


class ServiceCategory(models.Model):
    """Nhóm dịch vụ"""
    name = models.CharField(max_length=255, verbose_name='Tên nhóm')
    description = models.TextField(blank=True, null=True, verbose_name='Mô tả')
    is_active = models.BooleanField(default=True, verbose_name='Hoạt động')

    class Meta:
        db_table = 'spa_service_categories'
        verbose_name = 'Nhóm dịch vụ'
        verbose_name_plural = 'Nhóm dịch vụ'
        ordering = ['name']

    def __str__(self):
        return self.name


class Service(models.Model):
    """Dịch vụ spa"""
    code = models.CharField(max_length=20, unique=True, verbose_name='Mã DV')
    name = models.CharField(max_length=255, verbose_name='Tên dịch vụ')
    category = models.ForeignKey(ServiceCategory, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='services', verbose_name='Nhóm')
    duration_minutes = models.IntegerField(default=60, verbose_name='Thời lượng (phút)')
    price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Giá dịch vụ')
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                          verbose_name='% Hoa hồng riêng (ưu tiên)')
    description = models.TextField(blank=True, null=True, verbose_name='Mô tả')
    image = models.ImageField(upload_to='services/', blank=True, null=True, verbose_name='Hình ảnh')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'spa_services'
        verbose_name = 'Dịch vụ'
        verbose_name_plural = 'Dịch vụ'
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Booking(models.Model):
    """Lịch hẹn / Phiếu dịch vụ"""
    STATUS_CHOICES = [
        (0, 'Đặt trước'),
        (1, 'Đang phục vụ'),
        (2, 'Hoàn thành'),
        (3, 'Hủy'),
    ]
    code = models.CharField(max_length=20, unique=True, verbose_name='Mã lịch hẹn')
    store = models.ForeignKey('system_management.Store', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='bookings', verbose_name='Cửa hàng')
    customer = models.ForeignKey('customers.Customer', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='bookings', verbose_name='Khách hàng')
    customer_name = models.CharField(max_length=255, blank=True, null=True, verbose_name='Tên khách (vãng lai)')
    customer_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='SĐT khách')
    staff = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='bookings', verbose_name='KTV phụ trách')
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='bookings', verbose_name='Phòng')
    booking_date = models.DateField(verbose_name='Ngày hẹn')
    start_time = models.TimeField(verbose_name='Giờ bắt đầu')
    end_time = models.TimeField(blank=True, null=True, verbose_name='Giờ kết thúc')
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name='Trạng thái')
    total_amount = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Tổng tiền')
    discount_amount = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Giảm giá')
    final_amount = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Thành tiền')
    paid_amount = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Đã thanh toán')
    commission_amount = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Hoa hồng KTV')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='bookings_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'spa_bookings'
        verbose_name = 'Lịch hẹn'
        verbose_name_plural = 'Lịch hẹn'
        ordering = ['-booking_date', '-start_time']

    def __str__(self):
        return f"{self.code} - {self.booking_date}"


class BookingItem(models.Model):
    """Chi tiết dịch vụ trong lịch hẹn"""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='items', verbose_name='Lịch hẹn')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='booking_items', verbose_name='Dịch vụ')
    staff = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='booking_items', verbose_name='KTV thực hiện')
    quantity = models.IntegerField(default=1, verbose_name='Số lượng')
    unit_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Đơn giá')
    total_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Thành tiền')
    commission_amount = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Hoa hồng')

    class Meta:
        db_table = 'spa_booking_items'
        verbose_name = 'Chi tiết dịch vụ'
        verbose_name_plural = 'Chi tiết dịch vụ'

    def __str__(self):
        return f"{self.service.name} x{self.quantity}"
