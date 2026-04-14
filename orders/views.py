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
from django.db.models import Q
from django.views.decorators.cache import never_cache
from .models import (
    Order, OrderItem, Quotation, QuotationItem, OrderReturn, OrderReturnItem,
    Packaging, OrderEditHistory,
)
from customers.models import Customer
from products.models import Product, Warehouse, ProductStock
from finance.models import Receipt, FinanceCategory, CashBook, PaymentMethodOption
from finance.services import (
    cancel_receipt_with_effect,
    save_receipt_with_effect,
    update_order_payment_status,
)
from core.store_utils import filter_by_store, get_user_store, brand_owner_required

logger = logging.getLogger(__name__)

GUEST_CUSTOMER_CODE_PREFIX = 'KHLE-'
GUEST_CUSTOMER_NAME = 'Khách lẻ / khách vãng lai'


def _to_decimal(value, default='0'):
    try:
        return Decimal(str(value if value not in (None, '') else default))
    except Exception:
        return Decimal(str(default))


def _adjust_stock_quantity(stock, delta):
    stock.quantity = _to_decimal(stock.quantity) + _to_decimal(delta)
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


def _get_or_create_guest_customer(request):
    store = _get_default_store_for_request(request)
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
    if customer_id:
        customer = _get_sales_customers_queryset(request).filter(id=customer_id).first()
        if customer:
            return customer
    return _get_or_create_guest_customer(request)


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
        status__in=[1, 2, 3, 4],
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
    OrderEditHistory.objects.create(
        order=order,
        actor=actor,
        action=action,
        summary=summary or '',
        status_before=status_before,
        status_after=status_after,
    )


def _get_cashbook_for_payment(payment_method, selected_method=None, cash_book_id=None):
    if cash_book_id:
        cash_book = CashBook.objects.filter(id=cash_book_id, is_active=True).first()
        if cash_book:
            return cash_book
    if selected_method and selected_method.default_cash_book_id:
        return selected_method.default_cash_book
    lookup = 'ngân hàng' if payment_method == 2 else 'tiền mặt'
    return CashBook.objects.filter(is_active=True, name__icontains=lookup).first()


def _next_receipt_code(base_code):
    receipt_code = base_code
    suffix = 1
    while Receipt.all_objects.filter(code=receipt_code).exists():
        suffix += 1
        receipt_code = f'{base_code}-{suffix}'
    return receipt_code


def _create_completed_receipt_for_order(order, actor, amount, payment_method=2,
                                        payment_method_option_id=None, cash_book_id=None,
                                        base_code=None, description_suffix='tự động'):
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


def _refresh_order_payment(order):
    update_order_payment_status(order)
    order.refresh_from_db(fields=['paid_amount', 'payment_status'])


@login_required(login_url="/login/")
@brand_owner_required
def order_tbl(request):
    from core.store_utils import get_managed_store_ids
    store_ids = get_managed_store_ids(request.user)
    customers = list(_get_sales_customers_queryset(request).values('id', 'code', 'name', 'phone'))
    warehouses = list(Warehouse.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'name'))
    cashbooks = list(CashBook.objects.filter(is_active=True).values('id', 'name'))
    payment_methods = list(PaymentMethodOption.objects.filter(is_active=True).values(
        'id', 'name', 'default_cash_book_id', 'legacy_type'
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
    context = {'active_tab': 'order_return_tbl'}
    return render(request, "orders/order_return_list.html", context)


@login_required(login_url="/login/")
@brand_owner_required
def packaging_tbl(request):
    orders = list(Order.objects.exclude(status=6).values('id', 'code').order_by('-order_date'))
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
    orders = Order.objects.select_related('customer', 'customer__group', 'warehouse').prefetch_related('receipts').all()
    orders = filter_by_store(orders, request)
    data = [{
        'id': o.id, 'code': o.code,
        'customer': o.customer.name if o.customer else GUEST_CUSTOMER_NAME,
        'customer_id': o.customer_id,
        'customer_phone': o.customer.phone if o.customer and o.customer.phone else '',
        'warehouse': o.warehouse.name if o.warehouse else '',
        'warehouse_id': o.warehouse_id,
        'order_date': o.order_date.strftime('%Y-%m-%d') if o.order_date else '',
        'total_amount': float(o.total_amount),
        'discount_amount': float(o.discount_amount),
        'shipping_fee': float(getattr(o, 'shipping_fee', 0) or 0),
        'final_amount': float(o.final_amount),
        'paid_amount': float(o.paid_amount),
        'remaining_amount': max(float(o.final_amount) - float(o.paid_amount), 0),
        'status': o.status, 'status_display': o.get_status_display(),
        'payment_status': o.payment_status,
        'payment_status_display': o.get_payment_status_display(),
        'has_receipt': o.receipts.filter(status=1).exists(),
        'receipt_count': o.receipts.filter(status=1).count(),
        'tags': o.tags or '',
        'note': o.note or '',
        'customer_group': o.customer.group.name if o.customer and o.customer.group else '',
        'customer_group_id': o.customer.group_id if o.customer else None,
        'creator_name': o.creator_name or '',
        'salesperson': o.salesperson or '',
        'server_staff': o.server_staff or '',
        'approver_id': o.approver_id,
        'approver_name': o.approver.get_full_name() if o.approver else '',
        'approval_status': o.approval_status,
        'approval_status_display': o.get_approval_status_display(),
        'approved_at': o.approved_at.strftime('%d/%m/%Y %H:%M') if o.approved_at else '',
        'bonus_amount': float(o.bonus_amount),
    } for o in orders]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_get_order_detail(request):
    """Lấy chi tiết đơn hàng bao gồm items"""
    oid = request.GET.get('id')
    if not oid:
        return JsonResponse({'status': 'error', 'message': 'Missing id'})
    try:
        o = Order.objects.select_related('customer', 'warehouse').get(id=oid)
        items = [{
            'product_id': it.product_id,
            'variant_id': it.variant_id,
            'product_code': it.product.code,
            'product_name': it.product.name,
            'variant_name': it.variant.size_name if it.variant else '',
            'unit': it.product.unit,
            'image_url': it.product.image.url if it.product.image else '',
            'quantity': float(it.quantity),
            'unit_price': float(it.unit_price),
            'discount_percent': float(it.discount_percent),
            'total_price': float(it.total_price),
        } for it in o.items.select_related('product', 'variant').all()]
        return JsonResponse({
            'status': 'ok',
            'order': {
                'id': o.id,
                'code': o.code,
                'customer_id': None if _is_guest_customer(o.customer) else o.customer_id,
                'customer_label': o.customer.name if o.customer else GUEST_CUSTOMER_NAME,
                'warehouse_id': o.warehouse_id,
                'order_date': o.order_date.strftime('%Y-%m-%d') if o.order_date else '',
                'discount_amount': float(o.discount_amount),
                'shipping_fee': float(getattr(o, 'shipping_fee', 0) or 0),
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
            oid = data.get('id')
            old_status = None
            history_action = 'update' if oid else 'create'
            if oid:
                o = Order.objects.get(id=oid)
                old_status = o.status
                # KHÓA: Không cho sửa đơn hàng đã Hoàn thành hoặc Hủy
                if old_status in (5, 6):
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Không thể sửa đơn hàng đã Hoàn thành/Hủy. Liên hệ quản lý nếu cần điều chỉnh.'
                    })
            else:
                o = Order()
                o.created_by = request.user
                if not o.store_id:
                    o.store = _get_default_store_for_request(request)
            requested_code = (data.get('code', '') or '').strip()
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
            o.customer = _resolve_sale_customer(request, data.get('customer_id'))
            o.warehouse_id = data.get('warehouse_id') or None
            o.quotation_id = data.get('quotation_id') or None
            o.order_date = data.get('order_date')
            o.discount_amount = data.get('discount_amount', 0) or 0
            o.shipping_fee = data.get('shipping_fee', 0) or 0
            o.tags = (data.get('tags', '') or '').strip() or None
            new_status = int(data.get('status', 0))
            new_approver_id_raw = data.get('approver_id') or None
            # Status transition validation — one-way flow
            STATUS_TRANSITIONS = {
                0: {0, 1, 6},       # Nháp → Xác nhận hoặc Hủy
                1: {1, 2, 6},       # Xác nhận → Đang xử lý hoặc Hủy
                2: {2, 3, 6},       # Đang xử lý → Đóng gói hoặc Hủy
                3: {3, 4, 6},       # Đóng gói → Đã giao hoặc Hủy
                4: {4, 5, 6},       # Đã giao → Hoàn thành hoặc Hủy
                5: {5},             # Hoàn thành → locked
                6: {6},             # Hủy → locked
            }
            if oid and old_status is not None:
                allowed = STATUS_TRANSITIONS.get(old_status, {old_status})
                if new_status not in allowed:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Không được chuyển trạng thái từ "{Order.STATUS_CHOICES[old_status][1]}" sang "{Order.STATUS_CHOICES[new_status][1]}". '
                                   f'Chỉ cho phép: {", ".join(Order.STATUS_CHOICES[s][1] for s in sorted(allowed) if s != old_status) or "Không chuyển được"}.'
                    })
            # SAFEGUARD: Nếu có người duyệt và chưa duyệt → không cho tự chuyển Hoàn thành
            if new_status == 5 and new_approver_id_raw and o.approval_status != 2:
                # Giữ status trước đó, không cho Hoàn thành khi chưa duyệt
                new_status = old_status or 1  # Fallback to Xác nhận
            o.status = new_status
            o.note = data.get('note', '')

            # Thông tin nhân sự
            o.creator_name = request.user.get_full_name() or request.user.username
            # NV bán hàng: nếu có quotation thì tự lấy từ người tạo báo giá
            sp = data.get('salesperson', '')
            if not sp and o.quotation_id:
                try:
                    q = Quotation.objects.get(id=o.quotation_id)
                    sp = q.salesperson or (q.created_by.get_full_name() if q.created_by else '')
                except Quotation.DoesNotExist:
                    pass
            o.salesperson = sp or None
            o.server_staff = data.get('server_staff', '') or None
            new_approver_id = data.get('approver_id') or None
            o.approver_id = new_approver_id
            # Xác định approval_status dựa trên có/không người duyệt
            if new_approver_id:
                # Có người duyệt → cần duyệt (nếu chưa duyệt)
                if o.approval_status not in (2, 3):  # Chưa duyệt/từ chối → chờ duyệt
                    o.approval_status = 1  # Chờ duyệt
            else:
                o.approval_status = 0  # Không cần duyệt
            o.bonus_amount = data.get('bonus_amount', 0) or 0

            # Tính tổng từ items
            items_data = data.get('items', [])
            _validate_unique_line_items(items_data)
            total = Decimal('0')
            for it in items_data:
                qty = Decimal(str(it.get('quantity', 0)))
                price = Decimal(str(it.get('unit_price', 0)))
                disc = Decimal(str(it.get('discount_percent', 0)))
                line_total = qty * price * (1 - disc / 100)
                total += line_total

            o.total_amount = total
            o.final_amount = total - Decimal(str(o.discount_amount or 0)) + Decimal(str(o.shipping_fee or 0))
            order_discount_ratio = Decimal('0')
            if total > 0 and Decimal(str(o.discount_amount or 0)) > 0:
                order_discount_ratio = min(Decimal(str(o.discount_amount or 0)) / total, Decimal('1'))

            try:
                o.save()
            except IntegrityError:
                if oid:
                    raise
                o.code = _auto_next_order_code()
                o.save()

            # Xử lý thanh toán — hỗ trợ multi-payment lines
            payment_lines = data.get('payment_lines', [])
            pay_mode = data.get('pay_mode', '')
            is_paid = data.get('is_paid', True) if not pay_mode else (pay_mode == 'full')
            payment_amount = float(data.get('payment_amount', 0) or 0)

            # Tính tổng đã thu từ các phiếu thu Hoàn thành hiện có
            existing_paid = sum(
                float(rec.amount)
                for rec in Receipt.objects.filter(order=o, status=1)
            )

            # Build receipt items from payment_lines or legacy single-line
            if payment_lines and isinstance(payment_lines, list):
                receipt_items = []
                for pl in payment_lines:
                    amt = float(pl.get('amount', 0) or 0)
                    if amt <= 0:
                        continue
                    receipt_items.append({
                        'amount': amt,
                        'payment_method_option_id': pl.get('payment_method_option_id'),
                        'payment_method': int(pl.get('payment_method', 2) or 2),
                        'cash_book_id': pl.get('cash_book_id'),
                    })
            else:
                # Legacy single-line
                if pay_mode == 'partial' and payment_amount > 0:
                    amount_to_collect = payment_amount
                elif is_paid:
                    amount_to_collect = float(o.final_amount) - existing_paid
                else:
                    amount_to_collect = 0
                receipt_items = [{
                    'amount': amount_to_collect,
                    'payment_method_option_id': data.get('payment_method_option_id'),
                    'payment_method': int(data.get('payment_method', 2) or 2),
                    'cash_book_id': data.get('cash_book_id'),
                }] if amount_to_collect > 0 else []

            for idx, ri in enumerate(receipt_items):
                base_code = f'PT-{o.code}' if idx == 0 else f'PT-{o.code}-{idx+1}'
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

            # Hoàn tác tồn kho nếu trước đó đã hoàn thành
            if old_status == 5 and o.warehouse_id:
                from products.models import ComboItem as _ComboItem
                for old_item in o.items.all():
                    product = old_item.product
                    if product.is_combo:
                        # Combo: hoàn lại kho từng SP thành phần
                        for ci in _ComboItem.objects.filter(combo=product):
                            if not ci.product.is_service:
                                stock, _ = ProductStock.objects.get_or_create(
                                    product_id=ci.product_id, warehouse_id=o.warehouse_id)
                                _adjust_stock_quantity(
                                    stock,
                                    _to_decimal(old_item.quantity) * _to_decimal(ci.quantity),
                                )
                    elif not product.is_service:
                        stock, _ = ProductStock.objects.get_or_create(
                            product_id=old_item.product_id, warehouse_id=o.warehouse_id)
                        _adjust_stock_quantity(stock, _to_decimal(old_item.quantity))

            # Xóa items cũ và tạo mới
            o.items.all().delete()
            loss_warnings = []
            for it in items_data:
                qty = Decimal(str(it.get('quantity', 0)))
                price = Decimal(str(it.get('unit_price', 0)))
                disc = Decimal(str(it.get('discount_percent', 0)))
                line_total = qty * price * (1 - disc / 100)
                product = Product.objects.get(id=it['product_id'])
                variant_id = it.get('variant_id') or None
                cost = Decimal(str(product.cost_price or 0))
                fallback_cost = Decimal(str(product.import_price or 0))
                if variant_id:
                    from products.models import ProductVariant
                    try:
                        variant = ProductVariant.objects.get(id=variant_id)
                        cost = Decimal(str(variant.cost_price or 0))
                        fallback_cost = Decimal(str(variant.import_price or 0))
                    except ProductVariant.DoesNotExist:
                        variant_id = None
                compare_cost = cost if cost > 0 else fallback_cost
                unit_after_line_discount = price * (1 - disc / 100)
                unit_after_order_discount = unit_after_line_discount * (1 - order_discount_ratio)
                is_below_cost = compare_cost > 0 and unit_after_order_discount < compare_cost
                if is_below_cost:
                    loss_warnings.append(
                        f'{product.code} - {product.name}: bán {int(unit_after_order_discount):,}đ < vốn {int(compare_cost):,}đ'
                    )
                OrderItem.objects.create(
                    order=o,
                    product=product,
                    variant_id=variant_id,
                    quantity=qty,
                    unit_price=price,
                    cost_price=cost,
                    discount_percent=disc,
                    total_price=line_total,
                    is_below_listed=is_below_cost,
                )
            o.below_listed_price_warning = bool(loss_warnings)
            o.save(update_fields=['below_listed_price_warning'])

            # Trừ tồn kho khi đơn hàng Hoàn thành (status=5)
            if new_status == 5 and old_status != 5 and o.warehouse_id:
                from products.models import ComboItem as _ComboItem2
                for item in o.items.select_related('product').all():
                    qty = Decimal(str(item.quantity))
                    product = item.product
                    if product.is_combo:
                        # Combo: trừ kho từng SP thành phần (bỏ qua dịch vụ)
                        for ci in _ComboItem2.objects.filter(combo_id=product.id):
                            if not ci.product.is_service:
                                stock, _ = ProductStock.objects.get_or_create(
                                    product_id=ci.product_id, warehouse_id=o.warehouse_id)
                                _adjust_stock_quantity(stock, -(qty * _to_decimal(ci.quantity)))
                    elif not product.is_service:
                        stock, _ = ProductStock.objects.get_or_create(
                            product_id=product.id, warehouse_id=o.warehouse_id)
                        _adjust_stock_quantity(stock, -qty)
            # Cập nhật trạng thái báo giá → "Đã tạo đơn hàng"
            if o.quotation_id:
                Quotation.objects.filter(id=o.quotation_id).update(status=3)

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
        return JsonResponse({'status': 'ok', 'message': msg, 'order_id': o.id, 'order_code': o.code})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_update_order_note(request):
    """Cho phép sửa ghi chú đơn hàng đã hoàn thành/hủy"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        order = Order.objects.get(id=data.get('id'))
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
        order = Order.objects.get(id=data.get('id'))
        # KHÓA: Không cho xóa đơn hàng đã Hoàn thành hoặc Hủy
        if order.status in (5, 6):
            return JsonResponse({
                'status': 'error',
                'message': 'Không thể xóa đơn hàng đã Hoàn thành/Hủy.'
            })
        order.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_cancel_order(request):
    """Hủy đơn hàng đã hoàn thành → hoàn lại tồn kho"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        order_id = data.get('id')
        reason = data.get('reason', '')

        with transaction.atomic():
            order = Order.objects.get(id=order_id)

            if order.status == 6:
                return JsonResponse({'status': 'error', 'message': 'Đơn hàng này đã bị hủy trước đó.'})

            if order.status not in (1, 2, 3, 4, 5):
                return JsonResponse({'status': 'error', 'message': 'Chỉ có thể hủy đơn hàng đã xác nhận/hoàn thành.'})

            # Nếu đơn đã hoàn thành (status=5) → hoàn lại tồn kho
            if order.status == 5 and order.warehouse_id:
                from products.models import ComboItem as _CancelComboItem
                from decimal import Decimal as _Dec
                for item in order.items.all():
                    product = item.product
                    if product.is_combo:
                        for ci in _CancelComboItem.objects.filter(combo=product):
                            if not ci.product.is_service:
                                stock, _ = ProductStock.objects.get_or_create(
                                    product_id=ci.product_id, warehouse_id=order.warehouse_id)
                                _adjust_stock_quantity(stock, _Dec(str(item.quantity)) * _Dec(str(ci.quantity)))
                    elif not product.is_service:
                        stock, _ = ProductStock.objects.get_or_create(
                            product_id=item.product_id, warehouse_id=order.warehouse_id)
                        _adjust_stock_quantity(stock, _Dec(str(item.quantity)))

            # Xử lý phiếu thu liên quan
            linked_receipts = Receipt.objects.filter(order=order)
            receipt_warning = ''
            if linked_receipts.exists():
                # Hủy phiếu thu tự động
                auto_receipts = linked_receipts.filter(description__icontains='tự động')
                manual_receipts = linked_receipts.exclude(description__icontains='tự động')

                for r in auto_receipts:
                    cancel_receipt_with_effect(
                        r,
                        note_prefix=f'[HỦY TỰ ĐỘNG] Đơn hàng {order.code} đã bị hủy.'
                    )

                if manual_receipts.exists():
                    codes = ', '.join([r.code for r in manual_receipts])
                    receipt_warning = f' ⚠️ Có phiếu thu thủ công liên quan: {codes}. Vui lòng kiểm tra và xử lý.'

            # Cập nhật trạng thái → Hủy
            old_note = order.note or ''
            cancel_note = f"[HỦY] Lý do: {reason}" if reason else "[HỦY]"
            old_status = order.status
            order.status = 6
            order.payment_status = 0
            order.paid_amount = 0
            order.note = f"{cancel_note}\n{old_note}".strip() if old_note else cancel_note
            order.save()
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
            'message': f'Đã hủy đơn hàng {order.code}. Tồn kho đã được hoàn lại.{receipt_warning}'
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
            order = Order.objects.get(id=order_id)

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
                # Duyệt chỉ đưa đơn vào luồng xử lý/đang giao dịch.
                # Tồn kho thực tế chỉ trừ ở bước Hoàn thành để tránh nhảy trạng thái quá sớm.
                if order.status < 2:
                    order.status = 2  # Đang xử lý

                if note:
                    order.note = f"{order.note or ''}\n[DUYỆT] {note}".strip()
                order.save()
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
                    'message': f'✅ Đã duyệt đơn hàng {order.code}. Đơn hàng đã chuyển sang Đang xử lý.'
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
            orders = filter_by_store(
                Order.objects.filter(id__in=ids).prefetch_related('items', 'receipts'),
                request
            )
            for order in orders:
                if order.status == 6:
                    skipped.append(f'{order.code} (đã hủy)')
                    continue
                if order.status not in (1, 2, 3, 4, 5):
                    skipped.append(f'{order.code} (không ở trạng thái được phép hủy)')
                    continue

                if order.status == 5 and order.warehouse_id:
                    from products.models import ComboItem as _CancelComboItem
                    from decimal import Decimal as _Dec
                    for item in order.items.all():
                        product = item.product
                        if product.is_combo:
                            for ci in _CancelComboItem.objects.filter(combo=product):
                                if not ci.product.is_service:
                                    stock, _ = ProductStock.objects.get_or_create(
                                        product_id=ci.product_id, warehouse_id=order.warehouse_id)
                                    _adjust_stock_quantity(stock, _Dec(str(item.quantity)) * _Dec(str(ci.quantity)))
                        elif not product.is_service:
                            stock, _ = ProductStock.objects.get_or_create(
                                product_id=item.product_id, warehouse_id=order.warehouse_id)
                            _adjust_stock_quantity(stock, _Dec(str(item.quantity)))

                auto_receipts = Receipt.objects.filter(order=order, description__icontains='tự động')
                for receipt in auto_receipts:
                    cancel_receipt_with_effect(receipt, note_prefix='[HỦY TỰ ĐỘNG] Hủy nhanh nhiều đơn.')

                old_status = order.status
                order.status = 6
                order.payment_status = 0
                order.paid_amount = 0
                order.note = (f'[HỦY NHANH] {reason}\n{order.note or ""}').strip()
                order.save(update_fields=['status', 'payment_status', 'paid_amount', 'note'])
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
        with transaction.atomic():
            orders = filter_by_store(
                Order.objects.filter(id__in=ids).prefetch_related('receipts'),
                request
            )
            for order in orders:
                if order.status == 6:
                    skipped.append(f'{order.code} (đã hủy)')
                    continue
                remaining = float(order.final_amount) - sum(
                    float(rec.amount) for rec in Receipt.objects.filter(order=order, status=1)
                )
                if remaining <= 0:
                    skipped.append(f'{order.code} (đã thanh toán đủ)')
                    continue

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
                    status_before=order.status,
                    status_after=order.status,
                )
                collected.append(order.code)

        message = f'Đã thanh toán nhanh {len(collected)} đơn.'
        if skipped:
            message += ' Bỏ qua: ' + ', '.join(skipped[:8])
        return JsonResponse({'status': 'ok', 'message': message})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: QUOTATION ============

@login_required(login_url="/login/")
def api_get_quotations(request):
    quotes = Quotation.objects.select_related('customer', 'customer__group').all()
    quotes = filter_by_store(quotes, request)
    data = [{
        'id': q.id, 'code': q.code,
        'customer': q.customer.name if q.customer else GUEST_CUSTOMER_NAME,
        'customer_id': q.customer_id,
        'customer_phone': q.customer.phone if q.customer and q.customer.phone else '',
        'customer_group': q.customer.group.name if q.customer and q.customer.group else '',
        'customer_group_id': q.customer.group_id if q.customer else None,
        'quotation_date': q.quotation_date.strftime('%Y-%m-%d') if q.quotation_date else '',
        'valid_until': q.valid_until.strftime('%Y-%m-%d') if q.valid_until else '',
        'total_amount': float(q.total_amount),
        'discount_amount': float(q.discount_amount),
        'shipping_fee': float(getattr(q, 'shipping_fee', 0) or 0),
        'final_amount': float(q.final_amount),
        'status': q.status, 'status_display': q.get_status_display(),
        'tags': q.tags or '',
        'note': q.note or '',
        'salesperson': q.salesperson or '',
        'item_count': q.items.count(),
    } for q in quotes]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_get_quotation_detail(request):
    """Lấy chi tiết báo giá bao gồm items"""
    qid = request.GET.get('id')
    if not qid:
        return JsonResponse({'status': 'error', 'message': 'Missing id'})
    try:
        q = Quotation.objects.select_related('customer').get(id=qid)
        items = [{
            'product_id': it.product_id,
            'variant_id': it.variant_id,
            'product_code': it.product.code,
            'product_name': it.product.name,
            'variant_name': it.variant.size_name if it.variant else '',
            'unit': it.product.unit,
            'image': it.product.image.url if it.product.image else '',
            'quantity': float(it.quantity),
            'unit_price': float(it.unit_price),
            'discount_percent': float(it.discount_percent),
            'total_price': float(it.total_price),
            'note': it.note or '',
        } for it in q.items.select_related('product', 'variant').all()]
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
                q = Quotation.objects.get(id=qid)
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
            q.discount_amount = data.get('discount_amount', 0) or 0
            q.shipping_fee = data.get('shipping_fee', 0) or 0
            q.tags = (data.get('tags', '') or '').strip() or None
            q.status = data.get('status', 0)
            q.note = data.get('note', '')
            q.salesperson = data.get('salesperson', '') or (request.user.get_full_name() or request.user.username)

            # Tính tổng từ items
            items_data = data.get('items', [])
            _validate_unique_line_items(items_data)
            total = 0
            for it in items_data:
                qty = float(it.get('quantity', 0))
                price = float(it.get('unit_price', 0))
                disc = float(it.get('discount_percent', 0))
                line_total = qty * price * (1 - disc / 100)
                total += line_total

            q.total_amount = total
            q.final_amount = total - float(q.discount_amount) + float(q.shipping_fee or 0)
            quotation_discount_ratio = 0
            if total > 0 and float(q.discount_amount or 0) > 0:
                quotation_discount_ratio = min(float(q.discount_amount or 0) / total, 1)
            q.save()

            # Lưu items
            loss_warnings = []
            for it in items_data:
                qty = float(it.get('quantity', 0))
                price = float(it.get('unit_price', 0))
                disc = float(it.get('discount_percent', 0))
                line_total = qty * price * (1 - disc / 100)
                product = Product.objects.get(id=it['product_id'])
                compare_cost = float(product.cost_price or product.import_price or 0)
                variant_id = it.get('variant_id') or None
                if variant_id:
                    from products.models import ProductVariant
                    variant = ProductVariant.objects.filter(id=variant_id).first()
                    if variant:
                        compare_cost = float(variant.cost_price or variant.import_price or compare_cost)
                effective_unit_price = price * (1 - disc / 100) * (1 - quotation_discount_ratio)
                if compare_cost > 0 and effective_unit_price < compare_cost:
                    loss_warnings.append(
                        f'{product.code} - {product.name}: bán {int(effective_unit_price):,}đ < vốn {int(compare_cost):,}đ'
                    )
                QuotationItem.objects.create(
                    quotation=q,
                    product=product,
                    variant_id=variant_id,
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
        Quotation.objects.filter(id=data.get('id')).delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: ORDER RETURN ============

@login_required(login_url="/login/")
def api_get_order_returns(request):
    returns = OrderReturn.objects.select_related('order', 'customer').all()
    returns = filter_by_store(returns, request, field_name='order__store')
    data = [{
        'id': r.id, 'code': r.code,
        'order': r.order.code if r.order else '',
        'customer': r.customer.name if r.customer else '',
        'return_date': r.return_date.strftime('%Y-%m-%d') if r.return_date else '',
        'total_refund': float(r.total_refund),
        'status': r.status, 'status_display': r.get_status_display(),
        'reason': r.reason or '',
    } for r in returns]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_order_return(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        rid = data.get('id')
        if rid:
            r = OrderReturn.objects.get(id=rid)
        else:
            r = OrderReturn()
            r.created_by = request.user
        r.code = data.get('code', '')
        r.customer_id = data.get('customer_id') or None
        r.return_date = data.get('return_date')
        r.total_refund = data.get('total_refund', 0) or 0
        r.reason = data.get('reason', '')
        r.status = data.get('status', 0)
        r.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
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
            p = Packaging.objects.get(id=pid)
        else:
            p = Packaging()
        p.code = data.get('code', '')
        p.order_id = data.get('order_id') or None
        p.status = data.get('status', 0)
        p.weight = data.get('weight', 0) or 0
        p.note = data.get('note', '')
        p.packed_by = request.user

        packed_at = data.get('packed_at')
        if packed_at:
            from django.utils.dateparse import parse_datetime
            p.packed_at = parse_datetime(packed_at)

        p.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_packaging(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        Packaging.objects.filter(id=data.get('id')).delete()
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
                except:
                    num = 1
            else:
                num = 1
            code = f'{prefix}-{num:04d}'

            # Get default warehouse
            warehouse = Warehouse.objects.filter(
                store=store, is_active=True
            ).first() if store else None

            order = Order(
                code=code,
                store=store,
                warehouse=warehouse,
                customer_id=data.get('customer_id') or None,
                status=5,  # Hoàn thành
                payment_status=0,
                total_amount=data.get('total_amount', 0),
                discount_amount=data.get('discount_amount', 0),
                final_amount=data.get('final_amount', 0),
                paid_amount=0,
                order_date=date.today(),
                note=data.get('note', ''),
                created_by=request.user,
                creator_name=request.user.get_full_name() or request.user.username,
            )
            order.save()

            # Create items + deduct stock
            for item_data in items_data:
                product = Product.objects.get(id=item_data['product_id'])
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
                            stock, _ = ProductStock.objects.get_or_create(
                                product=ci.product, warehouse=warehouse,
                                defaults={'quantity': 0}
                            )
                            _adjust_stock_quantity(stock, -qty_deduct)
                    else:
                        stock, _ = ProductStock.objects.get_or_create(
                            product=product, warehouse=warehouse,
                            defaults={'quantity': 0}
                        )
                        _adjust_stock_quantity(stock, -_to_decimal(item_data.get('quantity', 1)))

            paid_amount = Decimal(str(data.get('paid_amount') or data.get('final_amount') or 0))
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
                    tbl = CafeTable.objects.get(id=table_id)
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

    orders = Order.objects.select_related(
        'customer', 'warehouse', 'created_by'
    ).all().order_by('-order_date', '-id')
    orders = filter_by_store(orders, request)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    status = request.GET.get('status')
    if date_from:
        orders = orders.filter(order_date__gte=date_from)
    if date_to:
        orders = orders.filter(order_date__lte=date_to)
    if status:
        orders = orders.filter(status=int(status))

    columns = [
        {'key': 'stt', 'label': 'STT', 'width': 6},
        {'key': 'code', 'label': 'Mã ĐH', 'width': 14},
        {'key': 'date', 'label': 'Ngày', 'width': 13},
        {'key': 'customer', 'label': 'Khách hàng', 'width': 24},
        {'key': 'warehouse', 'label': 'Kho', 'width': 16},
        {'key': 'total', 'label': 'Tổng tiền hàng', 'width': 16},
        {'key': 'discount', 'label': 'Chiết khấu', 'width': 14},
        {'key': 'shipping', 'label': 'Phí VC', 'width': 12},
        {'key': 'final', 'label': 'Tổng thanh toán', 'width': 18},
        {'key': 'paid', 'label': 'Đã trả', 'width': 16},
        {'key': 'debt', 'label': 'Còn nợ', 'width': 16},
        {'key': 'payment', 'label': 'Thanh toán', 'width': 16},
        {'key': 'status', 'label': 'Trạng thái', 'width': 14},
        {'key': 'creator', 'label': 'Người tạo', 'width': 16},
        {'key': 'note', 'label': 'Ghi chú', 'width': 28},
    ]

    rows = []
    total_final = 0
    total_paid = 0
    total_debt = 0
    for i, o in enumerate(orders, 1):
        debt = max(float(o.final_amount) - float(o.paid_amount), 0)
        total_final += float(o.final_amount)
        total_paid += float(o.paid_amount)
        total_debt += debt
        rows.append({
            'stt': i,
            'code': o.code,
            'date': o.order_date,
            'customer': o.customer.name if o.customer else '',
            'warehouse': o.warehouse.name if o.warehouse else '',
            'total': float(o.total_amount),
            'discount': float(o.discount_amount),
            'shipping': float(o.shipping_fee) if hasattr(o, 'shipping_fee') else 0,
            'final': float(o.final_amount),
            'paid': float(o.paid_amount),
            'debt': debt,
            'payment': o.get_payment_status_display(),
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
    GET /api/orders/print/?id=<order_id>&type=k80|a4|quotation|warranty|export
    Renders a print-ready HTML page for the given order.
    Also supports source=quotation to print from Quotation model.
    """
    from system_management.models import Brand

    order_id = request.GET.get('id')
    print_type = request.GET.get('type', 'a4')
    source = request.GET.get('source', 'order')  # 'order' or 'quotation'

    TEMPLATES = {
        'k80': 'orders/print/receipt_k80.html',
        'a4': 'orders/print/invoice_a4.html',
        'quotation': 'orders/print/quotation_a4.html',
        'warranty': 'orders/print/warranty_a4.html',
        'export': 'orders/print/export_a4.html',
    }
    template = TEMPLATES.get(print_type, TEMPLATES['a4'])

    # Get brand info for header
    brand = None
    try:
        from core.store_utils import get_owned_brands
        brands = get_owned_brands(request.user)
        brand = brands.first() if brands.exists() else None
    except Exception:
        pass

    if source == 'quotation':
        try:
            quotation = Quotation.objects.select_related('customer').get(id=order_id)
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
                self.warehouse = None
                self.shipping_address = None
                self.created_by = q.created_by
                self.tags = q.tags

            def get_status_display(self):
                return self._q.get_status_display()

        order = QuotationWrapper(quotation)
        remaining = 0
        valid_until = quotation.valid_until
    else:
        try:
            order = Order.objects.select_related('customer', 'warehouse', 'created_by').get(id=order_id)
        except Order.DoesNotExist:
            return render(request, template, {'error': 'Không tìm thấy đơn hàng'})
        items = order.items.select_related('product').all()
        remaining = max(0, float(order.final_amount) - float(order.paid_amount))
        valid_until = None

    context = {
        'order': order,
        'items': items,
        'brand': brand,
        'remaining': remaining,
        'valid_until': valid_until,
        'print_type': print_type,
    }
    return render(request, template, context)
