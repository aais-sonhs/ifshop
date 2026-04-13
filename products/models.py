from django.db import models
from django.contrib.auth.models import User
from core.soft_delete import SoftDeleteModel


class Supplier(SoftDeleteModel):
    """Nhà cung cấp"""
    code = models.CharField(max_length=50, unique=True, verbose_name='Mã NCC')
    name = models.CharField(max_length=255, verbose_name='Tên nhà cung cấp')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='Số điện thoại')
    email = models.EmailField(blank=True, null=True, verbose_name='Email')
    address = models.TextField(blank=True, null=True, verbose_name='Địa chỉ')
    tax_code = models.CharField(max_length=20, blank=True, null=True, verbose_name='Mã số thuế')
    contact_person = models.CharField(max_length=100, blank=True, null=True, verbose_name='Người liên hệ')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='suppliers_created')

    class Meta:
        db_table = 'suppliers'
        verbose_name = 'Nhà cung cấp'
        verbose_name_plural = 'Nhà cung cấp'
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}"


class ProductCategory(SoftDeleteModel):
    """Danh mục sản phẩm"""
    name = models.CharField(max_length=255, verbose_name='Tên danh mục')
    description = models.TextField(blank=True, null=True, verbose_name='Mô tả')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='children', verbose_name='Danh mục cha')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'product_categories'
        verbose_name = 'Danh mục sản phẩm'
        verbose_name_plural = 'Danh mục sản phẩm'
        ordering = ['name']

    def __str__(self):
        return self.name


class Warehouse(SoftDeleteModel):
    """Danh mục kho"""
    store = models.ForeignKey('system_management.Store', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='warehouses', verbose_name='Cửa hàng')
    code = models.CharField(max_length=50, unique=True, verbose_name='Mã kho')
    name = models.CharField(max_length=255, verbose_name='Tên kho')
    address = models.TextField(blank=True, null=True, verbose_name='Địa chỉ')
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='managed_warehouses', verbose_name='Quản lý kho')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'warehouses'
        verbose_name = 'Kho'
        verbose_name_plural = 'Kho'
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Product(SoftDeleteModel):
    """Sản phẩm"""
    store = models.ForeignKey('system_management.Store', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='products', verbose_name='Cửa hàng')
    code = models.CharField(max_length=50, unique=True, verbose_name='Mã sản phẩm')
    barcode = models.CharField(max_length=100, blank=True, null=True, verbose_name='Barcode')
    name = models.CharField(max_length=255, verbose_name='Tên sản phẩm')
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='products', verbose_name='Danh mục')
    unit = models.CharField(max_length=50, default='Cái', verbose_name='Đơn vị tính')
    description = models.TextField(blank=True, null=True, verbose_name='Mô tả')
    image = models.ImageField(upload_to='products/', blank=True, null=True, verbose_name='Hình ảnh')

    # Giá
    cost_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Giá vốn')
    listed_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Giá niêm yết')
    selling_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Giá bán')

    # Tồn kho
    min_stock = models.IntegerField(default=0, verbose_name='Tồn kho tối thiểu')
    max_stock = models.IntegerField(default=0, verbose_name='Tồn kho tối đa')

    # SAPO
    sapo_id = models.CharField(max_length=100, blank=True, null=True, verbose_name='Mã SAPO')

    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='products', verbose_name='Nhà cung cấp')
    is_weight_based = models.BooleanField(default=False, verbose_name='Bán theo khối lượng')
    is_service = models.BooleanField(default=False, verbose_name='Sản phẩm dịch vụ')
    is_combo = models.BooleanField(default=False, verbose_name='Sản phẩm combo')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='products_created')

    class Meta:
        db_table = 'products'
        verbose_name = 'Sản phẩm'
        verbose_name_plural = 'Sản phẩm'
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}"


class ProductVariant(models.Model):
    """Biến thể sản phẩm (theo kích thước/size)"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants', verbose_name='Sản phẩm')
    size_name = models.CharField(max_length=50, verbose_name='Kích thước')
    sku = models.CharField(max_length=100, unique=True, verbose_name='Mã SKU')
    barcode = models.CharField(max_length=100, blank=True, null=True, verbose_name='Barcode')
    cost_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Giá vốn')
    listed_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Giá niêm yết')
    selling_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Giá bán')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'product_variants'
        verbose_name = 'Biến thể sản phẩm'
        verbose_name_plural = 'Biến thể sản phẩm'
        ordering = ['product', 'size_name']

    def __str__(self):
        return f"{self.product.code} - {self.size_name}"



class ComboItem(models.Model):
    """Thành phần của combo: liên kết combo → sản phẩm thành phần"""
    combo = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='combo_items',
                               verbose_name='Combo')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='in_combos',
                                 verbose_name='Sản phẩm thành phần')
    quantity = models.DecimalField(max_digits=15, decimal_places=2, default=1, verbose_name='Số lượng')

    class Meta:
        db_table = 'combo_items'
        verbose_name = 'Thành phần combo'
        verbose_name_plural = 'Thành phần combo'
        unique_together = ['combo', 'product']

    def __str__(self):
        return f"{self.combo.name} → {self.product.name} x{self.quantity}"


class ProductStock(models.Model):
    """Tồn kho sản phẩm theo từng kho"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stocks', verbose_name='Sản phẩm')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stocks', verbose_name='Kho')
    quantity = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Số lượng tồn')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'product_stocks'
        verbose_name = 'Tồn kho'
        verbose_name_plural = 'Tồn kho'
        unique_together = ['product', 'warehouse']

    def __str__(self):
        return f"{self.product.name} - {self.warehouse.name}: {self.quantity}"


class PurchaseOrder(SoftDeleteModel):
    """Đặt hàng nhập"""
    STATUS_CHOICES = [
        (0, 'Nháp'),
        (1, 'Đã gửi'),
        (2, 'Đã nhận hàng'),
        (3, 'Hoàn thành'),
        (4, 'Hủy'),
    ]
    code = models.CharField(max_length=50, unique=True, verbose_name='Mã đơn đặt hàng')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, related_name='purchase_orders',
                                  verbose_name='Nhà cung cấp')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, related_name='purchase_orders',
                                   verbose_name='Kho nhập')
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name='Trạng thái')
    total_amount = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Tổng tiền')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    order_date = models.DateField(verbose_name='Ngày đặt hàng')
    expected_date = models.DateField(blank=True, null=True, verbose_name='Ngày dự kiến nhận')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='purchase_orders_created')

    class Meta:
        db_table = 'purchase_orders'
        verbose_name = 'Đơn đặt hàng nhập'
        verbose_name_plural = 'Đơn đặt hàng nhập'
        ordering = ['-order_date']

    def __str__(self):
        return self.code


class PurchaseOrderItem(models.Model):
    """Chi tiết đơn đặt hàng nhập"""
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items',
                                        verbose_name='Đơn đặt hàng')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='purchase_items',
                                 verbose_name='Sản phẩm')
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='purchase_items', verbose_name='Biến thể')
    quantity = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Số lượng đặt')
    received_quantity = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Số lượng nhận')
    unit_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Đơn giá')
    total_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Thành tiền')

    class Meta:
        db_table = 'purchase_order_items'
        verbose_name = 'Chi tiết đơn đặt hàng'
        verbose_name_plural = 'Chi tiết đơn đặt hàng'

    def __str__(self):
        return f"{self.purchase_order.code} - {self.product.name}"


class GoodsReceipt(SoftDeleteModel):
    """Nhập hàng (Phiếu nhập kho)"""
    STATUS_CHOICES = [
        (0, 'Nháp'),
        (1, 'Hoàn thành'),
        (2, 'Hủy'),
    ]
    code = models.CharField(max_length=50, unique=True, verbose_name='Mã phiếu nhập')
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='goods_receipts', verbose_name='Đơn đặt hàng')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, related_name='goods_receipts',
                                  verbose_name='Nhà cung cấp')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, related_name='goods_receipts',
                                   verbose_name='Kho nhập')
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name='Trạng thái')
    total_amount = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Tổng tiền')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    receipt_date = models.DateField(verbose_name='Ngày nhập')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='goods_receipts_created')

    class Meta:
        db_table = 'goods_receipts'
        verbose_name = 'Phiếu nhập kho'
        verbose_name_plural = 'Phiếu nhập kho'
        ordering = ['-receipt_date']

    def __str__(self):
        return self.code


class GoodsReceiptItem(models.Model):
    """Chi tiết phiếu nhập kho"""
    goods_receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name='items',
                                       verbose_name='Phiếu nhập')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='receipt_items',
                                 verbose_name='Sản phẩm')
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='receipt_items', verbose_name='Biến thể')
    quantity = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Số lượng nhập')
    unit_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Đơn giá')
    total_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Thành tiền')

    class Meta:
        db_table = 'goods_receipt_items'
        verbose_name = 'Chi tiết phiếu nhập'
        verbose_name_plural = 'Chi tiết phiếu nhập'


class StockCheck(SoftDeleteModel):
    """Kiểm hàng (Kiểm kê kho)"""
    STATUS_CHOICES = [
        (0, 'Đang kiểm'),
        (1, 'Hoàn thành'),
        (2, 'Hủy'),
    ]
    code = models.CharField(max_length=50, unique=True, verbose_name='Mã phiếu kiểm')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, related_name='stock_checks',
                                   verbose_name='Kho')
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name='Trạng thái')
    check_date = models.DateField(verbose_name='Ngày kiểm')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='stock_checks_created')

    class Meta:
        db_table = 'stock_checks'
        verbose_name = 'Phiếu kiểm kê'
        verbose_name_plural = 'Phiếu kiểm kê'
        ordering = ['-check_date']


class StockCheckItem(models.Model):
    """Chi tiết phiếu kiểm kê"""
    stock_check = models.ForeignKey(StockCheck, on_delete=models.CASCADE, related_name='items',
                                      verbose_name='Phiếu kiểm')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='check_items',
                                 verbose_name='Sản phẩm')
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='check_items', verbose_name='Biến thể')
    system_quantity = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Tồn hệ thống')
    actual_quantity = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Tồn thực tế')
    difference = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Chênh lệch')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')

    class Meta:
        db_table = 'stock_check_items'
        verbose_name = 'Chi tiết kiểm kê'
        verbose_name_plural = 'Chi tiết kiểm kê'


class StockTransfer(SoftDeleteModel):
    """Chuyển hàng giữa các kho"""
    STATUS_CHOICES = [
        (0, 'Nháp'),
        (1, 'Đang chuyển'),
        (2, 'Hoàn thành'),
        (3, 'Hủy'),
    ]
    code = models.CharField(max_length=50, unique=True, verbose_name='Mã phiếu chuyển')
    from_warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True,
                                        related_name='transfers_out', verbose_name='Kho xuất')
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True,
                                      related_name='transfers_in', verbose_name='Kho nhập')
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name='Trạng thái')
    transfer_date = models.DateField(verbose_name='Ngày chuyển')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='transfers_created')

    class Meta:
        db_table = 'stock_transfers'
        verbose_name = 'Phiếu chuyển kho'
        verbose_name_plural = 'Phiếu chuyển kho'
        ordering = ['-transfer_date']


class StockTransferItem(models.Model):
    """Chi tiết phiếu chuyển kho"""
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name='items',
                                  verbose_name='Phiếu chuyển')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='transfer_items',
                                 verbose_name='Sản phẩm')
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='transfer_items', verbose_name='Biến thể')
    quantity = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Số lượng')

    class Meta:
        db_table = 'stock_transfer_items'
        verbose_name = 'Chi tiết chuyển kho'
        verbose_name_plural = 'Chi tiết chuyển kho'


class CostAdjustment(models.Model):
    """Điều chỉnh giá vốn"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='cost_adjustments',
                                 verbose_name='Sản phẩm')
    old_cost = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Giá vốn cũ')
    new_cost = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Giá vốn mới')
    reason = models.TextField(blank=True, null=True, verbose_name='Lý do')
    adjusted_at = models.DateTimeField(auto_now_add=True, verbose_name='Ngày điều chỉnh')
    adjusted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cost_adjustments')

    class Meta:
        db_table = 'cost_adjustments'
        verbose_name = 'Điều chỉnh giá vốn'
        verbose_name_plural = 'Điều chỉnh giá vốn'
        ordering = ['-adjusted_at']
