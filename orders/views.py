import json
import logging
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_FLOOR
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import transaction, IntegrityError
from django.db.models import Prefetch, Q
from .models import (
    Order, OrderItem, Quotation, QuotationItem, OrderReturn,
    Packaging, OrderEditHistory,
)
from customers.models import Customer
from products.models import Product, Warehouse, ProductStock, ProductVariant
from finance.models import Receipt, FinanceCategory, CashBook, Payment, PaymentMethodOption
from finance.services import (
    cancel_receipt_with_effect,
    save_receipt_with_effect,
    update_order_payment_status,
)
from system_management.models import PrintTemplate
from core.store_utils import (
    brand_owner_required,
    filter_by_store,
    get_managed_store_ids,
    get_user_store,
)

logger = logging.getLogger(__name__)

GUEST_CUSTOMER_CODE_PREFIX = 'KHLE-'
GUEST_CUSTOMER_NAME = 'Khách lẻ / khách vãng lai'

# Luồng chuyển trạng thái của đơn hàng theo đúng quy trình một chiều:
# Báo giá -> Đơn hàng -> Xử lý -> Đóng gói -> Xuất kho -> Hoàn thành.
ORDER_STATUS_TRANSITIONS = {
    0: {0, 1, 6},  # Báo giá -> Đơn hàng hoặc Hủy
    1: {1, 2, 6},  # Đơn hàng -> Đang xử lý hoặc Hủy
    2: {2, 3, 6},  # Đang xử lý -> Đóng gói hoặc Hủy
    3: {3, 4, 6},  # Đóng gói -> Đã xuất kho hoặc Hủy
    4: {4, 5, 6},  # Đã xuất kho -> Hoàn thành hoặc Hủy
    5: {5},        # Hoàn thành -> khóa
    6: {6},        # Hủy -> khóa
}
ORDER_STOCK_EXPORTED_STATUSES = {4, 5}

PRINT_TEMPLATE_DEFAULTS = {
    'k80': {'title': 'HÓA ĐƠN BÁN HÀNG', 'footer_note': 'Cảm ơn quý khách!\nHẹn gặp lại!'},
    'a4': {'title': 'HÓA ĐƠN BÁN HÀNG', 'footer_note': 'Cảm ơn quý khách đã mua hàng.'},
    'quotation': {
        'title': 'BÁO GIÁ',
        'terms': 'Báo giá có hiệu lực theo ngày hiệu lực trên phiếu.\nGiá trên chưa bao gồm VAT nếu chưa ghi rõ.\nThanh toán theo thỏa thuận hai bên.',
        'footer_note': 'Cảm ơn Quý khách đã quan tâm.',
    },
    'quotation_a4': {
        'title': 'BÁO GIÁ',
        'terms': 'Báo giá có hiệu lực theo ngày hiệu lực trên phiếu.\nGiá trên chưa bao gồm VAT nếu chưa ghi rõ.\nThanh toán theo thỏa thuận hai bên.',
        'footer_note': 'Cảm ơn Quý khách đã quan tâm.',
    },
    'warranty': {
        'title': 'PHIẾU BẢO HÀNH',
        'terms': 'Sản phẩm được bảo hành theo chính sách của nhà sản xuất / cửa hàng.\nKhông bảo hành nếu sản phẩm bị hư hỏng do tác động bên ngoài, sử dụng sai cách.\nKhách hàng xuất trình phiếu bảo hành này khi yêu cầu bảo hành.\nPhiếu bảo hành chỉ có giá trị khi có đầy đủ thông tin và dấu xác nhận.',
    },
    'export': {'title': 'PHIẾU XUẤT KHO', 'footer_note': 'Ngày in được ghi tự động trên phiếu.'},
}


def _to_decimal(value, default='0'):
    try:
        return Decimal(str(value if value not in (None, '') else default))
    except Exception:
        return Decimal(str(default))


def _non_negative_decimal(value, default='0'):
    return max(_to_decimal(value, default), Decimal('0'))


def _normalize_percentage(value):
    percent = _to_decimal(value)
    if percent < 0:
        return Decimal('0')
    if percent > 100:
        return Decimal('100')
    return percent


def _adjust_stock_quantity(stock, delta):
    stock.quantity = _to_decimal(stock.quantity) + _to_decimal(delta)
    stock.save(update_fields=['quantity'])


def _get_locked_stock(product_id, warehouse_id):
    stock, _ = ProductStock.objects.select_for_update().get_or_create(
        product_id=product_id,
        warehouse_id=warehouse_id,
        defaults={'quantity': 0},
    )
    return stock


def _allow_negative_stock_for_store(store):
    if not store:
        return False
    try:
        from system_management.models import BusinessConfig
        brand = store.brand if getattr(store, 'brand_id', None) else None
        return bool(BusinessConfig.get_config(brand=brand).opt_allow_negative_stock)
    except Exception:
        return False


def _adjust_locked_stock(stock, delta, allow_negative=True):
    delta = _to_decimal(delta)
    new_quantity = _to_decimal(stock.quantity) + delta
    if not allow_negative and new_quantity < 0:
        product_name = stock.product.name if getattr(stock, 'product_id', None) and stock.product else 'sản phẩm'
        warehouse_name = stock.warehouse.name if getattr(stock, 'warehouse_id', None) and stock.warehouse else 'kho'
        raise ValueError(f'Tồn kho không đủ cho {product_name} tại {warehouse_name}')
    stock.quantity = new_quantity
    stock.save(update_fields=['quantity'])


def _get_sales_customers_queryset(request):
    from core.store_utils import get_managed_store_ids

    store_ids = get_managed_store_ids(request.user)
    return Customer.objects.filter(
        is_active=True,
        store_id__in=store_ids,
    ).exclude(code__startswith=GUEST_CUSTOMER_CODE_PREFIX)


def _is_guest_customer(customer):
    return bool(customer and customer.code and customer.code.startswith(GUEST_CUSTOMER_CODE_PREFIX))


def _get_default_store_for_request(request):
    from core.store_utils import get_managed_store_ids as _get_store_ids
    from system_management.models import Store as _Store

    user_store = get_user_store(request)
    if user_store:
        return user_store

    store_ids = _get_store_ids(request.user)
    if not store_ids:
        return None
    return _Store.objects.filter(id__in=store_ids).order_by('id').first()


def _get_brand_for_print(request, record=None):
    store = getattr(record, 'store', None)
    if store and getattr(store, 'brand_id', None):
        return store.brand
    try:
        profile = request.user.profile
        if profile.store and profile.store.brand_id:
            return profile.store.brand
    except Exception:
        pass
    try:
        from core.store_utils import get_owned_brands
        brands = get_owned_brands(request.user)
        return brands.first() if brands.exists() else None
    except Exception:
        return None


def _get_print_template(template_type, brand=None):
    defaults = PRINT_TEMPLATE_DEFAULTS.get(template_type, {})
    title = defaults.get('title') or dict(PrintTemplate.TEMPLATE_TYPE_CHOICES).get(template_type, 'Mẫu in')
    template, _ = PrintTemplate.objects.get_or_create(
        brand=brand,
        template_type=template_type,
        defaults={
            'title': title,
            'header_note': defaults.get('header_note', ''),
            'terms': defaults.get('terms', ''),
            'footer_note': defaults.get('footer_note', ''),
        },
    )
    return template


def _get_or_create_guest_customer(request, store=None):
    store = store or _get_default_store_for_request(request)
    store_key = store.id if store else 0
    guest_code = f'{GUEST_CUSTOMER_CODE_PREFIX}{store_key:03d}'

    guest = Customer.all_objects.filter(code=guest_code).first()
    if guest:
        update_fields = []
        if guest.is_deleted:
            guest.is_deleted = False
            guest.deleted_at = None
            update_fields.extend(['is_deleted', 'deleted_at'])
        if not guest.is_active:
            guest.is_active = True
            update_fields.append('is_active')
        if guest.name != GUEST_CUSTOMER_NAME:
            guest.name = GUEST_CUSTOMER_NAME
            update_fields.append('name')
        if store and guest.store_id != store.id:
            guest.store = store
            update_fields.append('store')
        if update_fields:
            guest.save(update_fields=update_fields)
        return guest

    return Customer.objects.create(
        code=guest_code,
        name=GUEST_CUSTOMER_NAME,
        customer_type=1,
        store=store,
        is_active=True,
        created_by=request.user,
    )


def _resolve_sale_customer(request, customer_id):
    """Lấy khách hàng trong phạm vi cửa hàng; nếu thiếu thì dùng khách lẻ mặc định."""
    if customer_id:
        customer = _get_sales_customers_queryset(request).filter(id=customer_id).first()
        if customer:
            return customer
    return _get_or_create_guest_customer(request)


def _resolve_sales_record_store(request, customer, warehouse, products, current_store=None):
    """Xác định store nghiệp vụ và chặn trộn dữ liệu giữa các cửa hàng."""
    store = warehouse.store if warehouse else None

    if customer and not _is_guest_customer(customer) and customer.store_id:
        if store and store.id != customer.store_id:
            raise ValueError('Khách hàng không cùng cửa hàng với kho xuất.')
        store = customer.store

    for product in products:
        if not product or not product.store_id:
            continue
        if store and store.id != product.store_id:
            raise ValueError(f'Sản phẩm "{product.name}" không cùng cửa hàng với chứng từ.')
        store = product.store

    store = store or current_store or _get_default_store_for_request(request)

    if store and customer and _is_guest_customer(customer) and customer.store_id != store.id:
        customer = _get_or_create_guest_customer(request, store=store)

    return store, customer


def _filter_order_returns_by_scope(queryset, request):
    """Lọc phiếu trả theo store hợp lệ.

    Ưu tiên order.store. Với dữ liệu dev/legacy thiếu order, fallback sang
    warehouse.store rồi customer.store để vẫn nhìn thấy và chỉnh lại dữ liệu.
    """
    if request.user.is_superuser:
        return queryset.none()
    store_ids = get_managed_store_ids(request.user)
    if not store_ids:
        return queryset.none()
    return queryset.filter(
        Q(order__store_id__in=store_ids) |
        Q(order__isnull=True, warehouse__store_id__in=store_ids) |
        Q(order__isnull=True, warehouse__isnull=True, customer__store_id__in=store_ids)
    ).distinct()


def _get_order_for_user(request, order_id, queryset=None):
    """Lấy đơn hàng trong phạm vi store mà user đang được phép thao tác."""
    if not order_id:
        return None
    base_queryset = queryset if queryset is not None else Order.objects.all()
    return filter_by_store(base_queryset.filter(id=order_id), request).first()


def _get_quotation_for_user(request, quotation_id):
    """Lấy báo giá trong phạm vi store mà user đang được phép thao tác."""
    if not quotation_id:
        return None
    return filter_by_store(Quotation.objects.filter(id=quotation_id), request).first()


def _get_warehouse_for_user(request, warehouse_id):
    """Lấy kho trong phạm vi store mà user được phép thao tác."""
    if not warehouse_id:
        return None
    return filter_by_store(Warehouse.objects.filter(id=warehouse_id), request).first()


def _get_product_for_user(request, product_id):
    """Lấy sản phẩm trong phạm vi store mà user được phép thao tác."""
    if not product_id:
        return None
    return filter_by_store(Product.objects.filter(id=product_id), request).first()


def _get_variant_for_product(product, variant_id):
    if not variant_id:
        return None
    return ProductVariant.objects.filter(id=variant_id, product=product).first()


def _get_packaging_for_user(request, packaging_id):
    if not packaging_id:
        return None
    return filter_by_store(
        Packaging.objects.filter(id=packaging_id),
        request,
        field_name='order__store',
    ).first()


def _get_approver_for_user(request, approver_id):
    """Người duyệt phải nằm trong cùng phạm vi store user hiện tại quản lý."""
    if not approver_id:
        return None
    from django.contrib.auth.models import User as AuthUser
    return AuthUser.objects.filter(
        id=approver_id,
        is_active=True,
        profile__store_id__in=get_managed_store_ids(request.user),
    ).first()


def _mark_quotation_as_used(quotation_id):
    """Đánh dấu báo giá đã được dùng để tạo đơn, trừ trường hợp báo giá đã hủy."""
    if not quotation_id:
        return
    Quotation.objects.filter(id=quotation_id).exclude(status=4).update(status=3)


def _reopen_quotation_if_unused(quotation_id, exclude_order_id=None):
    """Mở lại báo giá nếu không còn đơn chưa hủy nào khác liên kết với nó."""
    if not quotation_id:
        return

    linked_orders = Order.objects.exclude(status=6).filter(quotation_id=quotation_id)
    if exclude_order_id:
        linked_orders = linked_orders.exclude(id=exclude_order_id)

    if linked_orders.exists():
        return

    Quotation.objects.filter(id=quotation_id, status=3).update(status=2)


def _validate_unique_line_items(items_data):
    seen = set()
    for item in items_data:
        product_id = item.get('product_id')
        if not product_id:
            continue
        key = (str(product_id), str(item.get('variant_id') or ''))
        if key in seen:
            raise ValueError('Không được nhập trùng sản phẩm/biến thể trong cùng một đơn.')
        seen.add(key)


def _payload_is_service_line(item):
    return not item.get('product_id') and bool(item.get('is_service_line') or item.get('item_type') == 'service')


def _payload_service_name(item):
    return (item.get('item_name') or item.get('product_name') or item.get('name') or '').strip()


def _payload_service_unit(item):
    return (item.get('unit') or '').strip()[:50]


def _item_display_code(item):
    return item.product.code if item.product else 'DV'


def _item_display_name(item):
    return item.product.name if item.product else (item.item_name or 'Dịch vụ')


def _item_display_unit(item):
    return item.product.unit if item.product else (item.unit or '')


def _build_default_warranty_items(items):
    """Chuẩn hóa dòng in bảo hành từ item gốc; frontend có thể gửi bản chỉnh sửa riêng."""
    warranty_items = []
    for item in items:
        if not item.product_id or getattr(item, 'is_service_line', False):
            continue
        warranty_items.append({
            'code': _item_display_code(item),
            'name': _item_display_name(item),
            'unit': _item_display_unit(item),
            'quantity': item.quantity,
            'serial': '',
            'warranty_term': '',
            'note': '',
        })
    return warranty_items


def _parse_warranty_items_payload(raw_payload):
    if not raw_payload:
        return None
    try:
        payload = json.loads(raw_payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, list):
        return None

    warranty_items = []
    for row in payload[:100]:
        if not isinstance(row, dict):
            continue
        name = (row.get('name') or row.get('product_name') or '').strip()
        if not name:
            continue
        warranty_items.append({
            'code': (row.get('code') or row.get('product_code') or '').strip()[:80],
            'name': name[:255],
            'unit': (row.get('unit') or '').strip()[:50],
            'quantity': _non_negative_decimal(row.get('quantity', 1)),
            'serial': (row.get('serial') or '').strip()[:255],
            'warranty_term': (row.get('warranty_term') or '').strip()[:120],
            'note': (row.get('note') or '').strip()[:255],
        })
    return warranty_items


def _get_reserved_stock_maps(request, exclude_order_id=None):
    reserved_by_product = defaultdict(lambda: defaultdict(float))
    pending_by_product = defaultdict(lambda: defaultdict(float))

    def accumulate_items(order_queryset, target_map):
        order_items = OrderItem.objects.filter(order__in=order_queryset).select_related(
            'order', 'product'
        ).prefetch_related('product__combo_items__product')

        for item in order_items:
            warehouse_id = item.order.warehouse_id
            if not warehouse_id:
                continue
            if not item.product_id or not item.product:
                continue

            if item.product.is_combo:
                for combo_item in item.product.combo_items.all():
                    if combo_item.product.is_service:
                        continue
                    target_map[combo_item.product_id][warehouse_id] += (
                        float(item.quantity) * float(combo_item.quantity)
                    )
            elif not item.product.is_service:
                target_map[item.product_id][warehouse_id] += float(item.quantity)

    reservable_orders = Order.objects.filter(
        status__in=[1, 2, 3],
        warehouse_id__isnull=False,
    ).filter(
        Q(approver_id__isnull=True) | Q(approval_status=2)
    )
    reservable_orders = filter_by_store(reservable_orders, request)
    if exclude_order_id:
        reservable_orders = reservable_orders.exclude(id=exclude_order_id)
    accumulate_items(reservable_orders, reserved_by_product)

    pending_orders = Order.objects.filter(
        status__in=[0, 1],
        approval_status=1,
        warehouse_id__isnull=False,
    )
    pending_orders = filter_by_store(pending_orders, request)
    if exclude_order_id:
        pending_orders = pending_orders.exclude(id=exclude_order_id)
    accumulate_items(pending_orders, pending_by_product)

    total_reserved_by_product = defaultdict(float)
    for product_id, warehouse_map in reserved_by_product.items():
        total_reserved_by_product[product_id] = sum(warehouse_map.values())

    total_pending_by_product = defaultdict(float)
    for product_id, warehouse_map in pending_by_product.items():
        total_pending_by_product[product_id] = sum(warehouse_map.values())

    return reserved_by_product, total_reserved_by_product, pending_by_product, total_pending_by_product


def _floor_stock_capacity(quantity, required_quantity):
    quantity = Decimal(str(quantity or 0))
    required_quantity = Decimal(str(required_quantity or 0))
    if required_quantity <= 0:
        return 0
    return int((quantity / required_quantity).to_integral_value(rounding=ROUND_FLOOR))


def _get_combo_stock_maps(product, reserved_by_product, pending_by_product):
    """Calculate combo availability from component inventory per warehouse."""
    component_items = [
        item for item in product.combo_items.all()
        if item.product and not item.product.is_service and Decimal(str(item.quantity or 0)) > 0
    ]
    if not component_items:
        return {}, {}, {}, {}, 0.0, 0.0, 0.0, 0.0

    warehouse_ids = set()
    component_stock_maps = {}
    for item in component_items:
        stock_map = {}
        for stock in item.product.stocks.all():
            stock_map[int(stock.warehouse_id)] = float(stock.quantity)
            warehouse_ids.add(int(stock.warehouse_id))
        component_stock_maps[item.product_id] = stock_map
        warehouse_ids.update(int(wid) for wid in reserved_by_product[item.product_id].keys())
        warehouse_ids.update(int(wid) for wid in pending_by_product[item.product_id].keys())

    stocks = {}
    reserved_stocks = {}
    pending_stocks = {}
    sellable_stocks = {}

    for warehouse_id in sorted(warehouse_ids):
        actual_capacities = []
        sellable_capacities = []
        pending_capacities = []
        for item in component_items:
            required_qty = Decimal(str(item.quantity))
            component_stocks = component_stock_maps.get(item.product_id, {})
            actual_qty = component_stocks.get(warehouse_id, 0)
            reserved_qty = reserved_by_product[item.product_id].get(warehouse_id, 0)
            pending_qty = pending_by_product[item.product_id].get(warehouse_id, 0)

            actual_capacities.append(_floor_stock_capacity(actual_qty, required_qty))
            sellable_capacities.append(_floor_stock_capacity(actual_qty - reserved_qty, required_qty))
            pending_capacities.append(_floor_stock_capacity(pending_qty, required_qty))

        actual_combo_qty = min(actual_capacities) if actual_capacities else 0
        sellable_combo_qty = min(sellable_capacities) if sellable_capacities else 0
        pending_combo_qty = min(pending_capacities) if pending_capacities else 0
        reserved_combo_qty = max(actual_combo_qty - sellable_combo_qty, 0)

        stocks[str(warehouse_id)] = float(actual_combo_qty)
        reserved_stocks[str(warehouse_id)] = float(reserved_combo_qty)
        pending_stocks[str(warehouse_id)] = float(pending_combo_qty)
        sellable_stocks[str(warehouse_id)] = float(sellable_combo_qty)

    total_stock = sum(stocks.values())
    total_reserved_stock = sum(reserved_stocks.values())
    total_pending_stock = sum(pending_stocks.values())
    total_sellable_stock = sum(sellable_stocks.values())
    return (
        stocks,
        reserved_stocks,
        pending_stocks,
        sellable_stocks,
        float(total_stock),
        float(total_reserved_stock),
        float(total_pending_stock),
        float(total_sellable_stock),
    )


def _log_order_history(order, actor, action, summary='', status_before=None, status_after=None):
    """Ghi lại nhật ký thay đổi để dễ truy vết thao tác nghiệp vụ."""
    OrderEditHistory.objects.create(
        order=order,
        actor=actor,
        action=action,
        summary=summary or '',
        status_before=status_before,
        status_after=status_after,
    )


def _get_cashbook_for_payment(payment_method, selected_method=None, cash_book_id=None):
    """Chọn quỹ ưu tiên theo dữ liệu người dùng nhập, sau đó fallback về cấu hình mặc định."""
    if cash_book_id:
        cash_book = CashBook.objects.filter(id=cash_book_id, is_active=True).first()
        if cash_book:
            return cash_book
    if selected_method and selected_method.default_cash_book_id:
        return selected_method.default_cash_book
    lookup = 'ngân hàng' if payment_method == 2 else 'tiền mặt'
    return CashBook.objects.filter(is_active=True, name__icontains=lookup).first()


def _next_receipt_code(base_code):
    """Sinh mã phiếu thu không trùng, kể cả với bản ghi đã xóa mềm."""
    receipt_code = base_code
    suffix = 1
    while Receipt.all_objects.filter(code=receipt_code).exists():
        suffix += 1
        receipt_code = f'{base_code}-{suffix}'
    return receipt_code


def _next_payment_code(base_code, exclude_id=None):
    """Sinh mã phiếu chi không trùng, kể cả với bản ghi đã xóa mềm."""
    payment_code = base_code
    suffix = 1
    while Payment.all_objects.filter(code=payment_code).exclude(id=exclude_id).exists():
        suffix += 1
        payment_code = f'{base_code}-{suffix}'
    return payment_code


def _adjust_refund_cashbook(cash_book_id, amount_delta, validate_non_negative=False):
    if not cash_book_id:
        return None
    cash_book = CashBook.objects.select_for_update().get(id=cash_book_id)
    amount_delta = _to_decimal(amount_delta)
    new_balance = _to_decimal(cash_book.balance) + amount_delta
    if validate_non_negative and new_balance < 0:
        raise ValueError(
            f'Số dư quỹ "{cash_book.name}" không đủ để hoàn tiền. '
            f'Số dư hiện tại: {int(cash_book.balance):,}đ, cần chi: {int(abs(amount_delta)):,}đ.'
        )
    cash_book.balance = new_balance
    cash_book.save(update_fields=['balance'])
    return cash_book


def _create_completed_receipt_for_order(order, actor, amount, payment_method=2,
                                        payment_method_option_id=None, cash_book_id=None,
                                        base_code=None, description_suffix='tự động'):
    """Tạo phiếu thu hoàn thành cho đơn hàng và áp hiệu ứng sổ quỹ ngay lập tức."""
    amount = Decimal(str(amount or 0))
    if amount <= 0:
        return None

    selected_method = None
    if payment_method_option_id:
        selected_method = PaymentMethodOption.objects.select_related('default_cash_book').filter(
            id=payment_method_option_id,
            is_active=True,
        ).first()
        if selected_method:
            payment_method = selected_method.legacy_type if selected_method.legacy_type in (1, 2) else 2

    cash_book = _get_cashbook_for_payment(payment_method, selected_method, cash_book_id)
    sale_cat = FinanceCategory.objects.filter(
        type=1, name__icontains='bán hàng', is_active=True
    ).first()

    receipt = Receipt(
        code=_next_receipt_code(base_code or f'PT-{order.code}'),
        store=order.store,
        category=sale_cat,
        customer_id=order.customer_id,
        order=order,
        amount=amount,
        description=f'Thu tiền đơn hàng {order.code} ({description_suffix})',
        receipt_date=order.order_date or date.today(),
        status=1,
        payment_method=payment_method,
        payment_method_option=selected_method,
        cash_book=cash_book,
        created_by=actor,
    )
    save_receipt_with_effect(receipt)
    return receipt


def _sync_refund_payment_for_return(order_return, actor, payment_method_option_id=None,
                                    payment_method=2, cash_book_id=None):
    """Tạo/cập nhật phiếu chi hoàn tiền theo phiếu trả hàng hoàn thành."""
    base_code = f'PC-{order_return.code}'
    reference = f'ORDER_RETURN:{order_return.id}'
    payment_qs = Payment.all_objects.select_for_update()
    existing = payment_qs.filter(reference=reference).first()
    if not existing:
        existing = payment_qs.filter(
            code=base_code,
            description__icontains=f'phiếu trả {order_return.code}',
        ).first()

    if order_return.status != 2 or _to_decimal(order_return.total_refund) <= 0:
        existing_is_active = existing and not getattr(existing, 'is_deleted', False)
        if existing_is_active and existing.status == 1 and existing.cash_book_id:
            _adjust_refund_cashbook(existing.cash_book_id, existing.amount)
        if existing_is_active:
            existing.status = 2
            existing.note = f'[HỦY TỰ ĐỘNG] Phiếu trả {order_return.code} không còn ở trạng thái Hoàn thành.'
            existing.save(update_fields=['status', 'note'])
        return existing

    selected_method = None
    if payment_method_option_id:
        selected_method = PaymentMethodOption.objects.select_related('default_cash_book').filter(
            id=payment_method_option_id,
            is_active=True,
        ).first()
        if selected_method:
            payment_method = selected_method.legacy_type if selected_method.legacy_type in (1, 2) else 2
    elif existing and existing.payment_method_option_id:
        selected_method = existing.payment_method_option
    else:
        selected_method = PaymentMethodOption.objects.select_related('default_cash_book').filter(is_active=True).first()
        if selected_method:
            payment_method = selected_method.legacy_type if selected_method.legacy_type in (1, 2) else 2

    cash_book = _get_cashbook_for_payment(payment_method, selected_method, cash_book_id)
    if not cash_book and existing and existing.cash_book_id:
        cash_book = existing.cash_book
    if not cash_book:
        raise ValueError('Phương thức hoàn tiền chưa có tài khoản/quỹ mặc định để ghi nhận phiếu chi.')

    existing_is_active = existing and not getattr(existing, 'is_deleted', False)
    if existing_is_active and existing.status == 1 and existing.cash_book_id:
        _adjust_refund_cashbook(existing.cash_book_id, existing.amount)

    payment = existing or Payment(created_by=actor)
    payment.code = _next_payment_code(base_code, exclude_id=payment.id)
    if getattr(payment, 'is_deleted', False):
        payment.is_deleted = False
        payment.deleted_at = None
    refund_cat = FinanceCategory.objects.filter(
        type=2, name__icontains='hoàn', is_active=True
    ).first() or FinanceCategory.objects.filter(type=2, is_active=True).first()
    payment.store = order_return.order.store if order_return.order else None
    payment.category = refund_cat
    payment.cash_book = cash_book
    payment.payment_method_option = selected_method
    payment.customer = order_return.customer
    payment.amount = _to_decimal(order_return.total_refund)
    payment.description = f'Hoàn tiền phiếu trả {order_return.code} - đơn {order_return.order.code if order_return.order else ""}'
    payment.payment_date = order_return.return_date
    payment.reference = reference
    payment.status = 1
    payment.payment_method = payment_method
    payment.note = order_return.reason or ''

    _adjust_refund_cashbook(cash_book.id, -payment.amount, validate_non_negative=True)
    payment.save()
    return payment


def _refresh_order_payment(order):
    """Đồng bộ `paid_amount` và `payment_status` từ toàn bộ phiếu thu hiện có."""
    update_order_payment_status(order)
    order.refresh_from_db(fields=['paid_amount', 'payment_status', 'status'])


def _order_exports_stock_status(status):
    return int(status or 0) in ORDER_STOCK_EXPORTED_STATUSES


def _order_can_complete(order, payment_status=None, exported_status=None):
    payment_status = order.payment_status if payment_status is None else payment_status
    exported_status = order.status if exported_status is None else exported_status
    approved = not order.approver_id or order.approval_status == 2
    return int(exported_status or 0) == 4 and int(payment_status or 0) == 2 and approved


def _project_payment_status(order, paid_amount):
    target_total = max(_to_decimal(order.final_amount), Decimal('0'))
    paid_amount = _to_decimal(paid_amount)
    if paid_amount >= target_total:
        return 2
    if paid_amount > 0:
        return 1
    return 0


def _completion_block_message(order, payment_status=None, exported_status=None):
    missing = []
    exported_status = order.status if exported_status is None else exported_status
    if int(exported_status or 0) != 4:
        missing.append('xuất kho')
    if int(payment_status if payment_status is not None else order.payment_status) != 2:
        missing.append('thanh toán đủ')
    if order.approver_id and order.approval_status != 2:
        missing.append('duyệt đơn')
    if missing:
        return 'Chỉ được hoàn thành đơn hàng sau khi đã ' + ' và '.join(missing) + '.'
    return ''


def _calculate_line_total(quantity, unit_price, discount_percent):
    """Tính thành tiền của một dòng hàng sau khi trừ chiết khấu theo dòng."""
    qty = _non_negative_decimal(quantity)
    price = _non_negative_decimal(unit_price)
    discount = _normalize_percentage(discount_percent)
    return qty * price * (Decimal('1') - (discount / Decimal('100')))


def _calculate_final_amount(total, discount_amount=0, shipping_fee=0):
    """Tính tổng thanh toán và chặn mọi trường hợp âm do chiết khấu quá lớn."""
    final_amount = _to_decimal(total) - _non_negative_decimal(discount_amount) + _non_negative_decimal(shipping_fee)
    return final_amount if final_amount > 0 else Decimal('0')


def _build_receipt_items_from_payload(data, order, existing_paid):
    """Chuẩn hóa dữ liệu thanh toán từ payload cũ/mới về cùng một cấu trúc danh sách."""
    payment_lines = data.get('payment_lines', [])
    pay_mode = data.get('pay_mode', '')
    is_paid = data.get('is_paid', True) if not pay_mode else (pay_mode == 'full')
    payment_amount = float(data.get('payment_amount', 0) or 0)

    if payment_lines and isinstance(payment_lines, list):
        receipt_items = []
        for payment_line in payment_lines:
            amount = float(payment_line.get('amount', 0) or 0)
            if amount <= 0:
                continue
            receipt_items.append({
                'amount': amount,
                'payment_method_option_id': payment_line.get('payment_method_option_id'),
                'payment_method': int(payment_line.get('payment_method', 2) or 2),
                'cash_book_id': payment_line.get('cash_book_id'),
            })
        return receipt_items

    if pay_mode == 'partial' and payment_amount > 0:
        amount_to_collect = payment_amount
    elif is_paid:
        amount_to_collect = float(order.final_amount) - existing_paid
    else:
        amount_to_collect = 0

    if amount_to_collect <= 0:
        return []

    return [{
        'amount': amount_to_collect,
        'payment_method_option_id': data.get('payment_method_option_id'),
        'payment_method': int(data.get('payment_method', 2) or 2),
        'cash_book_id': data.get('cash_book_id'),
    }]


def _normalize_optional_int(value):
    """Chuẩn hóa id từ payload HTML/JSON về int hoặc None để so sánh an toàn."""
    if value in (None, '', 0, '0'):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _order_item_signature_from_queryset(items):
    """Tạo chữ ký dữ liệu item hiện có để phát hiện thay đổi khi đơn đã có phiếu thu."""
    return sorted([
        (
            item.product_id,
            item.variant_id,
            item.item_name or '',
            item.unit or '',
            bool(item.is_service_line),
            _to_decimal(item.quantity),
            _to_decimal(item.unit_price),
            _to_decimal(item.discount_percent),
        )
        for item in items
    ])


def _order_item_signature_from_payload(items_data):
    """Tạo chữ ký item từ payload frontend theo cùng format với dữ liệu trong DB."""
    signature = []
    for item in items_data:
        signature.append((
            _normalize_optional_int(item.get('product_id')),
            _normalize_optional_int(item.get('variant_id')),
            _payload_service_name(item) if _payload_is_service_line(item) else '',
            _payload_service_unit(item) if _payload_is_service_line(item) else '',
            bool(_payload_is_service_line(item)),
            _to_decimal(item.get('quantity', 0)),
            _to_decimal(item.get('unit_price', 0)),
            _to_decimal(item.get('discount_percent', 0)),
        ))
    return sorted(signature)


def _order_items_payload_from_order(order):
    """Chuyển item hiện có thành payload để các cập nhật một phần không làm rỗng đơn."""
    return [{
        'product_id': item.product_id,
        'variant_id': item.variant_id,
        'item_name': item.item_name or '',
        'unit': item.unit or '',
        'is_service_line': bool(item.is_service_line or not item.product_id),
        'quantity': item.quantity,
        'unit_price': item.unit_price,
        'discount_percent': item.discount_percent,
    } for item in order.items.all()]


def _payload_requests_new_receipt(data):
    """Kiểm tra payload có đang yêu cầu tạo thêm phiếu thu hay không."""
    payment_lines = data.get('payment_lines') or []
    for line in payment_lines:
        if _to_decimal(line.get('amount', 0)) > 0:
            return True
    return _to_decimal(data.get('payment_amount', 0)) > 0


def _get_receipted_order_blocking_changes(order, data):
    """Liệt kê các thay đổi không được phép khi đơn đã phát sinh phiếu thu."""
    changes = []

    if 'code' in data and (data.get('code') or '').strip() != order.code:
        changes.append('mã đơn')

    if 'customer_id' in data:
        current_customer_id = None if _is_guest_customer(order.customer) else order.customer_id
        if _normalize_optional_int(data.get('customer_id')) != current_customer_id:
            changes.append('khách hàng')

    if 'warehouse_id' in data and _normalize_optional_int(data.get('warehouse_id')) != order.warehouse_id:
        changes.append('kho xuất')

    if 'order_date' in data:
        current_date = order.order_date.isoformat() if order.order_date else ''
        if (data.get('order_date') or '') != current_date:
            changes.append('ngày đặt')

    for field_name, label in (
        ('discount_amount', 'chiết khấu'),
        ('shipping_fee', 'phí vận chuyển'),
        ('bonus_amount', 'tiền bonus'),
    ):
        if field_name in data and _to_decimal(data.get(field_name, 0)) != _to_decimal(getattr(order, field_name, 0)):
            changes.append(label)

    if 'approver_id' in data and _normalize_optional_int(data.get('approver_id')) != order.approver_id:
        changes.append('người duyệt')

    if 'items' in data:
        current_items = _order_item_signature_from_queryset(order.items.all())
        incoming_items = _order_item_signature_from_payload(data.get('items') or [])
        if incoming_items != current_items:
            changes.append('sản phẩm/giá/số lượng')

    if _payload_requests_new_receipt(data):
        changes.append('thanh toán mới')

    return changes


def _save_receipted_order_safe_update(request, order, data, old_status):
    """Cập nhật phần an toàn của đơn đã có phiếu thu mà không đụng tiền/hàng."""
    if old_status in (5, 6):
        return JsonResponse({
            'status': 'error',
            'message': 'Không thể sửa đơn hàng đã Hoàn thành/Hủy. Vui lòng dùng chức năng hoàn hàng/hoàn tiền nếu cần xử lý sau bán.'
        })

    new_status = int(data.get('status', old_status))
    allowed = ORDER_STATUS_TRANSITIONS.get(old_status, {old_status})
    if new_status not in allowed:
        return JsonResponse({
            'status': 'error',
            'message': f'Không được chuyển trạng thái từ "{Order.STATUS_CHOICES[old_status][1]}" sang "{Order.STATUS_CHOICES[new_status][1]}". '
            f'Chỉ cho phép: {", ".join(Order.STATUS_CHOICES[s][1] for s in sorted(allowed) if s != old_status) or "Không chuyển được"}.'
        })

    if new_status == 6:
        return JsonResponse({
            'status': 'error',
            'message': 'Đơn đã có phiếu thu. Vui lòng dùng chức năng Hủy đơn để hệ thống xử lý phiếu thu và tồn kho đúng quy trình.'
        })
    if new_status == 5:
        _refresh_order_payment(order)
        if not _order_can_complete(order, exported_status=old_status):
            return JsonResponse({
                'status': 'error',
                'message': _completion_block_message(order, exported_status=old_status)
            })

    blocking_changes = _get_receipted_order_blocking_changes(order, data)
    if blocking_changes:
        return JsonResponse({
            'status': 'error',
            'message': 'Đơn hàng đã có phiếu thu, chỉ được đổi trạng thái/ghi chú. Không thể thay đổi: '
            + ', '.join(blocking_changes) + '.'
        })

    status_after = new_status
    if status_after == 5 and order.approver_id and order.approval_status != 2:
        status_after = old_status

    update_fields = []
    if order.status != status_after:
        order.status = status_after
        update_fields.append('status')
    if 'note' in data and order.note != data.get('note', ''):
        order.note = data.get('note', '')
        update_fields.append('note')
    if 'tags' in data:
        tags = (data.get('tags', '') or '').strip() or None
        if order.tags != tags:
            order.tags = tags
            update_fields.append('tags')
    if 'salesperson' in data:
        salesperson = data.get('salesperson', '') or None
        if order.salesperson != salesperson:
            order.salesperson = salesperson
            update_fields.append('salesperson')
    if 'server_staff' in data:
        server_staff = data.get('server_staff', '') or None
        if order.server_staff != server_staff:
            order.server_staff = server_staff
            update_fields.append('server_staff')

    if update_fields:
        order.save(update_fields=update_fields)

    _sync_order_quotation_status(order, old_quotation_id=order.quotation_id)
    _refresh_order_payment(order)
    _log_order_history(
        order=order,
        actor=request.user,
        action='status',
        summary='Cập nhật trạng thái đơn đã có phiếu thu; không thay đổi tiền hàng.',
        status_before=old_status,
        status_after=order.status,
    )

    message = 'Đã cập nhật trạng thái đơn hàng'
    if new_status == 5 and status_after != 5:
        message = 'Đơn hàng cần được duyệt trước khi chuyển Hoàn thành.'
    return JsonResponse({
        'status': 'ok',
        'message': message,
        'order_id': order.id,
        'order_code': order.code,
        'order_status': order.status,
        'order_status_display': order.get_status_display(),
        'payment_status': order.payment_status,
        'payment_status_display': order.get_payment_status_display(),
        'paid_amount': float(order.paid_amount or 0),
    })


def _apply_order_stock_adjustment(order, direction, warehouse_id=None):
    """Áp biến động tồn kho cho toàn bộ item của đơn.

    - `direction = 1`: hoàn lại tồn kho
    - `direction = -1`: trừ tồn kho
    """
    warehouse_id = warehouse_id or order.warehouse_id
    if not warehouse_id:
        return

    from products.models import ComboItem
    allow_negative = True
    if _to_decimal(direction) < 0:
        allow_negative = _allow_negative_stock_for_store(order.store)

    for item in order.items.select_related('product').all():
        product = item.product
        if not product:
            continue
        quantity_delta = _to_decimal(item.quantity) * _to_decimal(direction)

        if product.is_combo:
            # Combo không trừ trực tiếp vào chính nó mà trừ/hoàn vào từng thành phần.
            for combo_item in ComboItem.objects.filter(combo_id=product.id).select_related('product'):
                if combo_item.product.is_service:
                    continue
                stock = _get_locked_stock(
                    product_id=combo_item.product_id,
                    warehouse_id=warehouse_id,
                )
                _adjust_locked_stock(
                    stock,
                    quantity_delta * _to_decimal(combo_item.quantity),
                    allow_negative=allow_negative,
                )
            continue

        if product.is_service:
            continue

        stock = _get_locked_stock(
            product_id=product.id,
            warehouse_id=warehouse_id,
        )
        _adjust_locked_stock(stock, quantity_delta, allow_negative=allow_negative)


def _cancel_auto_receipts_for_order(order, note_prefix):
    """Hủy toàn bộ phiếu thu tự động của đơn và trả về các phiếu thu thủ công còn lại."""
    linked_receipts = Receipt.objects.filter(order=order)
    auto_receipts = linked_receipts.filter(description__icontains='tự động')

    for receipt in auto_receipts:
        cancel_receipt_with_effect(receipt, note_prefix=note_prefix)

    return linked_receipts.exclude(description__icontains='tự động')


def _sync_order_quotation_status(order, old_quotation_id=None):
    """Đồng bộ trạng thái báo giá theo báo giá đang gắn với đơn sau khi lưu/hủy/xóa."""
    if order.status != 6 and order.quotation_id:
        _mark_quotation_as_used(order.quotation_id)

    if old_quotation_id and (old_quotation_id != order.quotation_id or order.status == 6):
        _reopen_quotation_if_unused(old_quotation_id, exclude_order_id=order.id)

    if order.status == 6 and order.quotation_id and order.quotation_id != old_quotation_id:
        _reopen_quotation_if_unused(order.quotation_id, exclude_order_id=order.id)


@login_required(login_url="/login/")
@brand_owner_required
def order_tbl(request):
    from core.store_utils import get_managed_store_ids
    store_ids = get_managed_store_ids(request.user)
    customers = list(_get_sales_customers_queryset(request).values('id', 'code', 'name', 'phone'))
    warehouses = list(Warehouse.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'name'))
    cashbooks = list(CashBook.objects.filter(is_active=True).values('id', 'name'))
    payment_methods = list(PaymentMethodOption.objects.filter(is_active=True).values(
        'id', 'name', 'default_cash_book_id', 'default_cash_book__name', 'legacy_type'
    ))
    # Báo giá chưa hủy VÀ chưa tạo đơn hàng (hoặc đơn hàng đã hủy)
    # Lấy ID báo giá đã có đơn hàng chưa hủy
    used_quotation_ids = Order.objects.exclude(status=6).exclude(
        quotation_id__isnull=True
    ).values_list('quotation_id', flat=True)
    quotations = list(Quotation.objects.select_related('customer').filter(
        store_id__in=store_ids
    ).exclude(
        status__in=[3, 4]  # Loại bỏ báo giá đã tạo ĐH hoặc đã hủy
    ).exclude(
        id__in=used_quotation_ids  # Loại bỏ báo giá đã có đơn hàng liên kết
    ).values('id', 'code', 'customer__name', 'final_amount', 'status').order_by('-quotation_date'))
    # Danh sách user cho dropdown "Người duyệt" — chỉ lấy user thuộc cùng thương hiệu
    from django.contrib.auth.models import User as AuthUser
    brand_users = AuthUser.objects.filter(
        is_active=True,
        profile__store_id__in=store_ids
    ).distinct().order_by('last_name', 'first_name')
    system_users = [
        {'id': u.id, 'full_name': u.get_full_name() or u.username}
        for u in brand_users
    ]
    from customers.models import CustomerGroup
    customer_groups = list(CustomerGroup.objects.filter(is_active=True).values('id', 'name').order_by('name'))
    context = {
        'active_tab': 'order_tbl',
        'customers': customers,
        'customer_groups': customer_groups,
        'warehouses': warehouses,
        'cashbooks': cashbooks,
        'payment_methods': payment_methods,
        'quotations': quotations,
        'system_users': system_users,
    }
    # Thêm cấu hình tồn âm
    try:
        from system_management.models import BusinessConfig
        from core.store_utils import get_owned_brands
        brands = get_owned_brands(request.user)
        config = BusinessConfig.get_config(brands.first() if brands.exists() else None)
        context['allow_negative_stock'] = config.opt_allow_negative_stock
    except Exception:
        context['allow_negative_stock'] = False
    return render(request, "orders/order_list.html", context)


@login_required(login_url="/login/")
def order_approvals(request):
    """Trang duyệt đơn hàng — cho người được gán làm approver"""
    context = {'active_tab': 'order_approvals'}
    return render(request, "orders/order_approvals.html", context)


@login_required(login_url="/login/")
def api_pending_approvals(request):
    """API lấy đơn hàng chờ duyệt của user đang đăng nhập"""
    user = request.user
    from core.store_utils import is_brand_owner

    # Lấy đơn chờ duyệt: approver = user hiện tại, hoặc brand owner thấy tất cả
    if is_brand_owner(user):
        pending = Order.objects.filter(approval_status=1).select_related('customer', 'approver')
        pending = filter_by_store(pending, request)
        # Đơn đã xử lý gần đây (duyệt/từ chối) trong 7 ngày
        from django.utils import timezone
        from datetime import timedelta
        recent_cutoff = timezone.now() - timedelta(days=7)
        processed = Order.objects.filter(
            approval_status__in=[2, 3],
            approved_at__gte=recent_cutoff
        ).select_related('customer', 'approver')
        processed = filter_by_store(processed, request)
    else:
        pending = Order.objects.filter(approver=user, approval_status=1).select_related('customer', 'approver')
        from django.utils import timezone
        from datetime import timedelta
        recent_cutoff = timezone.now() - timedelta(days=7)
        processed = Order.objects.filter(
            approver=user,
            approval_status__in=[2, 3],
            approved_at__gte=recent_cutoff
        ).select_related('customer', 'approver')

    def serialize(orders):
        return [{
            'id': o.id,
            'code': o.code,
            'customer': o.customer.name if o.customer else '',
            'order_date': o.order_date.strftime('%d/%m/%Y') if o.order_date else '',
            'final_amount': float(o.final_amount),
            'paid_amount': float(o.paid_amount),
            'status': o.status,
            'status_display': o.get_status_display(),
            'payment_status': o.payment_status,
            'payment_status_display': o.get_payment_status_display(),
            'approval_status': o.approval_status,
            'approval_status_display': o.get_approval_status_display(),
            'approved_at': o.approved_at.strftime('%d/%m/%Y %H:%M') if o.approved_at else '',
            'approver_name': o.approver.get_full_name() if o.approver else '',
            'creator_name': o.creator_name or '',
            'salesperson': o.salesperson or '',
            'note': o.note or '',
            'created_at': o.created_at.strftime('%d/%m/%Y %H:%M') if o.created_at else '',
        } for o in orders.order_by('-created_at')]

    return JsonResponse({
        'status': 'ok',
        'pending': serialize(pending),
        'pending_count': pending.count(),
        'processed': serialize(processed),
    })


@login_required(login_url="/login/")
@brand_owner_required
def quotation_tbl(request):
    from django.contrib.auth.models import User as AuthUser
    from core.store_utils import get_managed_store_ids
    store_ids = get_managed_store_ids(request.user)
    customers = list(_get_sales_customers_queryset(request).values('id', 'code', 'name', 'phone'))
    warehouses = list(Warehouse.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'name'))
    brand_users = AuthUser.objects.filter(
        is_active=True,
        profile__store_id__in=store_ids
    ).distinct().order_by('last_name', 'first_name')
    system_users = [
        {'id': u.id, 'full_name': u.get_full_name() or u.username}
        for u in brand_users
    ]
    from customers.models import CustomerGroup
    customer_groups = list(CustomerGroup.objects.filter(is_active=True).values('id', 'name').order_by('name'))
    context = {
        'active_tab': 'quotation_tbl',
        'customers': customers,
        'customer_groups': customer_groups,
        'system_users': system_users,
        'warehouses': warehouses,
    }
    return render(request, "orders/quotation_list.html", context)


@login_required(login_url="/login/")
@brand_owner_required
def order_return_tbl(request):
    payment_methods = list(PaymentMethodOption.objects.filter(is_active=True).values(
        'id', 'name', 'default_cash_book_id', 'default_cash_book__name', 'legacy_type'
    ))
    context = {
        'active_tab': 'order_return_tbl',
        'payment_methods': payment_methods,
    }
    return render(request, "orders/order_return_list.html", context)


@login_required(login_url="/login/")
@brand_owner_required
def packaging_tbl(request):
    orders = filter_by_store(Order.objects.exclude(status=6), request)
    orders = list(orders.values('id', 'code').order_by('-order_date'))
    context = {'active_tab': 'packaging_tbl', 'orders': orders}
    return render(request, "orders/packaging_list.html", context)


# ============ API: PRODUCTS for selection ============

@login_required(login_url="/login/")
def api_get_products_for_select(request):
    """Lấy danh sách SP cho ô chọn sản phẩm, kèm tồn kho theo từng kho"""
    products = Product.objects.filter(is_active=True).select_related('category').prefetch_related('stocks', 'variants', 'combo_items__product__stocks')
    products = filter_by_store(products, request)
    exclude_order_id = request.GET.get('exclude_order_id') or None
    reserved_by_product, total_reserved_by_product, pending_by_product, total_pending_by_product = _get_reserved_stock_maps(
        request,
        exclude_order_id=exclude_order_id,
    )
    data = []
    for p in products:
        # Tồn kho theo từng kho: {warehouse_id: quantity}
        stocks = {}
        reserved_stocks = {}
        pending_stocks = {}
        sellable_stocks = {}
        total_stock = 0
        for s in p.stocks.all():
            stocks[str(s.warehouse_id)] = float(s.quantity)
            total_stock += float(s.quantity)

        warehouse_keys = (
            set(stocks.keys()) |
            {str(wid) for wid in reserved_by_product[p.id].keys()} |
            {str(wid) for wid in pending_by_product[p.id].keys()}
        )
        for warehouse_key in warehouse_keys:
            actual_qty = float(stocks.get(warehouse_key, 0))
            reserved_qty = float(reserved_by_product[p.id].get(int(warehouse_key), 0))
            pending_qty = float(pending_by_product[p.id].get(int(warehouse_key), 0))
            reserved_stocks[warehouse_key] = reserved_qty
            pending_stocks[warehouse_key] = pending_qty
            sellable_stocks[warehouse_key] = actual_qty - reserved_qty

        # Variants
        variants = [{
            'id': v.id,
            'size_name': v.size_name,
            'sku': v.sku,
            'import_price': float(v.import_price),
            'cost_price': float(v.cost_price),
            'selling_price': float(v.selling_price),
        } for v in p.variants.filter(is_active=True)]

        # Combo items
        combo_items = []
        if p.is_combo:
            for ci in p.combo_items.select_related('product').all():
                ci_stocks = {}
                for s in ci.product.stocks.all():
                    ci_stocks[str(s.warehouse_id)] = float(s.quantity)
                combo_items.append({
                    'product_id': ci.product_id,
                    'product_name': ci.product.name,
                    'is_service': ci.product.is_service,
                    'quantity': float(ci.quantity),
                    'stocks': ci_stocks,
                })

        total_reserved_stock = float(total_reserved_by_product[p.id])
        total_pending_stock = float(total_pending_by_product[p.id])
        total_sellable_stock = float(total_stock - total_reserved_by_product[p.id])
        if p.is_combo:
            (
                stocks,
                reserved_stocks,
                pending_stocks,
                sellable_stocks,
                total_stock,
                total_reserved_stock,
                total_pending_stock,
                total_sellable_stock,
            ) = _get_combo_stock_maps(p, reserved_by_product, pending_by_product)

        data.append({
            'id': p.id,
            'code': p.code,
            'barcode': p.barcode or '',
            'name': p.name,
            'unit': p.unit,
            'image': p.image.url if p.image else '',
            'image_url': p.image.url if p.image else '',
            'category_id': p.category_id,
            'category_name': p.category.name if p.category else '',
            'selling_price': float(p.selling_price),
            'import_price': float(p.import_price),
            'cost_price': float(p.cost_price),
            'price': float(p.selling_price),
            'is_weight_based': p.is_weight_based,
            'is_service': p.is_service,
            'is_combo': p.is_combo,
            'combo_items': combo_items,
            'stocks': stocks,
            'reserved_stocks': reserved_stocks,
            'pending_stocks': pending_stocks,
            'sellable_stocks': sellable_stocks,
            'total_stock': float(total_stock),
            'total_reserved_stock': float(total_reserved_stock),
            'total_pending_stock': float(total_pending_stock),
            'total_sellable_stock': float(total_sellable_stock),
            'variants': variants,
        })
    return JsonResponse({'data': data})


# ============ API: CODE GENERATION ============

def _auto_next_order_code():
    """Internal helper: sinh mã đơn hàng tiếp theo, tránh trùng cả soft-delete.
    Luôn tăng tiến, không bao giờ tái sử dụng mã đã hủy/xóa (giống Sapo).
    """
    prefix = 'DH-'
    # Tìm số lớn nhất hiện có trong TẤT CẢ orders (kể cả soft-delete)
    max_num = 0
    for code in Order.all_objects.filter(code__startswith=prefix).values_list('code', flat=True):
        match = re.search(r'DH-(\d+)', code)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num
    next_num = max_num + 1
    code = f'{prefix}{next_num:03d}'
    return code


@login_required(login_url="/login/")
def api_next_order_code(request):
    """Sinh mã đơn hàng tiếp theo: DH-001, DH-002, ... (luôn tăng tiến, không tái sử dụng)"""
    code = _auto_next_order_code()
    return JsonResponse({'code': code})


@login_required(login_url="/login/")
def api_next_quotation_code(request):
    """Sinh mã báo giá tiếp theo: BG-001, BG-002, ... (luôn tăng tiến)"""
    prefix = 'BG-'
    max_num = 0
    for code in Quotation.all_objects.filter(code__startswith=prefix).values_list('code', flat=True):
        match = re.search(r'BG-(\d+)', code)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num
    next_num = max_num + 1
    code = f'{prefix}{next_num:03d}'
    return JsonResponse({'code': code})

# ============ API: QUICK CREATE CUSTOMER ============


@login_required(login_url="/login/")
def api_quick_create_customer(request):
    """Tạo nhanh khách hàng từ form đơn hàng"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        phone = data.get('phone', '').strip()
        if not name:
            return JsonResponse({'status': 'error', 'message': 'Vui lòng nhập tên khách hàng'})

        existing_customer = None
        if phone:
            existing_customer = _get_sales_customers_queryset(request).filter(phone=phone).first()
        if existing_customer:
            return JsonResponse({
                'status': 'ok',
                'message': f'Khách hàng {existing_customer.name} đã tồn tại, đã chọn lại.',
                'customer': {
                    'id': existing_customer.id,
                    'code': existing_customer.code,
                    'name': existing_customer.name,
                    'phone': existing_customer.phone or '',
                }
            })

        # Tự sinh mã khách hàng
        import re
        prefix = 'KH'
        last_cust = Customer.all_objects.filter(code__startswith=prefix).exclude(
            code__startswith=GUEST_CUSTOMER_CODE_PREFIX
        ).order_by('-id').first()
        next_num = 1
        if last_cust:
            match = re.search(r'KH(\d+)', last_cust.code)
            if match:
                next_num = int(match.group(1)) + 1
        while True:
            cust_code = f'{prefix}{next_num:03d}'
            if not Customer.all_objects.filter(code=cust_code).exists():
                break
            next_num += 1

        c = Customer()
        c.code = cust_code
        c.name = name
        c.phone = phone
        c.email = data.get('email', '').strip()
        c.address = data.get('address', '').strip()
        c.company = data.get('company', '').strip()
        c.created_by = request.user
        c.store = _get_default_store_for_request(request)
        group_id = data.get('group_id')
        if group_id:
            c.group_id = group_id
        note = data.get('note', '').strip()
        if note:
            c.note = note
        c.save()

        return JsonResponse({
            'status': 'ok',
            'message': f'Tạo khách hàng {c.name} thành công!',
            'customer': {
                'id': c.id,
                'code': c.code,
                'name': c.name,
                'phone': c.phone or '',
            }
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: ORDER ============

@login_required(login_url="/login/")
def api_get_orders(request):
    active_receipts = Receipt.objects.select_related('payment_method_option').filter(status=1)
    orders = Order.objects.select_related(
        'customer', 'customer__group', 'warehouse', 'created_by', 'approver'
    ).prefetch_related(
        'items__product',
        Prefetch('receipts', queryset=active_receipts, to_attr='active_receipts'),
    ).all()
    orders = filter_by_store(orders, request)
    data = []
    for o in orders:
        receipts = list(getattr(o, 'active_receipts', []))
        payment_method_names = sorted({
            r.get_payment_method_label()
            for r in receipts
            if r.get_payment_method_label()
        })
        items = list(o.items.all())
        product_labels = []
        product_search_parts = []
        product_ids = []
        for item in items:
            product = item.product
            if not product:
                if item.item_name:
                    product_labels.append(item.item_name)
                    product_search_parts.extend([item.item_name, item.unit or '', 'dịch vụ', 'service'])
                continue
            product_ids.append(product.id)
            label = ' - '.join(part for part in [product.code, product.name] if part)
            if label:
                product_labels.append(label)
            product_search_parts.extend([
                str(product.id),
                product.code or '',
                product.name or '',
                getattr(product, 'barcode', '') or '',
            ])
        creator_display = o.creator_name or ''
        if not creator_display and o.created_by:
            creator_display = o.created_by.get_full_name() or o.created_by.username
        data.append({
            'id': o.id, 'code': o.code,
            'customer': o.customer.name if o.customer else GUEST_CUSTOMER_NAME,
            'customer_id': o.customer_id,
            'customer_phone': o.customer.phone if o.customer and o.customer.phone else '',
            'warehouse': o.warehouse.name if o.warehouse else '',
            'warehouse_id': o.warehouse_id,
            'order_date': o.order_date.strftime('%Y-%m-%d') if o.order_date else '',
            'created_date': o.created_at.strftime('%Y-%m-%d') if o.created_at else '',
            'created_at': o.created_at.strftime('%d/%m/%Y %H:%M:%S') if o.created_at else '',
            'total_amount': float(o.total_amount),
            'discount_amount': float(o.discount_amount),
            'shipping_fee': float(getattr(o, 'shipping_fee', 0) or 0),
            'final_amount': float(o.final_amount),
            'paid_amount': float(o.paid_amount),
            'remaining_amount': max(float(o.final_amount) - float(o.paid_amount), 0),
            'status': o.status, 'status_display': o.get_status_display(),
            'payment_status': o.payment_status,
            'payment_status_display': o.get_payment_status_display(),
            'payment_method_option_ids': [
                r.payment_method_option_id for r in receipts if r.payment_method_option_id
            ],
            'payment_method_names': payment_method_names,
            'payment_method_display': ', '.join(payment_method_names),
            'has_receipt': bool(receipts),
            'receipt_count': len(receipts),
            'tags': o.tags or '',
            'note': o.note or '',
            'customer_group': o.customer.group.name if o.customer and o.customer.group else '',
            'customer_group_id': o.customer.group_id if o.customer else None,
            'creator_id': o.created_by_id,
            'creator_name': creator_display,
            'salesperson': o.salesperson or '',
            'server_staff': o.server_staff or '',
            'product_ids': product_ids,
            'product_names': product_labels,
            'product_display': ', '.join(product_labels[:3]) + ('...' if len(product_labels) > 3 else ''),
            'product_search': ' '.join(product_search_parts),
            'approver_id': o.approver_id,
            'approver_name': o.approver.get_full_name() if o.approver else '',
            'approval_status': o.approval_status,
            'approval_status_display': o.get_approval_status_display(),
            'approved_at': o.approved_at.strftime('%d/%m/%Y %H:%M') if o.approved_at else '',
            'bonus_amount': float(o.bonus_amount),
        })
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_get_order_detail(request):
    """Lấy chi tiết đơn hàng bao gồm items"""
    oid = request.GET.get('id')
    if not oid:
        return JsonResponse({'status': 'error', 'message': 'Missing id'})
    try:
        o = _get_order_for_user(
            request,
            oid,
            queryset=Order.objects.select_related('customer', 'warehouse'),
        )
        if not o:
            raise Order.DoesNotExist
        items = []
        for it in o.items.select_related('product', 'variant').all():
            product = it.product
            items.append({
                'product_id': it.product_id,
                'variant_id': it.variant_id,
                'product_code': _item_display_code(it),
                'product_name': _item_display_name(it),
                'variant_name': it.variant.size_name if it.variant else '',
                'unit': _item_display_unit(it),
                'image_url': product.image.url if product and product.image else '',
                'is_service_line': bool(it.is_service_line or not product),
                'item_name': it.item_name or '',
                'quantity': float(it.quantity),
                'unit_price': float(it.unit_price),
                'discount_percent': float(it.discount_percent),
                'total_price': float(it.total_price),
            })
        return JsonResponse({
            'status': 'ok',
            'order': {
                'id': o.id,
                'code': o.code,
                'customer_id': None if _is_guest_customer(o.customer) else o.customer_id,
                'customer_label': o.customer.name if o.customer else GUEST_CUSTOMER_NAME,
                'warehouse_id': o.warehouse_id,
                'order_date': o.order_date.strftime('%Y-%m-%d') if o.order_date else '',
                'total_amount': float(o.total_amount),
                'discount_amount': float(o.discount_amount),
                'shipping_fee': float(getattr(o, 'shipping_fee', 0) or 0),
                'final_amount': float(o.final_amount),
                'status': o.status, 'note': o.note or '',
                'tags': o.tags or '',
                'payment_status': o.payment_status,
                'paid_amount': float(o.paid_amount),
                'creator_name': o.creator_name or '',
                'salesperson': o.salesperson or '',
                'server_staff': o.server_staff or '',
                'approver_id': o.approver_id,
                'approver_name': o.approver.get_full_name() if o.approver else '',
                'approval_status': o.approval_status,
                'approval_status_display': o.get_approval_status_display(),
                'approved_at': o.approved_at.strftime('%d/%m/%Y %H:%M') if o.approved_at else '',
                'bonus_amount': float(o.bonus_amount),
            },
            'items': items,
        })
    except Order.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy'})


@login_required(login_url="/login/")
def api_save_order(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            # 1. Xác định đây là luồng tạo mới hay cập nhật đơn hiện có.
            oid = data.get('id')
            old_status = None
            old_quotation_id = None
            old_warehouse_id = None
            history_action = 'update' if oid else 'create'
            if oid:
                o = _get_order_for_user(request, oid)
                if not o:
                    return JsonResponse({'status': 'error', 'message': 'Không tìm thấy đơn hàng'})
                old_status = o.status
                old_quotation_id = o.quotation_id
                old_warehouse_id = o.warehouse_id
                # KHÓA: Không cho sửa đơn hàng đã Hoàn thành hoặc Hủy
                if old_status in (5, 6):
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Không thể sửa đơn hàng đã Hoàn thành/Hủy. Vui lòng dùng chức năng hoàn hàng/hoàn tiền nếu cần xử lý sau bán.'
                    })
            else:
                o = Order()
                o.created_by = request.user
                if not o.store_id:
                    o.store = _get_default_store_for_request(request)

            # 2. Chuẩn hóa mã đơn và báo giá liên kết trước khi ghi vào model.
            requested_code = (data.get('code', o.code if oid else '') or '').strip()
            if not requested_code:
                requested_code = _auto_next_order_code()
            # Kiểm tra trùng mã (kể cả record đã soft-delete)
            dup = Order.all_objects.filter(code=requested_code)
            if oid:
                dup = dup.exclude(id=oid)
            if dup.exists():
                # Auto-generate next available code instead of rejecting
                requested_code = _auto_next_order_code()
            o.code = requested_code
            if 'quotation_id' in data:
                requested_quotation_id = data.get('quotation_id') or None
            else:
                requested_quotation_id = o.quotation_id if oid else None
            quotation = None if 'quotation_id' in data else (o.quotation if oid else None)
            if requested_quotation_id:
                quotation = _get_quotation_for_user(request, requested_quotation_id)
                if not quotation:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Báo giá không tồn tại hoặc không thuộc phạm vi cửa hàng của bạn.'
                    })

            # 3. Gán dữ liệu đầu vào đã được kiểm tra vào đối tượng đơn hàng.
            if 'customer_id' in data or not oid:
                o.customer = _resolve_sale_customer(request, data.get('customer_id'))
            requested_warehouse_id = data.get('warehouse_id') if 'warehouse_id' in data else (o.warehouse_id if oid else None)
            requested_warehouse_id = requested_warehouse_id or None
            warehouse = None if 'warehouse_id' in data else (o.warehouse if oid else None)
            if requested_warehouse_id:
                warehouse = _get_warehouse_for_user(request, requested_warehouse_id)
            if requested_warehouse_id and not warehouse:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Kho xuất không tồn tại hoặc không thuộc phạm vi cửa hàng của bạn.'
                })
            o.warehouse = warehouse
            o.quotation = quotation
            if 'order_date' in data or not oid:
                o.order_date = data.get('order_date')
            o.discount_amount = _non_negative_decimal(data.get('discount_amount', o.discount_amount if oid else 0))
            o.shipping_fee = _non_negative_decimal(data.get('shipping_fee', o.shipping_fee if oid else 0))
            if 'tags' in data or not oid:
                o.tags = (data.get('tags', '') or '').strip() or None
            new_status = int(data.get('status', o.status if oid else 0))

            # 4. Chặn nhảy trạng thái sai quy trình để tránh làm lệch nghiệp vụ.
            if oid and old_status is not None:
                allowed = ORDER_STATUS_TRANSITIONS.get(old_status, {old_status})
                if new_status not in allowed:
                    status_labels = dict(Order.STATUS_CHOICES)
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Không được chuyển trạng thái từ "{status_labels.get(old_status, old_status)}" sang "{status_labels.get(new_status, new_status)}". '
                        f'Chỉ cho phép: {", ".join(status_labels.get(s, str(s)) for s in sorted(allowed) if s != old_status) or "Không chuyển được"}.'
                    })
                if new_status == 6:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Vui lòng dùng nút Hủy đơn để hệ thống hoàn tồn kho và xử lý phiếu thu đúng quy trình.'
                    })
            o.status = new_status
            if 'note' in data or not oid:
                o.note = data.get('note', '')

            # Thông tin nhân sự
            o.creator_name = request.user.get_full_name() or request.user.username
            # NV bán hàng: nếu có quotation thì tự lấy từ người tạo báo giá
            if 'salesperson' in data or (not oid and quotation):
                sp = data.get('salesperson', '')
                if not sp and quotation:
                    sp = quotation.salesperson or (quotation.created_by.get_full_name() if quotation.created_by else '')
                o.salesperson = sp or None
            if 'server_staff' in data or not oid:
                o.server_staff = data.get('server_staff', '') or None
            if 'approver_id' in data or not oid:
                new_approver_id = data.get('approver_id') or None
                approver = _get_approver_for_user(request, new_approver_id) if new_approver_id else None
                if new_approver_id and not approver:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Người duyệt không thuộc phạm vi cửa hàng của bạn.'
                    })
                o.approver = approver
                # Xác định approval_status dựa trên có/không người duyệt
                if new_approver_id:
                    # Có người duyệt → cần duyệt (nếu chưa duyệt)
                    if o.approval_status not in (2, 3):  # Chưa duyệt/từ chối → chờ duyệt
                        o.approval_status = 1  # Chờ duyệt
                else:
                    o.approval_status = 0  # Không cần duyệt
            o.bonus_amount = _non_negative_decimal(data.get('bonus_amount', o.bonus_amount if oid else 0))

            # 5. Tính tổng tiền từ danh sách item đã gửi lên.
            items_data = data.get('items')
            if items_data is None:
                items_data = _order_items_payload_from_order(o) if oid else []
            _validate_unique_line_items(items_data)
            normalized_items = []
            for item_data in items_data:
                if _payload_is_service_line(item_data):
                    service_name = _payload_service_name(item_data)
                    if not service_name:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Vui lòng nhập tên dịch vụ/thẻ trống.'
                        })
                    normalized_items.append((item_data, None, None))
                    continue
                product = _get_product_for_user(request, item_data.get('product_id'))
                if not product:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Có sản phẩm không tồn tại hoặc không thuộc cửa hàng hiện tại.'
                    })

                variant_id = item_data.get('variant_id') or None
                variant = _get_variant_for_product(product, variant_id) if variant_id else None
                if variant_id and not variant:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Biến thể không thuộc sản phẩm "{product.name}".'
                    })
                normalized_items.append((item_data, product, variant))

            try:
                o.store, o.customer = _resolve_sales_record_store(
                    request,
                    o.customer,
                    warehouse,
                    [product for _, product, _ in normalized_items if product],
                    current_store=o.store,
                )
            except ValueError as e:
                return JsonResponse({'status': 'error', 'message': str(e)})

            total = Decimal('0')
            for item_data in items_data:
                total += _calculate_line_total(
                    item_data.get('quantity', 0),
                    item_data.get('unit_price', 0),
                    item_data.get('discount_percent', 0),
                )

            o.total_amount = total
            o.final_amount = _calculate_final_amount(total, o.discount_amount, o.shipping_fee)
            order_discount_ratio = Decimal('0')
            if total > 0 and _to_decimal(o.discount_amount) > 0:
                order_discount_ratio = min(_to_decimal(o.discount_amount) / total, Decimal('1'))

            # 6. Dự phóng thanh toán trước khi lưu trạng thái cuối để tránh chốt sai quy trình.
            existing_paid = sum(
                _to_decimal(rec.amount)
                for rec in Receipt.objects.filter(order=o, status=1)
            ) if oid else Decimal('0')
            receipt_items = _build_receipt_items_from_payload(data, o, float(existing_paid))
            projected_paid = existing_paid + sum(
                (_to_decimal(ri.get('amount', 0)) for ri in receipt_items),
                Decimal('0'),
            )
            projected_payment_status = _project_payment_status(o, projected_paid)
            completion_base_status = old_status if oid else None
            if new_status == 5 and not _order_can_complete(
                o,
                payment_status=projected_payment_status,
                exported_status=completion_base_status,
            ):
                return JsonResponse({
                    'status': 'error',
                    'message': _completion_block_message(
                        o,
                        payment_status=projected_payment_status,
                        exported_status=completion_base_status,
                    )
                })

            try:
                o.save()
            except IntegrityError:
                if oid:
                    raise
                o.code = _auto_next_order_code()
                o.save()

            for idx, ri in enumerate(receipt_items):
                base_code = f'PT-{o.code}' if idx == 0 else f'PT-{o.code}-{idx + 1}'
                _create_completed_receipt_for_order(
                    order=o,
                    actor=request.user,
                    amount=ri['amount'],
                    payment_method=ri['payment_method'],
                    payment_method_option_id=ri.get('payment_method_option_id'),
                    cash_book_id=ri.get('cash_book_id'),
                    base_code=base_code,
                    description_suffix='tự động',
                )

            # Cập nhật paid trên order (luôn tính từ phiếu thu thực tế)
            _refresh_order_payment(o)

            # 7. Nếu đơn đã xuất kho trước đó, hoàn tồn cũ trước khi ghi lại dòng hàng mới.
            if _order_exports_stock_status(old_status) and old_warehouse_id:
                _apply_order_stock_adjustment(o, direction=1, warehouse_id=old_warehouse_id)

            # 8. Ghi lại danh sách item mới và tính cảnh báo bán thấp hơn giá vốn.
            o.items.all().delete()
            loss_warnings = []
            for item_data, product, variant in normalized_items:
                qty = _non_negative_decimal(item_data.get('quantity', 0))
                price = _non_negative_decimal(item_data.get('unit_price', 0))
                disc = _normalize_percentage(item_data.get('discount_percent', 0))
                line_total = _calculate_line_total(qty, price, disc)
                variant_id = variant.id if variant else None
                cost = Decimal('0')
                is_below_cost = False
                if product:
                    cost = Decimal(str(product.cost_price or 0))
                    fallback_cost = Decimal(str(product.import_price or 0))
                    if variant:
                        cost = Decimal(str(variant.cost_price or 0))
                        fallback_cost = Decimal(str(variant.import_price or 0))
                    compare_cost = cost if cost > 0 else fallback_cost
                    unit_after_line_discount = price * (Decimal('1') - disc / Decimal('100'))
                    unit_after_order_discount = unit_after_line_discount * (Decimal('1') - order_discount_ratio)
                    is_below_cost = compare_cost > 0 and unit_after_order_discount < compare_cost
                else:
                    compare_cost = Decimal('0')
                if is_below_cost:
                    loss_warnings.append(
                        f'{product.code} - {product.name}: bán {int(unit_after_order_discount):,}đ < vốn {int(compare_cost):,}đ'
                    )
                OrderItem.objects.create(
                    order=o,
                    product=product,
                    variant_id=variant_id,
                    item_name=_payload_service_name(item_data) if not product else None,
                    unit=_payload_service_unit(item_data) if not product else None,
                    is_service_line=not bool(product),
                    quantity=qty,
                    unit_price=price,
                    cost_price=cost,
                    discount_percent=disc,
                    total_price=line_total,
                    is_below_listed=is_below_cost,
                )
            o.below_listed_price_warning = bool(loss_warnings)
            o.save(update_fields=['below_listed_price_warning'])

            # 9. Trừ tồn tại bước xuất kho. Nếu vừa thanh toán đủ, service có thể tự chốt Hoàn thành.
            if _order_exports_stock_status(o.status) and o.warehouse_id:
                _apply_order_stock_adjustment(o, direction=-1)

            # 10. Đồng bộ trạng thái báo giá sau khi trạng thái đơn đã ổn định.
            _sync_order_quotation_status(o, old_quotation_id=old_quotation_id)

            summary_parts = [
                f'Tổng thanh toán {int(float(o.final_amount or 0)):,}đ',
            ]
            if float(o.discount_amount or 0):
                summary_parts.append(f'chiết khấu {int(float(o.discount_amount)):,}đ')
            if float(o.shipping_fee or 0):
                summary_parts.append(f'phí vận chuyển {int(float(o.shipping_fee)):,}đ')
            if o.tags:
                summary_parts.append(f'tags: {o.tags}')
            if float(o.paid_amount or 0):
                summary_parts.append(f'đã thu {int(float(o.paid_amount)):,}đ')
            if loss_warnings:
                summary_parts.append('cảnh báo bán lỗ: ' + '; '.join(loss_warnings[:5]))
            _log_order_history(
                order=o,
                actor=request.user,
                action=history_action,
                summary='; '.join(summary_parts),
                status_before=old_status,
                status_after=o.status,
            )

        # Xây dựng message phản hồi
        msg = 'Lưu thành công'
        if o.approver_id and o.approval_status == 1:
            approver_name = o.approver.get_full_name() if o.approver else ''
            msg += f'. ⏳ Đơn hàng cần được {approver_name} duyệt trước khi hoàn thành.'
        if loss_warnings:
            msg += '. Cảnh báo bán dưới giá vốn: ' + '; '.join(loss_warnings[:5])
        return JsonResponse({
            'status': 'ok',
            'message': msg,
            'order_id': o.id,
            'order_code': o.code,
            'order_status': o.status,
            'order_status_display': o.get_status_display(),
            'payment_status': o.payment_status,
            'payment_status_display': o.get_payment_status_display(),
            'paid_amount': float(o.paid_amount or 0),
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_update_order_note(request):
    """Cập nhật ghi chú cho đơn chưa hủy; đơn hoàn thành vẫn được bổ sung ghi chú."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        order = _get_order_for_user(request, data.get('id'))
        if not order:
            raise Order.DoesNotExist
        if order.status == 6:
            return JsonResponse({
                'status': 'error',
                'message': 'Đơn hàng đã Hủy nên không thể chỉnh sửa ghi chú.'
            })
        old_note = order.note or ''
        order.note = data.get('note', '')
        order.save(update_fields=['note'])
        _log_order_history(
            order=order,
            actor=request.user,
            action='note',
            summary=f'Cập nhật ghi chú đơn hàng. Trước: "{old_note[:120]}"; Sau: "{(order.note or "")[:120]}"',
            status_before=order.status,
            status_after=order.status,
        )
        return JsonResponse({'status': 'ok', 'message': 'Lưu ghi chú thành công'})
    except Order.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy đơn hàng'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_order(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        order = _get_order_for_user(request, data.get('id'))
        if not order:
            raise Order.DoesNotExist
        # Không cho xóa các đơn đã chốt trạng thái cuối hoặc đã phát sinh dòng tiền.
        if order.status in (5, 6):
            return JsonResponse({
                'status': 'error',
                'message': 'Không thể xóa đơn hàng đã Hoàn thành/Hủy.'
            })
        if Receipt.objects.filter(order=order).exists():
            return JsonResponse({
                'status': 'error',
                'message': 'Không thể xóa đơn hàng đã có phiếu thu. Vui lòng xử lý phiếu thu hoặc hủy đơn hàng theo đúng quy trình.'
            })
        quotation_id = order.quotation_id
        order.delete()
        # Sau khi xóa mềm đơn, mở lại báo giá nếu nó không còn bị đơn nào khác chiếm dụng.
        _reopen_quotation_if_unused(quotation_id)
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Order.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy đơn hàng'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_cancel_order(request):
    """Hủy đơn hàng và hoàn lại tồn kho nếu đơn đã xuất kho."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        order_id = data.get('id')
        reason = data.get('reason', '')

        with transaction.atomic():
            # 1. Khóa đơn trong đúng phạm vi store người dùng được phép thao tác.
            order = _get_order_for_user(request, order_id)
            if not order:
                raise Order.DoesNotExist

            if order.status == 6:
                return JsonResponse({'status': 'error', 'message': 'Đơn hàng này đã bị hủy trước đó.'})

            if order.status not in (0, 1, 2, 3, 4, 5):
                return JsonResponse({'status': 'error', 'message': 'Chỉ có thể hủy báo giá/đơn hàng chưa bị hủy.'})

            # 2. Nếu đơn đã xuất kho thì phải hoàn tồn kho trước khi đổi trạng thái.
            if _order_exports_stock_status(order.status) and order.warehouse_id:
                _apply_order_stock_adjustment(order, direction=1)

            # 3. Hủy các phiếu thu tự động; phiếu thủ công chỉ cảnh báo để người dùng tự xử lý.
            receipt_warning = ''
            manual_receipts = _cancel_auto_receipts_for_order(
                order,
                note_prefix=f'[HỦY TỰ ĐỘNG] Đơn hàng {order.code} đã bị hủy.',
            )
            if manual_receipts.exists():
                codes = ', '.join([receipt.code for receipt in manual_receipts])
                receipt_warning = f' ⚠️ Có phiếu thu thủ công liên quan: {codes}. Vui lòng kiểm tra và xử lý.'

            # 4. Chuyển đơn sang Hủy và xóa trạng thái thanh toán đã tổng hợp trước đó.
            old_note = order.note or ''
            cancel_note = f"[HỦY] Lý do: {reason}" if reason else "[HỦY]"
            old_status = order.status
            order.status = 6
            order.payment_status = 0
            order.paid_amount = 0
            order.note = f"{cancel_note}\n{old_note}".strip() if old_note else cancel_note
            order.save()
            _sync_order_quotation_status(order, old_quotation_id=order.quotation_id)
            _log_order_history(
                order=order,
                actor=request.user,
                action='cancel',
                summary=f'Hủy đơn hàng. Lý do: {reason or "Không nhập lý do"}',
                status_before=old_status,
                status_after=order.status,
            )

        return JsonResponse({
            'status': 'ok',
            'message': f'Đã hủy đơn hàng {order.code}. Tồn kho đã được hoàn lại nếu đơn đã xuất kho.{receipt_warning}'
        })
    except Order.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy đơn hàng'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_approve_order(request):
    """API để người duyệt xác nhận / từ chối đơn hàng"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        order_id = data.get('id')
        action = data.get('action')  # 'approve' hoặc 'reject'
        note = data.get('note', '')

        with transaction.atomic():
            order = _get_order_for_user(request, order_id)
            if not order:
                raise Order.DoesNotExist

            # Kiểm tra quyền: chỉ người duyệt hoặc brand owner mới được duyệt
            from core.store_utils import is_brand_owner
            if order.approver_id != request.user.id and not is_brand_owner(request.user):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Bạn không có quyền duyệt đơn hàng này. Chỉ người duyệt được chỉ định mới có quyền.'
                })

            if order.approval_status not in (1,):  # Chỉ duyệt khi đang Chờ duyệt
                return JsonResponse({
                    'status': 'error',
                    'message': 'Đơn hàng không ở trạng thái chờ duyệt.'
                })

            from django.utils import timezone

            if action == 'approve':
                order.approval_status = 2  # Đã duyệt
                order.approved_at = timezone.now()
                old_status = order.status
                # Duyệt báo giá/tạo đơn chỉ đưa chứng từ sang trạng thái Đơn hàng.
                # Tồn kho thực tế chỉ trừ ở bước Xuất kho.
                if order.status == 0:
                    order.status = 1

                if note:
                    order.note = f"{order.note or ''}\n[DUYỆT] {note}".strip()
                order.save()
                _refresh_order_payment(order)
                _log_order_history(
                    order=order,
                    actor=request.user,
                    action='approve',
                    summary=f'Duyệt đơn hàng. {note or "Không có ghi chú duyệt"}',
                    status_before=old_status,
                    status_after=order.status,
                )

                return JsonResponse({
                    'status': 'ok',
                    'message': f'✅ Đã duyệt đơn hàng {order.code}. Đơn hàng đã chuyển sang trạng thái Đơn hàng.'
                })

            elif action == 'reject':
                old_status = order.status
                order.approval_status = 3  # Từ chối
                order.approved_at = timezone.now()
                if note:
                    order.note = f"{order.note or ''}\n[TỪ CHỐI] {note}".strip()
                order.save()
                _log_order_history(
                    order=order,
                    actor=request.user,
                    action='reject',
                    summary=f'Từ chối duyệt đơn hàng. {note or "Không có lý do"}',
                    status_before=old_status,
                    status_after=order.status,
                )
                return JsonResponse({
                    'status': 'ok',
                    'message': f'❌ Đã từ chối duyệt đơn hàng {order.code}.'
                })
            else:
                return JsonResponse({'status': 'error', 'message': 'Hành động không hợp lệ'})

    except Order.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy đơn hàng'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_get_order_history(request):
    order_id = request.GET.get('id')
    if not order_id:
        return JsonResponse({'status': 'error', 'message': 'Missing id'})

    order_qs = filter_by_store(Order.objects.filter(id=order_id), request)
    order = order_qs.first()
    if not order:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy đơn hàng'})

    rows = [{
        'id': entry.id,
        'action': entry.action,
        'action_display': entry.get_action_display(),
        'actor': entry.actor.get_full_name() or entry.actor.username if entry.actor else '',
        'summary': entry.summary or '',
        'status_before': entry.status_before,
        'status_after': entry.status_after,
        'created_at': entry.created_at.strftime('%d/%m/%Y %H:%M:%S') if entry.created_at else '',
    } for entry in order.history_entries.select_related('actor').all()]
    return JsonResponse({'status': 'ok', 'data': rows})


@login_required(login_url="/login/")
def api_bulk_cancel_orders(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        ids = data.get('ids') or []
        reason = (data.get('reason') or '').strip()
        if not ids:
            return JsonResponse({'status': 'error', 'message': 'Chưa chọn đơn hàng'})

        cancelled = []
        skipped = []
        with transaction.atomic():
            # Chỉ thao tác trên các đơn thuộc store user đang quản lý.
            orders = filter_by_store(
                Order.objects.filter(id__in=ids).prefetch_related('items', 'receipts'),
                request
            )
            for order in orders:
                if order.status == 6:
                    skipped.append(f'{order.code} (đã hủy)')
                    continue
                if order.status not in (0, 1, 2, 3, 4, 5):
                    skipped.append(f'{order.code} (không ở trạng thái được phép hủy)')
                    continue

                # Hoàn tồn cho các đơn đã xuất kho.
                if _order_exports_stock_status(order.status) and order.warehouse_id:
                    _apply_order_stock_adjustment(order, direction=1)

                # Chỉ hủy các phiếu thu sinh tự động từ luồng đơn hàng.
                _cancel_auto_receipts_for_order(
                    order,
                    note_prefix='[HỦY TỰ ĐỘNG] Hủy nhanh nhiều đơn.',
                )

                old_status = order.status
                order.status = 6
                order.payment_status = 0
                order.paid_amount = 0
                order.note = (f'[HỦY NHANH] {reason}\n{order.note or ""}').strip()
                order.save(update_fields=['status', 'payment_status', 'paid_amount', 'note'])
                _sync_order_quotation_status(order, old_quotation_id=order.quotation_id)
                _log_order_history(
                    order=order,
                    actor=request.user,
                    action='bulk_cancel',
                    summary=f'Hủy nhanh nhiều đơn. {reason or "Không nhập lý do"}',
                    status_before=old_status,
                    status_after=order.status,
                )
                cancelled.append(order.code)

        message = f'Đã hủy {len(cancelled)} đơn.'
        if skipped:
            message += ' Bỏ qua: ' + ', '.join(skipped[:8])
        return JsonResponse({'status': 'ok', 'message': message})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_bulk_collect_orders(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        ids = data.get('ids') or []
        payment_method = int(data.get('payment_method', 2) or 2)
        payment_method_option_id = data.get('payment_method_option_id') or None
        cash_book_id = data.get('cash_book_id') or None
        if not ids:
            return JsonResponse({'status': 'error', 'message': 'Chưa chọn đơn hàng'})

        selected_method = None
        if payment_method_option_id:
            selected_method = PaymentMethodOption.objects.select_related('default_cash_book').filter(
                id=payment_method_option_id,
                is_active=True
            ).first()
            if selected_method:
                payment_method = selected_method.legacy_type if selected_method.legacy_type in (1, 2) else 2
        cash_book = _get_cashbook_for_payment(payment_method, selected_method, cash_book_id)

        collected = []
        skipped = []
        total_collected = Decimal('0')
        with transaction.atomic():
            orders = list(filter_by_store(
                Order.objects.filter(id__in=ids).prefetch_related('receipts'),
                request
            ))
            payable_customer_ids = {
                order.customer_id
                for order in orders
                if order.status != 6 and (_to_decimal(order.final_amount) - sum(
                    (_to_decimal(rec.amount) for rec in Receipt.objects.filter(order=order, status=1)),
                    Decimal('0')
                )) > 0
            }
            if len(payable_customer_ids) > 1:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Chỉ thanh toán nhanh nhiều đơn của cùng một khách hàng.'
                })
            for order in orders:
                if order.status == 6:
                    skipped.append(f'{order.code} (đã hủy)')
                    continue
                paid_total = sum(
                    (_to_decimal(rec.amount) for rec in Receipt.objects.filter(order=order, status=1)),
                    Decimal('0')
                )
                remaining = _to_decimal(order.final_amount) - paid_total
                if remaining <= 0:
                    skipped.append(f'{order.code} (đã thanh toán đủ)')
                    continue

                old_status = order.status
                _create_completed_receipt_for_order(
                    order=order,
                    actor=request.user,
                    amount=remaining,
                    payment_method=payment_method,
                    payment_method_option_id=payment_method_option_id,
                    cash_book_id=cash_book.id if cash_book else None,
                    base_code=f'PT-{order.code}-BULK',
                    description_suffix='thanh toán nhanh',
                )

                _refresh_order_payment(order)
                _log_order_history(
                    order=order,
                    actor=request.user,
                    action='bulk_collect',
                    summary=f'Thanh toán nhanh {int(remaining):,}đ qua {cash_book.name if cash_book else "tài khoản mặc định"}',
                    status_before=old_status,
                    status_after=order.status,
                )
                total_collected += remaining
                collected.append(order.code)

        message = f'Đã thanh toán nhanh {len(collected)} đơn.'
        if total_collected:
            message += f' Tổng đã thu: {int(total_collected):,}đ.'
        if skipped:
            message += ' Bỏ qua: ' + ', '.join(skipped[:8])
        return JsonResponse({
            'status': 'ok',
            'message': message,
            'collected_count': len(collected),
            'total_collected': float(total_collected),
            'skipped_count': len(skipped),
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: QUOTATION ============

@login_required(login_url="/login/")
def api_get_quotations(request):
    quotes = Quotation.objects.select_related('customer', 'customer__group', 'created_by').prefetch_related('items__product').all()
    quotes = filter_by_store(quotes, request)
    data = []
    for q in quotes:
        product_labels = []
        product_search_parts = []
        for item in q.items.all():
            product = item.product
            if not product:
                if item.item_name:
                    product_labels.append(item.item_name)
                    product_search_parts.extend([item.item_name, item.unit or '', 'dịch vụ', 'service'])
                continue
            label = ' - '.join(part for part in [product.code, product.name] if part)
            if label:
                product_labels.append(label)
            product_search_parts.extend([
                str(product.id),
                product.code or '',
                product.name or '',
                getattr(product, 'barcode', '') or '',
            ])
        data.append({
            'id': q.id, 'code': q.code,
            'customer': q.customer.name if q.customer else GUEST_CUSTOMER_NAME,
            'customer_id': q.customer_id,
            'customer_phone': q.customer.phone if q.customer and q.customer.phone else '',
            'customer_group': q.customer.group.name if q.customer and q.customer.group else '',
            'customer_group_id': q.customer.group_id if q.customer else None,
            'quotation_date': q.quotation_date.strftime('%Y-%m-%d') if q.quotation_date else '',
            'valid_until': q.valid_until.strftime('%Y-%m-%d') if q.valid_until else '',
            'created_date': q.created_at.strftime('%Y-%m-%d') if q.created_at else '',
            'created_at': q.created_at.strftime('%d/%m/%Y %H:%M:%S') if q.created_at else '',
            'creator_id': q.created_by_id,
            'creator_name': (q.created_by.get_full_name() or q.created_by.username) if q.created_by else '',
            'product_names': product_labels,
            'product_display': ', '.join(product_labels[:3]) + ('...' if len(product_labels) > 3 else ''),
            'product_search': ' '.join(product_search_parts),
            'total_amount': float(q.total_amount),
            'discount_amount': float(q.discount_amount),
            'shipping_fee': float(getattr(q, 'shipping_fee', 0) or 0),
            'final_amount': float(q.final_amount),
            'status': q.status, 'status_display': q.get_status_display(),
            'tags': q.tags or '',
            'note': q.note or '',
            'salesperson': q.salesperson or '',
            'item_count': q.items.count(),
        })
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_get_quotation_detail(request):
    """Lấy chi tiết báo giá bao gồm items"""
    qid = request.GET.get('id')
    if not qid:
        return JsonResponse({'status': 'error', 'message': 'Missing id'})
    try:
        q = _get_quotation_for_user(request, qid)
        if not q:
            raise Quotation.DoesNotExist
        items = []
        for it in q.items.select_related('product', 'variant').all():
            product = it.product
            items.append({
                'product_id': it.product_id,
                'variant_id': it.variant_id,
                'product_code': _item_display_code(it),
                'product_name': _item_display_name(it),
                'variant_name': it.variant.size_name if it.variant else '',
                'unit': _item_display_unit(it),
                'image': product.image.url if product and product.image else '',
                'is_service_line': bool(it.is_service_line or not product),
                'item_name': it.item_name or '',
                'quantity': float(it.quantity),
                'unit_price': float(it.unit_price),
                'discount_percent': float(it.discount_percent),
                'total_price': float(it.total_price),
                'note': it.note or '',
            })
        return JsonResponse({
            'status': 'ok',
            'quotation': {
                'id': q.id,
                'code': q.code,
                'customer_id': None if _is_guest_customer(q.customer) else q.customer_id,
                'customer_label': q.customer.name if q.customer else GUEST_CUSTOMER_NAME,
                'quotation_date': q.quotation_date.strftime('%Y-%m-%d') if q.quotation_date else '',
                'valid_until': q.valid_until.strftime('%Y-%m-%d') if q.valid_until else '',
                'discount_amount': float(q.discount_amount),
                'shipping_fee': float(getattr(q, 'shipping_fee', 0) or 0),
                'status': q.status, 'note': q.note or '',
                'tags': q.tags or '',
                'salesperson': q.salesperson or '',
            },
            'items': items,
        })
    except Quotation.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy'})


@login_required(login_url="/login/")
def api_save_quotation(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            qid = data.get('id')
            old_status = None
            if qid:
                q = _get_quotation_for_user(request, qid)
                if not q:
                    return JsonResponse({'status': 'error', 'message': 'Không tìm thấy báo giá'})
                old_status = q.status
                new_status = int(data.get('status', q.status))
                if old_status in (3, 4):
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Không thể sửa báo giá đã tạo đơn hàng hoặc đã hủy.'
                    })
                if new_status not in (old_status, 4) and new_status < old_status:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Không được chuyển lùi trạng thái báo giá. Chỉ được đi tiếp hoặc hủy.'
                    })
                q.items.all().delete()
            else:
                q = Quotation()
                q.created_by = request.user
                q.store = _get_default_store_for_request(request)
            requested_code = (data.get('code', '') or '').strip()
            # Kiểm tra trùng mã (kể cả record đã soft-delete)
            dup = Quotation.all_objects.filter(code=requested_code)
            if qid:
                dup = dup.exclude(id=qid)
            if dup.exists():
                # Auto-generate next available code
                prefix = 'BG-'
                last_q = Quotation.all_objects.filter(code__startswith=prefix).order_by('-id').first()
                next_num = 1
                if last_q:
                    m = re.search(r'BG-(\d+)', last_q.code)
                    if m:
                        next_num = int(m.group(1)) + 1
                while True:
                    requested_code = f'{prefix}{next_num:03d}'
                    if not Quotation.all_objects.filter(code=requested_code).exists():
                        break
                    next_num += 1
            q.code = requested_code
            q.customer = _resolve_sale_customer(request, data.get('customer_id'))
            q.quotation_date = data.get('quotation_date')
            q.valid_until = data.get('valid_until') or None
            q.discount_amount = _non_negative_decimal(data.get('discount_amount', 0))
            q.shipping_fee = _non_negative_decimal(data.get('shipping_fee', 0))
            q.tags = (data.get('tags', '') or '').strip() or None
            q.status = data.get('status', 0)
            q.note = data.get('note', '')
            q.salesperson = data.get('salesperson', '') or (request.user.get_full_name() or request.user.username)

            # Tính tổng từ items
            items_data = data.get('items', [])
            _validate_unique_line_items(items_data)
            normalized_items = []
            for it in items_data:
                if _payload_is_service_line(it):
                    service_name = _payload_service_name(it)
                    if not service_name:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Vui lòng nhập tên dịch vụ/thẻ trống.'
                        })
                    normalized_items.append((it, None, None))
                    continue
                product = _get_product_for_user(request, it.get('product_id'))
                if not product:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Có sản phẩm không tồn tại hoặc không thuộc cửa hàng hiện tại.'
                    })
                variant_id = it.get('variant_id') or None
                variant = _get_variant_for_product(product, variant_id) if variant_id else None
                if variant_id and not variant:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Biến thể không thuộc sản phẩm "{product.name}".'
                    })
                normalized_items.append((it, product, variant))

            try:
                q.store, q.customer = _resolve_sales_record_store(
                    request,
                    q.customer,
                    None,
                    [product for _, product, _ in normalized_items if product],
                    current_store=q.store,
                )
            except ValueError as e:
                return JsonResponse({'status': 'error', 'message': str(e)})

            total = Decimal('0')
            for it in items_data:
                qty = _non_negative_decimal(it.get('quantity', 0))
                price = _non_negative_decimal(it.get('unit_price', 0))
                disc = _normalize_percentage(it.get('discount_percent', 0))
                line_total = _calculate_line_total(qty, price, disc)
                total += line_total

            q.total_amount = total
            q.final_amount = _calculate_final_amount(total, q.discount_amount, q.shipping_fee)
            quotation_discount_ratio = Decimal('0')
            if total > 0 and _to_decimal(q.discount_amount) > 0:
                quotation_discount_ratio = min(_to_decimal(q.discount_amount) / total, Decimal('1'))
            q.save()

            # Lưu items
            loss_warnings = []
            for it, product, variant in normalized_items:
                qty = _non_negative_decimal(it.get('quantity', 0))
                price = _non_negative_decimal(it.get('unit_price', 0))
                disc = _normalize_percentage(it.get('discount_percent', 0))
                line_total = _calculate_line_total(qty, price, disc)
                variant_id = variant.id if variant else None
                if product:
                    compare_cost = _to_decimal(product.cost_price or product.import_price or 0)
                    if variant:
                        compare_cost = _to_decimal(variant.cost_price or variant.import_price or compare_cost)
                    effective_unit_price = price * (Decimal('1') - disc / Decimal('100')) * (Decimal('1') - quotation_discount_ratio)
                    if compare_cost > 0 and effective_unit_price < compare_cost:
                        loss_warnings.append(
                            f'{product.code} - {product.name}: bán {int(effective_unit_price):,}đ < vốn {int(compare_cost):,}đ'
                        )
                QuotationItem.objects.create(
                    quotation=q,
                    product=product,
                    variant_id=variant_id,
                    item_name=_payload_service_name(it) if not product else None,
                    unit=_payload_service_unit(it) if not product else None,
                    is_service_line=not bool(product),
                    quantity=qty,
                    unit_price=price,
                    discount_percent=disc,
                    total_price=line_total,
                    note=it.get('note', ''),
                )

        message = 'Lưu thành công'
        if loss_warnings:
            message += '. Cảnh báo bán dưới giá vốn: ' + '; '.join(loss_warnings[:5])
        return JsonResponse({'status': 'ok', 'message': message, 'order_id': q.id, 'order_code': q.code})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_quotation(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        quotation = _get_quotation_for_user(request, data.get('id'))
        if not quotation:
            return JsonResponse({'status': 'error', 'message': 'Không tìm thấy báo giá'})
        quotation.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: ORDER RETURN ============

@login_required(login_url="/login/")
def api_get_order_returns(request):
    returns = OrderReturn.objects.select_related('order', 'customer', 'warehouse').all()
    returns = list(_filter_order_returns_by_scope(returns, request))
    refund_refs = [f'ORDER_RETURN:{r.id}' for r in returns]
    refund_payments = {
        payment.reference: payment
        for payment in Payment.all_objects.select_related('payment_method_option', 'cash_book').filter(
            reference__in=refund_refs
        )
    }
    data = []
    for r in returns:
        refund_payment = refund_payments.get(f'ORDER_RETURN:{r.id}')
        data.append({
            'id': r.id, 'code': r.code,
            'order': r.order.code if r.order else '(Thiếu đơn gốc)',
            'order_id': r.order_id,
            'customer': r.customer.name if r.customer else '',
            'customer_id': r.customer_id,
            'warehouse_id': r.warehouse_id,
            'return_date': r.return_date.strftime('%Y-%m-%d') if r.return_date else '',
            'created_at': r.created_at.strftime('%d/%m/%Y %H:%M:%S') if r.created_at else '',
            'total_refund': float(r.total_refund),
            'status': r.status, 'status_display': r.get_status_display(),
            'reason': r.reason or '',
            'payment_method': refund_payment.payment_method if refund_payment else 2,
            'payment_method_option_id': refund_payment.payment_method_option_id if refund_payment else None,
            'cash_book_id': refund_payment.cash_book_id if refund_payment else None,
            'refund_payment_code': refund_payment.code
            if refund_payment and not refund_payment.is_deleted else '',
        })
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_order_return(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        payment_method_option_id = data.get('payment_method_option_id') or None
        cash_book_id = data.get('cash_book_id') or None
        try:
            refund_payment_method = int(data.get('payment_method', 2) or 2)
        except (TypeError, ValueError):
            refund_payment_method = 2

        with transaction.atomic():
            rid = data.get('id')
            if rid:
                current_return = _filter_order_returns_by_scope(
                    OrderReturn.objects.filter(id=rid),
                    request,
                ).first()
                if not current_return:
                    return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phiếu trả hàng'})
                r = OrderReturn.objects.select_for_update().get(id=current_return.id)
            else:
                r = OrderReturn()
                r.created_by = request.user

            order_id = _normalize_optional_int(data.get('order_id'))
            order = None
            if order_id:
                order = _get_order_for_user(request, order_id)
                if not order:
                    return JsonResponse({'status': 'error', 'message': 'Đơn gốc không tồn tại hoặc không thuộc cửa hàng của bạn.'})
            elif r.order_id:
                order = _get_order_for_user(request, r.order_id)
                if not order:
                    return JsonResponse({'status': 'error', 'message': 'Đơn gốc không tồn tại hoặc không thuộc cửa hàng của bạn.'})
            else:
                return JsonResponse({'status': 'error', 'message': 'Vui lòng chọn đơn hàng gốc cho phiếu trả.'})
            if order.status != 5:
                return JsonResponse({'status': 'error', 'message': 'Chỉ tạo phiếu hoàn hàng/hoàn tiền cho đơn hàng đã Hoàn thành.'})

            status = _normalize_optional_int(data.get('status'))
            valid_statuses = {choice[0] for choice in OrderReturn.STATUS_CHOICES}
            if status is None:
                status = 0
            if status not in valid_statuses:
                return JsonResponse({'status': 'error', 'message': 'Trạng thái phiếu trả không hợp lệ.'})

            r.code = (data.get('code', '') or '').strip()
            if not r.code:
                return JsonResponse({'status': 'error', 'message': 'Mã phiếu không được để trống.'})
            r.order = order
            r.customer = order.customer
            r.warehouse = order.warehouse
            r.return_date = data.get('return_date')
            r.total_refund = data.get('total_refund', 0) or 0
            r.reason = data.get('reason', '')
            r.status = status
            r.save()

            refund_payment = _sync_refund_payment_for_return(
                r,
                request.user,
                payment_method_option_id=payment_method_option_id,
                payment_method=refund_payment_method,
                cash_book_id=cash_book_id,
            )

        message = 'Lưu thành công'
        response_data = {'status': 'ok', 'message': message}
        if r.status == 2 and _to_decimal(r.total_refund) > 0 and refund_payment:
            response_data.update({
                'message': f'Lưu thành công. Đã ghi phiếu chi hoàn tiền {refund_payment.code}.',
                'refund_payment_id': refund_payment.id,
                'refund_payment_code': refund_payment.code,
            })
        elif refund_payment and refund_payment.status == 2:
            response_data.update({
                'message': f'Lưu thành công. Đã hủy phiếu chi hoàn tiền {refund_payment.code}.',
                'refund_payment_id': refund_payment.id,
                'refund_payment_code': refund_payment.code,
            })
        return JsonResponse(response_data)
    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': str(e)})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: PACKAGING ============

@login_required(login_url="/login/")
def api_get_packagings(request):
    packs = Packaging.objects.select_related('order', 'packed_by').all()
    packs = filter_by_store(packs, request, field_name='order__store')
    data = [{
        'id': p.id, 'code': p.code,
        'order': p.order.code if p.order else '',
        'order_id': p.order_id,
        'weight': float(p.weight),
        'packed_by': p.packed_by.username if p.packed_by else '',
        'status': p.status, 'status_display': p.get_status_display(),
        'packed_at': p.packed_at.strftime('%Y-%m-%dT%H:%M') if p.packed_at else '',
        'packed_at_display': p.packed_at.strftime('%d/%m/%Y %H:%M') if p.packed_at else '',
        'note': p.note or '',
    } for p in packs]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_packaging(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        pid = data.get('id')
        if pid:
            p = _get_packaging_for_user(request, pid)
            if not p:
                return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phiếu đóng gói'})
        else:
            p = Packaging()
        order = _get_order_for_user(request, data.get('order_id'))
        if not order:
            return JsonResponse({'status': 'error', 'message': 'Đơn hàng không thuộc phạm vi cửa hàng của bạn.'})
        if order.status in (5, 6):
            return JsonResponse({
                'status': 'error',
                'message': 'Không thể đóng gói đơn hàng đã Hoàn thành/Hủy.'
            })
        p.code = data.get('code', '')
        p.order = order
        p.status = int(data.get('status', 0) or 0)
        p.weight = data.get('weight', 0) or 0
        p.note = data.get('note', '')
        p.packed_by = request.user

        packed_at = data.get('packed_at')
        if packed_at:
            from django.utils.dateparse import parse_datetime
            p.packed_at = parse_datetime(packed_at)

        p.save()
        target_order_status = 1
        if p.status in (1, 2):
            target_order_status = 3
        if order.status < target_order_status and order.status < 4:
            old_status = order.status
            order.status = target_order_status
            order.save(update_fields=['status'])
            _log_order_history(
                order=order,
                actor=request.user,
                action='status',
                summary=f'Cập nhật từ phiếu đóng gói {p.code}.',
                status_before=old_status,
                status_after=order.status,
            )
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_packaging(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        packaging = _get_packaging_for_user(request, data.get('id'))
        if not packaging:
            return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phiếu đóng gói'})
        packaging.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: POS CHECKOUT ============

@login_required(login_url="/login/")
def api_pos_checkout(request):
    """POS bán hàng nhanh — tạo đơn + trừ kho + tích điểm"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        items_data = data.get('items', [])
        if not items_data:
            return JsonResponse({'status': 'error', 'message': 'Giỏ hàng trống'})

        with transaction.atomic():
            store = get_user_store(request)
            if not store:
                from core.store_utils import get_managed_store_ids
                from system_management.models import Store as StoreModel
                sids = get_managed_store_ids(request.user)
                store = StoreModel.objects.filter(id__in=sids).first() if sids else None

            # Auto generate code
            prefix = 'POS'
            last = Order.objects.filter(code__startswith=prefix).order_by('-id').first()
            if last:
                try:
                    num = int(last.code.replace(prefix + '-', '')) + 1
                except (TypeError, ValueError):
                    num = 1
            else:
                num = 1
            code = f'{prefix}-{num:04d}'

            # Get default warehouse
            warehouse = Warehouse.objects.filter(
                store=store, is_active=True
            ).first() if store else None
            customer = _resolve_sale_customer(request, data.get('customer_id')) if data.get('customer_id') else None
            if customer and not _is_guest_customer(customer) and store and customer.store_id != store.id:
                raise ValueError('Khách hàng không cùng cửa hàng với POS hiện tại.')

            subtotal = Decimal('0')
            normalized_items = []
            for item_data in items_data:
                qty = _non_negative_decimal(item_data.get('quantity', 1), default='1')
                price = _non_negative_decimal(item_data.get('unit_price', 0))
                disc = _normalize_percentage(item_data.get('discount_percent', 0))
                line_total = _calculate_line_total(qty, price, disc)
                subtotal += line_total
                normalized_items.append({
                    'product_id': item_data['product_id'],
                    'quantity': qty,
                    'unit_price': price,
                    'discount_percent': disc,
                    'total_price': line_total,
                })

            discount_amount = _non_negative_decimal(data.get('discount_amount', 0))
            final_amount = _calculate_final_amount(subtotal, discount_amount, 0)
            requested_paid_amount = _non_negative_decimal(data.get('paid_amount', final_amount), default=str(final_amount))
            paid_amount = min(requested_paid_amount, final_amount)

            order = Order(
                code=code,
                store=store,
                warehouse=warehouse,
                customer=customer,
                status=5,  # Hoàn thành
                payment_status=0,
                total_amount=subtotal,
                discount_amount=discount_amount,
                final_amount=final_amount,
                paid_amount=0,
                order_date=date.today(),
                note=data.get('note', ''),
                created_by=request.user,
                creator_name=request.user.get_full_name() or request.user.username,
            )
            order.save()

            # Create items + deduct stock
            allow_negative_stock = _allow_negative_stock_for_store(store)
            for item_data in normalized_items:
                product = _get_product_for_user(request, item_data['product_id'])
                if not product:
                    raise ValueError('Có sản phẩm không tồn tại hoặc không thuộc cửa hàng hiện tại.')
                if store and product.store_id != store.id:
                    raise ValueError(f'Sản phẩm "{product.name}" không cùng cửa hàng với POS hiện tại.')
                oi = OrderItem(
                    order=order,
                    product=product,
                    quantity=item_data.get('quantity', 1),
                    unit_price=item_data.get('unit_price', 0),
                    total_price=item_data.get('total_price', 0),
                    discount_percent=item_data.get('discount_percent', 0),
                    cost_price=float(product.cost_price or 0),
                )
                oi.save()

                # Deduct stock
                if warehouse and not getattr(product, 'is_service', False):
                    if product.is_combo:
                        # Combo: trừ kho từng thành phần
                        from products.models import ComboItem
                        combo_items = ComboItem.objects.filter(combo=product).select_related('product')
                        for ci in combo_items:
                            qty_deduct = _to_decimal(ci.quantity) * _to_decimal(item_data.get('quantity', 1))
                            stock = _get_locked_stock(ci.product_id, warehouse.id)
                            _adjust_locked_stock(stock, -qty_deduct, allow_negative=allow_negative_stock)
                    else:
                        stock = _get_locked_stock(product.id, warehouse.id)
                        _adjust_locked_stock(
                            stock,
                            -_to_decimal(item_data.get('quantity', 1)),
                            allow_negative=allow_negative_stock,
                        )

            if paid_amount > 0:
                _create_completed_receipt_for_order(
                    order=order,
                    actor=request.user,
                    amount=paid_amount,
                    payment_method=int(data.get('payment_method', 2) or 2),
                    payment_method_option_id=data.get('payment_method_option_id') or None,
                    cash_book_id=data.get('cash_book_id') or None,
                    base_code=f'PT-{order.code}',
                    description_suffix='POS',
                )
            else:
                _refresh_order_payment(order)

            # Tích điểm
            try:
                from customers.views import add_loyalty_points_for_order
                add_loyalty_points_for_order(order)
            except Exception as e:
                logger.warning(f'Loyalty points error: {e}')

            # Update table status if provided
            table_id = data.get('table_id')
            if table_id:
                try:
                    from customers.models import CafeTable
                    tbl = filter_by_store(CafeTable.objects.filter(id=table_id), request).first()
                    if not tbl:
                        raise CafeTable.DoesNotExist
                    tbl.status = 0  # Trống
                    tbl.current_order = None
                    tbl.save()
                except Exception:
                    pass

        return JsonResponse({
            'status': 'ok',
            'message': 'Thanh toán thành công',
            'order_code': code,
            'order_id': order.id
        })
    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': str(e)})
    except Exception as e:
        logger.error(f'POS checkout error: {e}')
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ EXCEL EXPORT ============

@login_required(login_url="/login/")
def export_orders_excel(request):
    """Xuất danh sách đơn hàng ra Excel"""
    from core.excel_export import excel_response
    from core.store_utils import filter_by_store
    from datetime import datetime

    active_receipts = Receipt.objects.select_related('payment_method_option').filter(status=1)
    orders = Order.objects.select_related(
        'customer', 'warehouse', 'created_by'
    ).prefetch_related(
        'items__product',
        Prefetch('receipts', queryset=active_receipts, to_attr='active_receipts'),
    ).all().order_by('-order_date', '-id')
    orders = filter_by_store(orders, request)

    date_from = request.GET.get('date_from') or request.GET.get('from_date')
    date_to = request.GET.get('date_to') or request.GET.get('to_date')
    created_from = request.GET.get('created_from')
    created_to = request.GET.get('created_to')
    status = request.GET.get('status')
    payment_status = request.GET.get('payment_status')
    payment_method = request.GET.get('payment_method')
    creator = request.GET.get('creator')
    product = (request.GET.get('product') or '').strip()
    if date_from:
        orders = orders.filter(order_date__gte=date_from)
    if date_to:
        orders = orders.filter(order_date__lte=date_to)
    if created_from:
        orders = orders.filter(created_at__date__gte=created_from)
    if created_to:
        orders = orders.filter(created_at__date__lte=created_to)
    if status not in [None, '']:
        orders = orders.filter(status=int(status))
    if payment_status not in [None, '']:
        orders = orders.filter(payment_status=int(payment_status))
    if payment_method:
        orders = orders.filter(receipts__status=1, receipts__payment_method_option_id=payment_method)
    if creator:
        orders = orders.filter(created_by_id=creator)
    if product:
        orders = orders.filter(
            Q(items__product__code__icontains=product) |
            Q(items__product__name__icontains=product) |
            Q(items__product__barcode__icontains=product) |
            Q(items__item_name__icontains=product)
        )
    if payment_method or product:
        orders = orders.distinct()

    columns = [
        {'key': 'stt', 'label': 'STT', 'width': 6},
        {'key': 'code', 'label': 'Mã ĐH', 'width': 14},
        {'key': 'date', 'label': 'Ngày', 'width': 13},
        {'key': 'created_at', 'label': 'Ngày tạo', 'width': 18},
        {'key': 'customer', 'label': 'Khách hàng', 'width': 24},
        {'key': 'products', 'label': 'Sản phẩm', 'width': 32},
        {'key': 'warehouse', 'label': 'Kho', 'width': 16},
        {'key': 'total', 'label': 'Tổng tiền hàng', 'width': 16},
        {'key': 'discount', 'label': 'Chiết khấu', 'width': 14},
        {'key': 'shipping', 'label': 'Phí VC', 'width': 12},
        {'key': 'final', 'label': 'Tổng thanh toán', 'width': 18},
        {'key': 'paid', 'label': 'Đã trả', 'width': 16},
        {'key': 'debt', 'label': 'Còn nợ', 'width': 16},
        {'key': 'payment', 'label': 'Thanh toán', 'width': 16},
        {'key': 'payment_method', 'label': 'PT thanh toán', 'width': 18},
        {'key': 'status', 'label': 'Trạng thái', 'width': 14},
        {'key': 'creator', 'label': 'Người tạo', 'width': 16},
        {'key': 'note', 'label': 'Ghi chú', 'width': 28},
    ]

    rows = []
    total_final = 0
    total_paid = 0
    total_debt = 0
    for i, o in enumerate(orders, 1):
        receipts = list(getattr(o, 'active_receipts', []))
        payment_methods = sorted({
            r.get_payment_method_label()
            for r in receipts
            if r.get_payment_method_label()
        })
        products = [
            ' - '.join(part for part in [_item_display_code(it), _item_display_name(it)] if part)
            for it in o.items.all()
        ]
        debt = max(float(o.final_amount) - float(o.paid_amount), 0)
        total_final += float(o.final_amount)
        total_paid += float(o.paid_amount)
        total_debt += debt
        rows.append({
            'stt': i,
            'code': o.code,
            'date': o.order_date,
            'created_at': o.created_at.strftime('%d/%m/%Y %H:%M') if o.created_at else '',
            'customer': o.customer.name if o.customer else '',
            'products': ', '.join(products),
            'warehouse': o.warehouse.name if o.warehouse else '',
            'total': float(o.total_amount),
            'discount': float(o.discount_amount),
            'shipping': float(o.shipping_fee) if hasattr(o, 'shipping_fee') else 0,
            'final': float(o.final_amount),
            'paid': float(o.paid_amount),
            'debt': debt,
            'payment': o.get_payment_status_display(),
            'payment_method': ', '.join(payment_methods),
            'status': o.get_status_display(),
            'creator': (o.created_by.get_full_name() or o.created_by.username) if o.created_by else '',
            'note': o.note or '',
        })

    period = ''
    if date_from and date_to:
        period = f' ({date_from} → {date_to})'
    elif date_from:
        period = f' (từ {date_from})'
    elif date_to:
        period = f' (đến {date_to})'

    return excel_response(
        title='DANH SÁCH ĐƠN HÀNG',
        subtitle=f'Xuất ngày {datetime.now().strftime("%d/%m/%Y %H:%M")}{period}',
        columns=columns,
        rows=rows,
        filename=f'Don_hang_{datetime.now().strftime("%Y%m%d")}',
        money_cols=['total', 'discount', 'shipping', 'final', 'paid', 'debt'],
        total_row={'stt': '', 'code': 'TỔNG CỘNG', 'final': total_final, 'paid': total_paid, 'debt': total_debt},
    )


@login_required(login_url="/login/")
def api_print_order(request):
    """
    GET /api/orders/print/?id=<order_id>&type=k80|a4|quotation|quotation_a4|warranty|export
    Quy ước mẫu in: a4 = hóa đơn A4, quotation = báo giá A5.
    Renders a print-ready HTML page for the given order.
    Also supports source=quotation to print from Quotation model.
    """
    order_id = request.GET.get('id')
    print_type = request.GET.get('type', 'a4')
    source = request.GET.get('source', 'order')  # 'order' or 'quotation'

    TEMPLATES = {
        'k80': 'orders/print/receipt_k80.html',
        'a4': 'orders/print/invoice_a4.html',
        'quotation': 'orders/print/quotation_a5.html',
        'quotation_a4': 'orders/print/quotation_a4.html',
        'warranty': 'orders/print/warranty_a4.html',
        'export': 'orders/print/export_a4.html',
    }
    template = TEMPLATES.get(print_type, TEMPLATES['a4'])

    if source == 'quotation':
        try:
            quotation = _get_quotation_for_user(request, order_id)
            if not quotation:
                raise Quotation.DoesNotExist
        except Quotation.DoesNotExist:
            return render(request, template, {'error': 'Không tìm thấy báo giá'})
        items = quotation.items.select_related('product').all()

        # Wrap quotation as an order-like object for template compatibility
        class QuotationWrapper:
            def __init__(self, q):
                self._q = q
                self.code = q.code
                self.customer = q.customer
                self.order_date = q.quotation_date
                self.total_amount = q.total_amount
                self.discount_amount = q.discount_amount
                self.shipping_fee = q.shipping_fee
                self.final_amount = q.final_amount
                self.paid_amount = Decimal('0')
                self.note = q.note
                self.salesperson = q.salesperson
                self.status = q.status
                self.store = q.store
                self.warehouse = None
                self.shipping_address = None
                self.created_by = q.created_by
                self.tags = q.tags

            def get_status_display(self):
                return self._q.get_status_display()

        order = QuotationWrapper(quotation)
        remaining = 0
        valid_until = quotation.valid_until
        brand = _get_brand_for_print(request, quotation)
    else:
        try:
            order = _get_order_for_user(
                request,
                order_id,
                queryset=Order.objects.select_related('customer', 'warehouse', 'created_by', 'store', 'store__brand'),
            )
            if not order:
                raise Order.DoesNotExist
        except Order.DoesNotExist:
            return render(request, template, {'error': 'Không tìm thấy đơn hàng'})
        items = order.items.select_related('product').all()
        remaining = max(0, float(order.final_amount) - float(order.paid_amount))
        valid_until = None
        brand = _get_brand_for_print(request, order)

    template_type = print_type if print_type in dict(PrintTemplate.TEMPLATE_TYPE_CHOICES) else 'a4'
    print_template = _get_print_template(template_type, brand)
    warranty_items = None
    if print_type == 'warranty':
        warranty_items = _parse_warranty_items_payload(request.GET.get('warranty_items'))
        if warranty_items is None:
            warranty_items = _build_default_warranty_items(items)

    context = {
        'order': order,
        'items': items,
        'warranty_items': warranty_items,
        'brand': brand,
        'remaining': remaining,
        'valid_until': valid_until,
        'print_type': print_type,
        'print_template': print_template,
    }
    return render(request, template, context)
