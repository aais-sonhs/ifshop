"""Danh mục và tiện ích cấu hình menu theo thương hiệu."""

from core.store_utils import get_company_brand_for_user


BRAND_MENU_CATALOG = (
    {
        'key': 'overview',
        'label': 'Tổng quan & bán nhanh',
        'icon': 'fas fa-home',
        'items': (
            {'key': 'dashboard', 'label': 'Dashboard'},
            {'key': 'pos', 'label': 'POS Bán hàng'},
            {'key': 'cafe_tables', 'label': 'Sơ đồ bàn'},
        ),
    },
    {
        'key': 'sales',
        'label': 'Bán hàng',
        'icon': 'fas fa-shopping-bag',
        'items': (
            {'key': 'orders', 'label': 'Bán hàng / Báo giá'},
            {'key': 'order_approvals', 'label': 'Duyệt đơn hàng'},
            {'key': 'order_returns', 'label': 'Trả hàng'},
            {'key': 'packaging', 'label': 'Đóng gói'},
        ),
    },
    {
        'key': 'inventory',
        'label': 'Kho & Sản phẩm',
        'icon': 'fas fa-boxes',
        'items': (
            {'key': 'products', 'label': 'Danh sách sản phẩm'},
            {'key': 'warehouses', 'label': 'Quản lý kho'},
            {'key': 'purchase_orders', 'label': 'Đặt hàng nhập'},
            {'key': 'goods_receipts', 'label': 'Nhập hàng'},
            {'key': 'purchase_returns', 'label': 'Trả hàng nhập'},
            {'key': 'stock_checks', 'label': 'Kiểm hàng'},
            {'key': 'stock_transfers', 'label': 'Chuyển hàng'},
            {'key': 'suppliers', 'label': 'Nhà cung cấp'},
        ),
    },
    {
        'key': 'customers',
        'label': 'Khách hàng',
        'icon': 'fas fa-users',
        'items': (
            {'key': 'customers', 'label': 'Danh sách khách hàng'},
            {'key': 'customer_groups', 'label': 'Nhóm khách hàng'},
        ),
    },
    {
        'key': 'finance',
        'label': 'Tài chính',
        'icon': 'fas fa-wallet',
        'items': (
            {'key': 'receipts', 'label': 'Phiếu thu'},
            {'key': 'payments', 'label': 'Phiếu chi'},
            {'key': 'finance_list', 'label': 'Danh sách thu chi'},
            {'key': 'cashbooks', 'label': 'Sổ quỹ'},
            {'key': 'supplier_debts', 'label': 'Công nợ nhà cung cấp'},
            {
                'key': 'financial_plans',
                'label': 'Kế hoạch tài chính',
                'badge': 'Mới',
                'help': 'Lập ngân sách, dự báo dòng tiền và xếp lịch trả nhà cung cấp.',
            },
        ),
    },
    {
        'key': 'reports',
        'label': 'Báo cáo',
        'icon': 'fas fa-chart-line',
        'items': (
            {'key': 'report_sales', 'label': 'Báo cáo bán hàng'},
            {'key': 'report_quotation_profit', 'label': 'Báo cáo lợi nhuận dự kiến'},
            {'key': 'report_purchases', 'label': 'Báo cáo nhập hàng'},
            {'key': 'report_inventory', 'label': 'Báo cáo kho'},
            {'key': 'report_finance', 'label': 'Báo cáo tài chính'},
            {'key': 'report_customers', 'label': 'Báo cáo khách hàng'},
            {'key': 'report_staff_sales', 'label': 'Báo cáo nhân viên bán hàng'},
        ),
    },
    {
        'key': 'spa',
        'label': 'Spa & Dịch vụ',
        'icon': 'fas fa-spa',
        'items': (
            {'key': 'spa_booking_calendar', 'label': 'Lịch hẹn (Lịch)'},
            {'key': 'spa_bookings', 'label': 'Lịch hẹn (Danh sách)'},
            {'key': 'spa_services', 'label': 'Dịch vụ'},
            {'key': 'spa_staff', 'label': 'Nhân viên / KTV'},
            {'key': 'spa_rooms', 'label': 'Phòng'},
        ),
    },
    {
        'key': 'administration',
        'label': 'Quản trị',
        'icon': 'fas fa-tools',
        'items': (
            {'key': 'users', 'label': 'Quản lý người dùng'},
            {'key': 'system_logs', 'label': 'Log hệ thống'},
            {'key': 'role_groups', 'label': 'Nhóm vai trò'},
            {'key': 'permissions', 'label': 'Phân quyền'},
            {'key': 'brand_info', 'label': 'Thông tin công ty'},
            {'key': 'business_config', 'label': 'Mô hình kinh doanh'},
            {'key': 'categories', 'label': 'Danh mục'},
            {'key': 'service_prices', 'label': 'Giá dịch vụ hàng tháng'},
        ),
    },
    {
        'key': 'settings',
        'label': 'Cài đặt',
        'icon': 'fas fa-sliders-h',
        'items': (
            {'key': 'quotation_settings', 'label': 'Cài đặt báo giá'},
            {'key': 'order_settings', 'label': 'Cài đặt đơn hàng'},
            {'key': 'stock_alert_email', 'label': 'Báo email tồn kho'},
            {'key': 'daily_email_report', 'label': 'Báo cáo email hàng ngày'},
            {'key': 'payment_methods', 'label': 'Phương thức thanh toán'},
            {'key': 'printer_settings', 'label': 'Cài đặt máy in'},
            {'key': 'print_brands', 'label': 'Nhãn hàng'},
            {'key': 'print_templates', 'label': 'Mẫu in'},
        ),
    },
)

BRAND_MENU_KEYS = frozenset(
    item['key']
    for group in BRAND_MENU_CATALOG
    for item in group['items']
)


def resolve_brand_menu_visibility(brand=None):
    """Trả về đủ mọi khóa; khóa chưa cấu hình luôn mặc định được hiển thị."""
    configured = brand.menu_visibility if brand and isinstance(brand.menu_visibility, dict) else {}
    return {
        key: configured.get(key, True) if isinstance(configured.get(key, True), bool) else True
        for key in BRAND_MENU_KEYS
    }


def resolve_brand_menu_groups(visibility):
    """Nhóm cha chỉ hiện khi còn ít nhất một menu con được bật."""
    return {
        group['key']: any(visibility[item['key']] for item in group['items'])
        for group in BRAND_MENU_CATALOG
    }


def compact_brand_menu_visibility(visibility):
    """Chỉ lưu các menu bị tắt để menu mới trong tương lai mặc định được bật."""
    return {
        key: False
        for key in BRAND_MENU_KEYS
        if visibility.get(key) is False
    }


def is_menu_visible_for_user(user, menu_key):
    """Kiểm tra menu cho đúng thương hiệu của user; Super Admin luôn được phép."""
    if menu_key not in BRAND_MENU_KEYS:
        return False
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    try:
        store = user.profile.store
    except Exception:
        store = None
    brand = get_company_brand_for_user(user, store=store)
    return resolve_brand_menu_visibility(brand)[menu_key]
