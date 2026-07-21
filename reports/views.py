import logging
import unicodedata
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from functools import wraps
from django.core.paginator import Paginator
from django.shortcuts import render
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import DecimalField, ExpressionWrapper, Sum, Count, Q, F
from django.utils.dateparse import parse_date
from orders.models import Order, OrderItem, OrderReturn, OrderReturnItem
from core.store_utils import (
    filter_by_store,
    brand_owner_required,
    report_permission_required,
    can_view_sales_report,
    get_managed_store_ids,
)

logger = logging.getLogger(__name__)


CUSTOMER_KIND_OPTIONS = [
    {'value': 'retail', 'label': 'Khách lẻ'},
    {'value': 'wholesale', 'label': 'Khách buôn / sỉ'},
    {'value': 'other', 'label': 'Khác / chưa phân loại'},
]

RETAIL_GROUP_KEYWORDS = ('lẻ', 'le', 'bán lẻ', 'ban le', 'retail')
WHOLESALE_GROUP_KEYWORDS = (
    'sỉ', 'si', 'buôn', 'buon', 'bán buôn', 'ban buon',
    'đại lý', 'dai ly', 'wholesale',
)


def _parse_sales_report_number(value):
    """Chuyển tham số số từ query string sang float; trả None nếu rỗng hoặc sai định dạng."""
    if value in (None, ''):
        return None
    try:
        return float(str(value).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def _normalize_report_text(value):
    text = str(value or '').casefold()
    text = ''.join(
        char for char in unicodedata.normalize('NFKD', text)
        if not unicodedata.combining(char)
    )
    return text.replace('đ', 'd')


def _parse_filter_int(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _inventory_valuation_unit_cost(product):
    """Giá dùng để định giá tồn: ưu tiên giá vốn, fallback về giá nhập."""
    cost_price = Decimal(str(product.cost_price or 0))
    if cost_price > 0:
        return cost_price, 'cost_price'

    import_price = Decimal(str(product.import_price or 0))
    if import_price > 0:
        return import_price, 'import_price'

    return Decimal('0'), 'none'


def _report_lookup(prefix, suffix):
    return f'{prefix}__{suffix}' if prefix else suffix


def _group_name_keyword_q(prefix, keywords):
    query = Q()
    for keyword in keywords:
        query |= Q(**{_report_lookup(prefix, 'group__name__icontains'): keyword})
    return query


def _get_sales_report_customer_kind_q(kind, prefix='customer'):
    """Ưu tiên field customer_kind; fallback sang suy luận từ nhóm KH cho dữ liệu cũ."""
    if kind not in {'retail', 'wholesale', 'other'}:
        return Q()

    kind_lookup = _report_lookup(prefix, 'customer_kind')
    explicit_kind_q = Q(**{kind_lookup: kind})
    blank_kind_q = Q(**{kind_lookup: ''})
    retail_legacy_q = blank_kind_q & _group_name_keyword_q(prefix, RETAIL_GROUP_KEYWORDS)
    wholesale_legacy_q = blank_kind_q & _group_name_keyword_q(prefix, WHOLESALE_GROUP_KEYWORDS)

    if kind == 'retail':
        if prefix:
            return explicit_kind_q | retail_legacy_q | Q(**{_report_lookup(prefix, 'isnull'): True})
        return explicit_kind_q | retail_legacy_q
    if kind == 'wholesale':
        return explicit_kind_q | wholesale_legacy_q
    known_legacy_q = retail_legacy_q | wholesale_legacy_q
    return explicit_kind_q | (blank_kind_q & ~known_legacy_q)


def _get_sales_report_return_customer_kind_q(kind):
    if kind not in {'retail', 'wholesale', 'other'}:
        return Q()
    return (
        (Q(order__isnull=False) & _get_sales_report_customer_kind_q(kind, 'order__customer')) |
        (Q(order__isnull=True) & _get_sales_report_customer_kind_q(kind, 'customer'))
    )


def _classify_sales_report_customer_kind(customer):
    if not customer:
        return 'retail', 'Khách lẻ'
    explicit_kind = str(getattr(customer, 'customer_kind', '') or '').strip()
    explicit_label = next(
        (option['label'] for option in CUSTOMER_KIND_OPTIONS if option['value'] == explicit_kind),
        '',
    )
    if explicit_label:
        return explicit_kind, explicit_label
    group_name = customer.group.name if getattr(customer, 'group', None) else ''
    normalized_group = _normalize_report_text(group_name)
    if any(keyword in normalized_group for keyword in ('si', 'buon', 'ban buon', 'dai ly', 'wholesale')):
        return 'wholesale', 'Khách buôn / sỉ'
    if any(keyword in normalized_group for keyword in ('le', 'ban le', 'retail')):
        return 'retail', 'Khách lẻ'
    return 'other', 'Khác / chưa phân loại'


def _get_product_category_scope_q(category_id, prefix):
    category_id = _parse_filter_int(category_id)
    if category_id is None:
        return Q()
    return (
        Q(**{f'{prefix}category_id': category_id}) |
        Q(**{f'{prefix}category__parent_id': category_id})
    )


def _get_product_category_direct_q(category_id, prefix):
    category_id = _parse_filter_int(category_id)
    if category_id is None:
        return Q()
    return Q(**{f'{prefix}category_id': category_id})


def sales_report_privileged_required(view_func):
    """Báo cáo bán hàng chỉ cho Chủ thương hiệu / Giám đốc / Kế toán."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if can_view_sales_report(request.user):
            return view_func(request, *args, **kwargs)
        message = 'Chỉ tài khoản Chủ thương hiệu, Giám đốc hoặc Kế toán mới được xem báo cáo bán hàng.'
        if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': message}, status=403)
        messages.error(request, message)
        from django.shortcuts import redirect
        return redirect('/dashboard/')
    return wrapper


def _get_sales_report_filters(request):
    today = datetime.now().date()
    from_date = request.GET.get('from_date') or today.replace(day=1).strftime('%Y-%m-%d')
    to_date = request.GET.get('to_date') or today.strftime('%Y-%m-%d')
    time_group = (request.GET.get('time_group') or 'day').strip().lower()
    if time_group not in ('day', 'month', 'year'):
        time_group = 'day'
    order_scope = (request.GET.get('order_scope') or 'realized').strip().lower()
    if order_scope not in ('realized', 'all_active'):
        order_scope = 'realized'
    return {
        'from_date': from_date,
        'to_date': to_date,
        'time_group': time_group,
        'order_scope': order_scope,
        'store_id': request.GET.get('store_id') or '',
        'customer_kind': request.GET.get('customer_kind', '').strip(),
        'customer_group_id': request.GET.get('customer_group_id') or '',
        'category_id': request.GET.get('category_id') or '',
        'product_type_id': request.GET.get('product_type_id') or '',
        'profit_filter': request.GET.get('profit_filter', '').strip(),
        'customer_id': request.GET.get('customer_id') or '',
        'product_id': request.GET.get('product_id') or '',
        'salesperson': request.GET.get('salesperson', '').strip(),
        'search': request.GET.get('search', '').strip(),
        'revenue_min': _parse_sales_report_number(request.GET.get('revenue_min')),
        'revenue_max': _parse_sales_report_number(request.GET.get('revenue_max')),
        'cost_min': _parse_sales_report_number(request.GET.get('cost_min')),
        'cost_max': _parse_sales_report_number(request.GET.get('cost_max')),
        'line_profit_min': _parse_sales_report_number(request.GET.get('line_profit_min')),
        'line_profit_max': _parse_sales_report_number(request.GET.get('line_profit_max')),
        'profit_min': _parse_sales_report_number(request.GET.get('profit_min')),
        'profit_max': _parse_sales_report_number(request.GET.get('profit_max')),
    }


def _get_sales_report_time_group_meta(time_group):
    """Trả metadata gom nhóm thời gian cho báo cáo bán hàng."""
    if time_group == 'month':
        return {'label': 'Tháng', 'key_format': '%Y-%m', 'display_format': '%m/%Y'}
    if time_group == 'year':
        return {'label': 'Năm', 'key_format': '%Y', 'display_format': '%Y'}
    return {'label': 'Ngày', 'key_format': '%Y-%m-%d', 'display_format': '%d/%m/%Y'}


def _get_sales_report_filter_labels(filters):
    from customers.models import Customer, CustomerGroup
    from products.models import Product, ProductCategory
    from system_management.models import Store

    def _lookup_name(model, raw_id):
        lookup_id = _parse_filter_int(raw_id)
        if lookup_id is None:
            return str(raw_id or '').strip()
        return model.objects.filter(id=lookup_id).values_list('name', flat=True).first() or str(raw_id)

    filter_labels = []
    if filters.get('time_group'):
        filter_labels.append(f"Xem theo: {_get_sales_report_time_group_meta(filters['time_group'])['label']}")
    order_scope_label = {
        'realized': 'Đã xuất kho + Hoàn thành',
        'all_active': 'Tất cả đơn chưa hủy',
    }.get(filters.get('order_scope'))
    if order_scope_label:
        filter_labels.append(f"Phạm vi đơn: {order_scope_label}")
    if filters.get('store_id'):
        filter_labels.append(f"Cửa hàng: {_lookup_name(Store, filters['store_id'])}")
    if filters.get('customer_kind'):
        kind_label = next(
            (option['label'] for option in CUSTOMER_KIND_OPTIONS if option['value'] == filters['customer_kind']),
            filters['customer_kind'],
        )
        filter_labels.append(f"Kiểu khách: {kind_label}")
    if filters.get('customer_group_id'):
        filter_labels.append(f"Nhóm KH: {_lookup_name(CustomerGroup, filters['customer_group_id'])}")
    if filters.get('category_id'):
        filter_labels.append(f"Nhóm mặt hàng: {_lookup_name(ProductCategory, filters['category_id'])}")
    if filters.get('product_type_id'):
        filter_labels.append(f"Loại SP: {_lookup_name(ProductCategory, filters['product_type_id'])}")
    if filters.get('customer_id'):
        customer_name = _lookup_name(Customer, filters['customer_id'])
        filter_labels.append(f"Khách hàng: {customer_name}")
    if filters.get('product_id'):
        product_name = _lookup_name(Product, filters['product_id'])
        filter_labels.append(f"Mặt hàng: {product_name}")
    if filters.get('salesperson'):
        filter_labels.append(f"Nhân viên: {filters['salesperson']}")
    if filters.get('search'):
        filter_labels.append(f"Từ khóa: {filters['search']}")
    if filters.get('profit_filter'):
        profit_label = {
            'profit': 'Có lãi',
            'loss': 'Báo lỗ',
        }.get(filters['profit_filter'], filters['profit_filter'])
        filter_labels.append(f"Lợi nhuận: {profit_label}")
    for key, label in (
        ('revenue_min', 'DT từ'),
        ('revenue_max', 'DT đến'),
        ('cost_min', 'GV từ'),
        ('cost_max', 'GV đến'),
        ('line_profit_min', 'LN dòng từ'),
        ('line_profit_max', 'LN dòng đến'),
        ('profit_min', 'LN gộp từ'),
        ('profit_max', 'LN gộp đến'),
    ):
        if filters.get(key) is not None:
            value = filters[key]
            filter_labels.append(f"{label}: {int(value) if float(value).is_integer() else value}")
    return filter_labels


def _filter_sales_returns_by_scope(queryset, request):
    """Lọc phiếu trả theo store hợp lệ.

    Ưu tiên liên kết order -> store. Với dữ liệu dev/legacy thiếu order, fallback sang
    warehouse.store rồi customer.store để không làm rơi dữ liệu vẫn còn suy luận được.
    """
    if request.user.is_superuser:
        return queryset.none()
    managed_ids = get_managed_store_ids(request.user)
    if not managed_ids:
        return queryset.none()
    return queryset.filter(
        Q(order__store_id__in=managed_ids) |
        Q(order__isnull=True, warehouse__store_id__in=managed_ids) |
        Q(order__isnull=True, warehouse__isnull=True, customer__store_id__in=managed_ids)
    ).distinct()


def _get_salesperson_filter_options(request, store_id=''):
    """Danh sách nhân viên cho filter báo cáo bán hàng trong phạm vi store hợp lệ."""
    from django.contrib.auth.models import User

    managed_ids = get_managed_store_ids(request.user)
    if not managed_ids:
        return []

    scoped_store_ids = list(managed_ids)
    if store_id:
        try:
            selected_store_id = int(store_id)
        except (TypeError, ValueError):
            return []
        if selected_store_id not in scoped_store_ids:
            return []
        scoped_store_ids = [selected_store_id]

    names = set()

    users = User.objects.filter(
        is_active=True,
        profile__store_id__in=scoped_store_ids,
    ).distinct().order_by('last_name', 'first_name', 'username')
    for user in users:
        name = (user.get_full_name() or user.username or '').strip()
        if name:
            names.add(name)

    legacy_salespersons = Order.objects.filter(
        store_id__in=scoped_store_ids,
    ).exclude(status=6).exclude(
        salesperson__isnull=True
    ).exclude(salesperson='').values_list('salesperson', flat=True)
    for name in legacy_salespersons:
        normalized = (name or '').strip()
        if normalized:
            names.add(normalized)

    return sorted(names, key=lambda value: value.casefold())


def _build_sales_report_payload(request, include_filter_options=True):
    from customers.models import CustomerGroup, Customer
    from products.models import ProductCategory, Product, GoodsReceipt
    from system_management.models import Store

    filters = _get_sales_report_filters(request)
    line_profit_scope = filters['line_profit_min'] is not None or filters['line_profit_max'] is not None
    item_scope = bool(
        filters['category_id'] or filters['product_type_id'] or filters['product_id'] or line_profit_scope
    )

    def _matches_metric_filters(row):
        revenue = float(row.get('revenue', row.get('amount', 0)) or 0)
        cost = float(row.get('cost', 0) or 0)
        profit = float(row.get('profit', revenue - cost) or 0)
        if filters['revenue_min'] is not None and revenue < filters['revenue_min']:
            return False
        if filters['revenue_max'] is not None and revenue > filters['revenue_max']:
            return False
        if filters['cost_min'] is not None and cost < filters['cost_min']:
            return False
        if filters['cost_max'] is not None and cost > filters['cost_max']:
            return False
        if filters['profit_min'] is not None and profit < filters['profit_min']:
            return False
        if filters['profit_max'] is not None and profit > filters['profit_max']:
            return False
        return True

    def _matches_line_profit_filters(row):
        line_profit = float(row.get('line_profit', row.get('profit', 0)) or 0)
        if filters['line_profit_min'] is not None and line_profit < filters['line_profit_min']:
            return False
        if filters['line_profit_max'] is not None and line_profit > filters['line_profit_max']:
            return False
        return True

    def _effective_product_unit_cost(product):
        if not product:
            return 0.0
        for candidate in (product.cost_price, product.import_price):
            value = float(candidate or 0)
            if value > 0:
                return value
        if product.is_combo:
            combo_cost = 0.0
            for combo_item in product.combo_items.select_related('product').all():
                component_cost = float(
                    combo_item.product.cost_price
                    or combo_item.product.import_price
                    or 0
                )
                combo_cost += component_cost * float(combo_item.quantity or 0)
            if combo_cost > 0:
                return combo_cost
        return 0.0

    def _effective_item_unit_cost(item):
        candidates = [item.cost_price]
        if item.variant_id:
            candidates.extend([item.variant.cost_price, item.variant.import_price])
        for candidate in candidates:
            value = float(candidate or 0)
            if value > 0:
                return value
        return _effective_product_unit_cost(item.product if item.product_id else None)

    orders_qs = Order.objects.filter(
        order_date__gte=filters['from_date'],
        order_date__lte=filters['to_date'],
    )
    if filters['order_scope'] == 'all_active':
        orders_qs = orders_qs.exclude(status=6)
    else:
        orders_qs = orders_qs.filter(status__in=[4, 5])
    orders_qs = orders_qs.select_related(
        'customer', 'customer__group', 'warehouse', 'store'
    )
    orders_qs = filter_by_store(orders_qs, request)

    if filters['store_id']:
        orders_qs = orders_qs.filter(store_id=filters['store_id'])
    if filters['customer_kind']:
        orders_qs = orders_qs.filter(_get_sales_report_customer_kind_q(filters['customer_kind']))
    if filters['customer_group_id']:
        orders_qs = orders_qs.filter(customer__group_id=filters['customer_group_id'])
    if filters['customer_id']:
        orders_qs = orders_qs.filter(customer_id=filters['customer_id'])
    if filters['salesperson']:
        orders_qs = orders_qs.filter(salesperson__iexact=filters['salesperson'])
    if filters['category_id']:
        orders_qs = orders_qs.filter(_get_product_category_scope_q(filters['category_id'], 'items__product__'))
    if filters['product_type_id']:
        orders_qs = orders_qs.filter(_get_product_category_direct_q(filters['product_type_id'], 'items__product__'))
    if filters['product_id']:
        orders_qs = orders_qs.filter(items__product_id=filters['product_id'])
    if filters['search']:
        search = filters['search']
        orders_qs = orders_qs.filter(
            Q(code__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(customer__phone__icontains=search) |
            Q(tags__icontains=search) |
            Q(note__icontains=search) |
            Q(salesperson__icontains=search) |
            Q(items__product__name__icontains=search) |
            Q(items__product__code__icontains=search)
        )
    orders_qs = orders_qs.distinct()

    orders_list = list(orders_qs.order_by('-order_date', '-id'))

    order_items_qs = OrderItem.objects.filter(order__in=orders_qs).select_related(
        'product', 'product__category', 'product__category__parent', 'variant',
        'order', 'order__customer', 'order__customer__group', 'order__created_by'
    )
    if filters['category_id']:
        order_items_qs = order_items_qs.filter(_get_product_category_scope_q(filters['category_id'], 'product__'))
    if filters['product_type_id']:
        order_items_qs = order_items_qs.filter(_get_product_category_direct_q(filters['product_type_id'], 'product__'))
    if filters['product_id']:
        order_items_qs = order_items_qs.filter(product_id=filters['product_id'])

    order_items = list(order_items_qs)
    adjusted_item_rows = []
    for item in order_items:
        base_total = float(item.order.total_amount or 0)
        final_total = max(float(item.order.final_amount or 0), 0)
        line_revenue = float(item.total_price or 0)
        line_cost = _effective_item_unit_cost(item) * float(item.quantity or 0)
        if base_total > 0:
            adjusted_revenue = line_revenue * final_total / base_total
        else:
            adjusted_revenue = line_revenue

        product = item.product
        order = item.order
        category = product.category if product else None
        root_category = category.parent if category and category.parent_id else category
        product_type = category if category and category.parent_id else None
        line_profit = adjusted_revenue - line_cost
        salesperson = order.salesperson or order.creator_name or ''
        if not salesperson and order.created_by_id:
            salesperson = order.created_by.get_full_name() or order.created_by.username
        adjusted_item_rows.append({
            'id': item.id,
            'order_id': item.order_id,
            'order_code': order.code,
            'date': order.order_date.strftime('%d/%m/%Y') if order.order_date else '',
            'date_raw': order.order_date.strftime('%Y-%m-%d') if order.order_date else '',
            'customer_name': order.customer.name if order.customer else '',
            'salesperson': salesperson,
            'product_name': product.name if product else (item.item_name or 'Dịch vụ'),
            'sku': item.variant.sku if item.variant else (product.code if product else 'DV'),
            'category_name': root_category.name if root_category else '',
            'product_type_name': product_type.name if product_type else '',
            'quantity': float(item.quantity or 0),
            'goods_amount': line_revenue,
            'revenue': adjusted_revenue,
            'cost': line_cost,
            'line_profit': line_profit,
        })

    loss_items_by_order = defaultdict(list)
    for item_row in adjusted_item_rows:
        if item_row['line_profit'] >= 0:
            continue
        quantity = float(item_row['quantity'] or 0)
        unit_revenue = item_row['revenue'] / quantity if quantity > 0 else item_row['revenue']
        unit_cost = item_row['cost'] / quantity if quantity > 0 else item_row['cost']
        loss_items_by_order[item_row['order_id']].append({
            'product_name': item_row['product_name'],
            'sku': item_row['sku'],
            'quantity': quantity,
            'unit_revenue': unit_revenue,
            'unit_cost': unit_cost,
            'loss_amount': abs(item_row['line_profit']),
        })

    if line_profit_scope:
        adjusted_item_rows = [row for row in adjusted_item_rows if _matches_line_profit_filters(row)]

    order_item_map = defaultdict(lambda: {'goods_amount': 0.0, 'revenue': 0.0, 'cost': 0.0})
    for item_row in adjusted_item_rows:
        order_item_map[item_row['order_id']]['goods_amount'] += item_row['goods_amount']
        order_item_map[item_row['order_id']]['revenue'] += item_row['revenue']
        order_item_map[item_row['order_id']]['cost'] += item_row['cost']

    order_rows = []
    for order in orders_list:
        if item_scope and order.id not in order_item_map:
            continue
        item_totals = order_item_map.get(order.id, {'goods_amount': 0, 'revenue': 0, 'cost': 0})
        goods_amount = item_totals['goods_amount'] if item_scope else float(max(order.total_amount or 0, 0))
        revenue = item_totals['revenue'] if item_scope else float(max(order.final_amount or 0, 0))
        cost = item_totals['cost']
        order_goods_total = float(max(order.total_amount or 0, 0))
        scope_ratio = (goods_amount / order_goods_total) if item_scope and order_goods_total > 0 else 1.0
        discount_amount = float(order.discount_amount or 0) * scope_ratio
        shipping_fee = float(order.shipping_fee or 0) * scope_ratio
        other_fee = float(order.other_fee or 0) * scope_ratio

        if item_scope:
            base_amount = float(order.final_amount or 0)
            if base_amount > 0:
                paid = min(float(order.paid_amount or 0) * revenue / base_amount, revenue)
            else:
                paid = 0
        else:
            paid = float(order.paid_amount or 0)

        profit = revenue - cost
        loss_products = loss_items_by_order.get(order.id, [])
        customer_kind, customer_kind_label = _classify_sales_report_customer_kind(order.customer)
        order_rows.append({
            'id': order.id,
            'code': order.code,
            'date': order.order_date.strftime('%d/%m/%Y') if order.order_date else '',
            'date_raw': order.order_date.strftime('%Y-%m-%d') if order.order_date else '',
            'customer': order.customer.name if order.customer else '',
            'customer_id': order.customer_id,
            'customer_kind': customer_kind,
            'customer_kind_label': customer_kind_label,
            'customer_group': order.customer.group.name if order.customer and order.customer.group else '',
            'customer_group_id': order.customer.group_id if order.customer else None,
            'store_id': order.store_id,
            'store_name': order.store.name if order.store else '',
            'salesperson': order.salesperson or '',
            'goods_amount': goods_amount,
            'discount_amount': discount_amount,
            'shipping_fee': shipping_fee,
            'other_fee': other_fee,
            'revenue': revenue,
            'paid': paid,
            'debt': revenue - paid,
            'cost': cost,
            'profit': profit,
            'is_loss': profit < 0,
            'loss_products': loss_products,
            'loss_product_names': ', '.join(
                row['product_name'] for row in loss_products
            ),
            'status': order.status,
            'status_display': order.get_status_display(),
            'payment_status': order.payment_status,
            'payment_status_display': order.get_payment_status_display(),
        })

    if filters['profit_filter'] == 'loss':
        order_rows = [row for row in order_rows if row['profit'] < 0]
    elif filters['profit_filter'] == 'profit':
        order_rows = [row for row in order_rows if row['profit'] >= 0]
    order_rows = [row for row in order_rows if _matches_metric_filters(row)]

    order_row_map = {row['id']: row for row in order_rows}

    allowed_order_ids = [row['id'] for row in order_rows]
    if allowed_order_ids:
        order_items_qs = order_items_qs.filter(order_id__in=allowed_order_ids)
    else:
        order_items_qs = order_items_qs.none()

    total_orders = len(order_rows)
    total_goods_amount = sum(row['goods_amount'] for row in order_rows)
    total_revenue = sum(row['revenue'] for row in order_rows)
    total_debt = sum(row['debt'] for row in order_rows)
    total_cost = sum(row['cost'] for row in order_rows)
    total_profit = sum(row['profit'] for row in order_rows)
    loss_count = len([row for row in order_rows if row['is_loss']])

    allowed_order_id_set = set(allowed_order_ids)
    product_map = {}
    category_map = {}
    sku_details = []
    for item_row in adjusted_item_rows:
        if item_row['order_id'] not in allowed_order_id_set:
            continue

        product_key = (item_row['product_name'], item_row['category_name'], item_row['product_type_name'])
        if product_key not in product_map:
            product_map[product_key] = {
                'name': item_row['product_name'],
                'category': item_row['category_name'],
                'product_type': item_row['product_type_name'],
                'qty': 0,
                'amount': 0,
                'cost': 0,
            }
        product_map[product_key]['qty'] += item_row['quantity']
        product_map[product_key]['amount'] += item_row['revenue']
        product_map[product_key]['cost'] += item_row['cost']

        category_key = item_row['category_name'] or 'Không DM'
        if category_key not in category_map:
            category_map[category_key] = {
                'name': category_key,
                'qty': 0,
                'revenue': 0,
                'cost': 0,
            }
        category_map[category_key]['qty'] += item_row['quantity']
        category_map[category_key]['revenue'] += item_row['revenue']
        category_map[category_key]['cost'] += item_row['cost']

        if _matches_metric_filters(item_row):
            sku_details.append({
                'id': item_row['id'],
                'date': item_row['date'],
                'date_raw': item_row['date_raw'],
                'customer': item_row['customer_name'],
                'product_name': item_row['product_name'],
                'sku': item_row['sku'],
                'order_id': item_row['order_id'],
                'order_code': item_row['order_code'],
                'salesperson': item_row['salesperson'],
                'quantity': item_row['quantity'],
                'revenue': item_row['revenue'],
                'cost': item_row['cost'],
                'profit': item_row['line_profit'],
                'line_profit': item_row['line_profit'],
            })

    sku_details = sorted(
        sku_details,
        key=lambda row: (row['date_raw'], row['order_id'], row['id']),
        reverse=True,
    )

    returns_qs = OrderReturn.objects.filter(
        return_date__gte=filters['from_date'],
        return_date__lte=filters['to_date'],
    ).exclude(status=3).select_related(
        'order', 'order__store', 'customer', 'customer__group', 'customer__store', 'warehouse', 'warehouse__store'
    )
    returns_qs = _filter_sales_returns_by_scope(returns_qs, request)
    if filters['store_id']:
        returns_qs = returns_qs.filter(
            Q(order__store_id=filters['store_id']) |
            Q(order__isnull=True, warehouse__store_id=filters['store_id']) |
            Q(order__isnull=True, warehouse__isnull=True, customer__store_id=filters['store_id'])
        )
    if filters['customer_kind']:
        returns_qs = returns_qs.filter(_get_sales_report_return_customer_kind_q(filters['customer_kind']))
    if filters['customer_group_id']:
        returns_qs = returns_qs.filter(
            Q(order__customer__group_id=filters['customer_group_id']) |
            Q(order__isnull=True, customer__group_id=filters['customer_group_id'])
        )
    if filters['customer_id']:
        returns_qs = returns_qs.filter(
            Q(order__customer_id=filters['customer_id']) |
            Q(order__isnull=True, customer_id=filters['customer_id'])
        )
    if filters['salesperson']:
        returns_qs = returns_qs.filter(order__salesperson__iexact=filters['salesperson'])
    if filters['search']:
        search = filters['search']
        returns_qs = returns_qs.filter(
            Q(code__icontains=search) |
            Q(order__code__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(reason__icontains=search)
        )
    # Phiếu trả có đơn gốc phải đi theo đúng phạm vi đơn đang được báo cáo.
    # Phiếu legacy thiếu đơn gốc vẫn được giữ lại nếu suy luận được đúng cửa hàng.
    returns_qs = returns_qs.filter(Q(order_id__in=allowed_order_ids) | Q(order__isnull=True))

    returns_total = 0
    returns_count = 0
    returns_by_date = {}
    return_cost_total = 0
    return_cost_by_date = {}

    return_items_qs = OrderReturnItem.objects.filter(order_return__in=returns_qs)
    if filters['category_id']:
        return_items_qs = return_items_qs.filter(_get_product_category_scope_q(filters['category_id'], 'product__'))
    if filters['product_type_id']:
        return_items_qs = return_items_qs.filter(_get_product_category_direct_q(filters['product_type_id'], 'product__'))
    if filters['product_id']:
        return_items_qs = return_items_qs.filter(product_id=filters['product_id'])
    return_items_for_breakdown = list(return_items_qs.select_related(
        'product',
        'order_return',
        'order_return__order',
        'order_return__customer',
        'order_return__order__store',
    ))

    if item_scope:
        returns_total = sum(float(item.total_price or 0) for item in return_items_for_breakdown)
        returns_count = len({item.order_return_id for item in return_items_for_breakdown})
        for item in return_items_for_breakdown:
            if not item.order_return.return_date:
                continue
            date_key = item.order_return.return_date.strftime('%Y-%m-%d')
            returns_by_date[date_key] = returns_by_date.get(date_key, 0) + float(item.total_price or 0)
    else:
        returns_total = float(returns_qs.aggregate(s=Sum('total_refund'))['s'] or 0)
        returns_count = returns_qs.count()
        for row in returns_qs.values('return_date').annotate(total=Sum('total_refund')):
            if not row['return_date']:
                continue
            returns_by_date[row['return_date'].strftime('%Y-%m-%d')] = float(row['total'] or 0)

    # Giá vốn hàng trả lấy theo snapshot giá vốn trên đơn gốc. Nếu dữ liệu cũ
    # thiếu snapshot thì fallback về giá vốn/import hiện có của sản phẩm.
    return_order_ids = {
        item.order_return.order_id
        for item in return_items_for_breakdown
        if item.order_return.order_id
    }
    return_product_ids = {item.product_id for item in return_items_for_breakdown if item.product_id}
    original_cost_map = defaultdict(lambda: {'quantity': 0.0, 'cost': 0.0})
    if return_order_ids and return_product_ids:
        original_items = OrderItem.objects.filter(
            order_id__in=return_order_ids,
            product_id__in=return_product_ids,
        ).select_related('product', 'variant')
        for original_item in original_items:
            quantity = float(original_item.quantity or 0)
            if quantity <= 0:
                continue
            key = (original_item.order_id, original_item.product_id)
            original_cost_map[key]['quantity'] += quantity
            original_cost_map[key]['cost'] += _effective_item_unit_cost(original_item) * quantity

    return_cost_by_return_id = {}
    return_cost_by_item_id = {}
    for item in return_items_for_breakdown:
        quantity = float(item.quantity or 0)
        order_id = item.order_return.order_id
        original_cost = original_cost_map.get((order_id, item.product_id))
        if original_cost and original_cost['quantity'] > 0:
            unit_cost = original_cost['cost'] / original_cost['quantity']
        else:
            unit_cost = _effective_product_unit_cost(item.product)
        item_return_cost = unit_cost * quantity
        return_cost_by_item_id[item.id] = item_return_cost
        return_cost_total += item_return_cost
        return_cost_by_return_id[item.order_return_id] = (
            return_cost_by_return_id.get(item.order_return_id, 0) + item_return_cost
        )
        if item.order_return.return_date:
            date_key = item.order_return.return_date.strftime('%Y-%m-%d')
            return_cost_by_date[date_key] = return_cost_by_date.get(date_key, 0) + item_return_cost

    purchases = GoodsReceipt.objects.filter(
        receipt_date__gte=filters['from_date'],
        receipt_date__lte=filters['to_date'],
    ).exclude(status=2)
    purchases = filter_by_store(purchases, request, field_name='warehouse__store')
    if filters['store_id']:
        purchases = purchases.filter(warehouse__store_id=filters['store_id'])
    total_purchases = float(purchases.aggregate(s=Sum('total_amount'))['s'] or 0)

    time_group_meta = _get_sales_report_time_group_meta(filters['time_group'])
    daily_map = {}
    for row in sorted(order_rows, key=lambda item: item['date_raw'] or ''):
        if not row['date_raw']:
            continue
        date_obj = datetime.strptime(row['date_raw'], '%Y-%m-%d')
        key = date_obj.strftime(time_group_meta['key_format'])
        if key not in daily_map:
            daily_map[key] = {
                'date': date_obj.strftime(time_group_meta['display_format']),
                'count': 0,
                'goods_amount': 0,
                'revenue': 0,
                'gross_cost': 0,
                'return_cost': 0,
                'cost': 0,
                'profit': 0,
                'returns': 0,
            }
        daily_map[key]['count'] += 1
        daily_map[key]['goods_amount'] += row['goods_amount']
        daily_map[key]['revenue'] += row['revenue']
        daily_map[key]['gross_cost'] += row['cost']
    for date_key, amount in returns_by_date.items():
        date_obj = datetime.strptime(date_key, '%Y-%m-%d')
        bucket_key = date_obj.strftime(time_group_meta['key_format'])
        bucket_label = date_obj.strftime(time_group_meta['display_format'])
        if bucket_key in daily_map:
            daily_map[bucket_key]['returns'] += amount
        else:
            daily_map[bucket_key] = {
                'date': bucket_label,
                'count': 0,
                'goods_amount': 0,
                'revenue': 0,
                'gross_cost': 0,
                'return_cost': 0,
                'cost': 0,
                'profit': 0,
                'returns': amount,
            }
    for date_key, amount in return_cost_by_date.items():
        date_obj = datetime.strptime(date_key, '%Y-%m-%d')
        bucket_key = date_obj.strftime(time_group_meta['key_format'])
        bucket_label = date_obj.strftime(time_group_meta['display_format'])
        if bucket_key not in daily_map:
            daily_map[bucket_key] = {
                'date': bucket_label,
                'count': 0,
                'goods_amount': 0,
                'revenue': 0,
                'gross_cost': 0,
                'return_cost': 0,
                'cost': 0,
                'profit': 0,
                'returns': 0,
            }
        daily_map[bucket_key]['return_cost'] += amount
    for row in daily_map.values():
        row['cost'] = row['gross_cost'] - row['return_cost']
        row['profit'] = row['revenue'] - row['returns'] - row['cost']
    daily_data = []
    for key in sorted(daily_map.keys()):
        row = daily_map[key]
        row['period_key'] = key
        daily_data.append(row)

    daily_finance_map = {}
    for row in sorted(order_rows, key=lambda item: item['date_raw'] or ''):
        date_key = row['date_raw']
        if not date_key:
            continue
        date_obj = datetime.strptime(date_key, '%Y-%m-%d')
        if date_key not in daily_finance_map:
            daily_finance_map[date_key] = {
                'date': date_obj.strftime('%d/%m/%Y'),
                'date_raw': date_key,
                'goods_amount': 0,
                'revenue': 0,
                'returns': 0,
                'net_revenue': 0,
                'gross_cost': 0,
                'return_cost': 0,
                'cost': 0,
                'gross_profit': 0,
                'gross_margin': 0,
                'net_profit': 0,
            }
        daily_finance_map[date_key]['goods_amount'] += row['goods_amount']
        daily_finance_map[date_key]['revenue'] += row['revenue']
        daily_finance_map[date_key]['gross_cost'] += row['cost']
    for date_key, amount in returns_by_date.items():
        date_obj = datetime.strptime(date_key, '%Y-%m-%d')
        if date_key not in daily_finance_map:
            daily_finance_map[date_key] = {
                'date': date_obj.strftime('%d/%m/%Y'),
                'date_raw': date_key,
                'goods_amount': 0,
                'revenue': 0,
                'returns': 0,
                'net_revenue': 0,
                'gross_cost': 0,
                'return_cost': 0,
                'cost': 0,
                'gross_profit': 0,
                'gross_margin': 0,
                'net_profit': 0,
            }
        daily_finance_map[date_key]['returns'] += amount
    for date_key, amount in return_cost_by_date.items():
        date_obj = datetime.strptime(date_key, '%Y-%m-%d')
        if date_key not in daily_finance_map:
            daily_finance_map[date_key] = {
                'date': date_obj.strftime('%d/%m/%Y'),
                'date_raw': date_key,
                'goods_amount': 0,
                'revenue': 0,
                'returns': 0,
                'net_revenue': 0,
                'gross_cost': 0,
                'return_cost': 0,
                'cost': 0,
                'gross_profit': 0,
                'gross_margin': 0,
                'net_profit': 0,
            }
        daily_finance_map[date_key]['return_cost'] += amount

    daily_finance = []
    for row in [daily_finance_map[key] for key in sorted(daily_finance_map.keys())]:
        revenue = float(row.get('revenue') or 0)
        returns = float(row.get('returns') or 0)
        gross_cost = float(row.get('gross_cost') or 0)
        return_cost = float(row.get('return_cost') or 0)
        cost = gross_cost - return_cost
        net_revenue = revenue - returns
        gross_profit = net_revenue - cost
        row['net_revenue'] = net_revenue
        row['cost'] = cost
        row['gross_profit'] = gross_profit
        row['gross_margin'] = round(gross_profit / net_revenue * 100, 1) if net_revenue > 0 else 0
        row['net_profit'] = gross_profit
        daily_finance.append(row)

    product_breakdown = [{
        'name': row['name'],
        'category': row['category'] or '',
        'product_type': row.get('product_type') or '',
        'qty': row['qty'],
        'amount': row['amount'],
        'cost': row['cost'],
        'profit': row['amount'] - row['cost'],
        'line_profit': row['amount'] - row['cost'],
    } for row in sorted(product_map.values(), key=lambda row: (-row['amount'], -row['qty'], row['name']))]
    product_breakdown = [row for row in product_breakdown if _matches_metric_filters(row)]

    category_breakdown = [{
        'name': row['name'],
        'qty': row['qty'],
        'revenue': row['revenue'],
        'cost': row['cost'],
        'profit': row['revenue'] - row['cost'],
    } for row in sorted(category_map.values(), key=lambda row: (-row['revenue'], row['name']))]
    category_breakdown = [row for row in category_breakdown if _matches_metric_filters(row)]

    customer_map = {}
    customer_kind_map = {}
    group_map = {}
    staff_map = {}
    store_map = {}
    for row in order_rows:
        customer_key = row['customer_id'] or ('guest:' + (row['customer'] or 'Khách lẻ'))
        if customer_key not in customer_map:
            customer_map[customer_key] = {
                'name': row['customer'] or 'Khách lẻ',
                'customer_kind': row['customer_kind'],
                'customer_kind_label': row['customer_kind_label'],
                'group': row['customer_group'] or '',
                'orders': 0,
                'amount': 0,
                'cost': 0,
                'profit': 0,
                'paid': 0,
                'debt': 0,
            }
        customer_map[customer_key]['orders'] += 1
        customer_map[customer_key]['amount'] += row['revenue']
        customer_map[customer_key]['cost'] += row['cost']
        customer_map[customer_key]['profit'] += row['profit']
        customer_map[customer_key]['paid'] += row['paid']
        customer_map[customer_key]['debt'] += row['debt']

        customer_kind_key = row['customer_kind']
        if customer_kind_key not in customer_kind_map:
            customer_kind_map[customer_kind_key] = {
                'key': customer_kind_key,
                'name': row['customer_kind_label'],
                'orders': 0,
                'amount': 0,
                'cost': 0,
                'profit': 0,
                'paid': 0,
                'debt': 0,
            }
        customer_kind_map[customer_kind_key]['orders'] += 1
        customer_kind_map[customer_kind_key]['amount'] += row['revenue']
        customer_kind_map[customer_kind_key]['cost'] += row['cost']
        customer_kind_map[customer_kind_key]['profit'] += row['profit']
        customer_kind_map[customer_kind_key]['paid'] += row['paid']
        customer_kind_map[customer_kind_key]['debt'] += row['debt']

        group_name = row['customer_group'] or 'Không nhóm'
        if group_name not in group_map:
            group_map[group_name] = {
                'name': group_name,
                'orders': 0,
                'amount': 0,
                'cost': 0,
                'profit': 0,
                'paid': 0,
                'debt': 0,
            }
        group_map[group_name]['orders'] += 1
        group_map[group_name]['amount'] += row['revenue']
        group_map[group_name]['cost'] += row['cost']
        group_map[group_name]['profit'] += row['profit']
        group_map[group_name]['paid'] += row['paid']
        group_map[group_name]['debt'] += row['debt']

        staff_name = row['salesperson'] or '(Chưa gán NV)'
        if staff_name not in staff_map:
            staff_map[staff_name] = {
                'salesperson': staff_name,
                'order_count': 0,
                'revenue': 0,
                'cost': 0,
                'profit': 0,
                'returns_amount': 0,
            }
        staff_map[staff_name]['order_count'] += 1
        staff_map[staff_name]['revenue'] += row['revenue']
        staff_map[staff_name]['cost'] += row['cost']
        staff_map[staff_name]['profit'] += row['profit']

        store_key = row['store_id'] or 0
        if store_key not in store_map:
            store_map[store_key] = {
                'store_id': row['store_id'],
                'store_name': row['store_name'] or 'Chưa gán cửa hàng',
                'orders': 0,
                'revenue': 0,
                'cost': 0,
                'profit': 0,
                'debt': 0,
                'paid': 0,
            }
        store_map[store_key]['orders'] += 1
        store_map[store_key]['revenue'] += row['revenue']
        store_map[store_key]['cost'] += row['cost']
        store_map[store_key]['profit'] += row['profit']
        store_map[store_key]['debt'] += row['debt']
        store_map[store_key]['paid'] += row['paid']

    if returns_qs.exists():
        for ret in returns_qs.select_related('order'):
            staff_name = (ret.order.salesperson if ret.order else '') or '(Chưa gán NV)'
            if staff_name not in staff_map:
                staff_map[staff_name] = {
                    'salesperson': staff_name,
                    'order_count': 0,
                    'revenue': 0,
                    'cost': 0,
                    'profit': 0,
                    'returns_amount': 0,
                }
            if item_scope:
                scoped_return_items = OrderReturnItem.objects.filter(order_return=ret)
                if filters['category_id']:
                    scoped_return_items = scoped_return_items.filter(
                        _get_product_category_scope_q(filters['category_id'], 'product__')
                    )
                if filters['product_type_id']:
                    scoped_return_items = scoped_return_items.filter(
                        _get_product_category_direct_q(filters['product_type_id'], 'product__')
                    )
                if filters['product_id']:
                    scoped_return_items = scoped_return_items.filter(product_id=filters['product_id'])
                ret_amount = float(scoped_return_items.aggregate(s=Sum('total_price'))['s'] or 0)
            else:
                ret_amount = float(ret.total_refund or 0)
            staff_map[staff_name]['returns_amount'] += ret_amount

    customer_breakdown = sorted(customer_map.values(), key=lambda row: (-row['amount'], -row['orders'], row['name']))
    customer_breakdown = [row for row in customer_breakdown if _matches_metric_filters(row)][:50]
    top_customers = customer_breakdown[:5]
    group_breakdown = sorted(group_map.values(), key=lambda row: (-row['amount'], row['name']))
    group_breakdown = [row for row in group_breakdown if _matches_metric_filters(row)]
    customer_kind_breakdown = sorted(customer_kind_map.values(), key=lambda row: (-row['amount'], row['name']))
    customer_kind_breakdown = [row for row in customer_kind_breakdown if _matches_metric_filters(row)]
    for row in customer_breakdown:
        row['contribution'] = round(row['amount'] / total_revenue * 100, 1) if total_revenue > 0 else 0
    for row in group_breakdown:
        row['contribution'] = round(row['amount'] / total_revenue * 100, 1) if total_revenue > 0 else 0
    for row in customer_kind_breakdown:
        row['contribution'] = round(row['amount'] / total_revenue * 100, 1) if total_revenue > 0 else 0

    staff_breakdown = sorted(staff_map.values(), key=lambda row: (-row['revenue'], row['salesperson']))
    staff_breakdown = [row for row in staff_breakdown if _matches_metric_filters(row)]
    for row in staff_breakdown:
        row['contribution'] = round(row['revenue'] / total_revenue * 100, 1) if total_revenue > 0 else 0

    order_status_map = {}
    payment_status_map = {}
    for row in order_rows:
        status_key = row['status_display'] or 'Khác'
        if status_key not in order_status_map:
            order_status_map[status_key] = {'name': status_key, 'count': 0, 'revenue': 0}
        order_status_map[status_key]['count'] += 1
        order_status_map[status_key]['revenue'] += row['revenue']

        payment_key = row['payment_status_display'] or 'Khác'
        if payment_key not in payment_status_map:
            payment_status_map[payment_key] = {'name': payment_key, 'count': 0, 'revenue': 0, 'debt': 0}
        payment_status_map[payment_key]['count'] += 1
        payment_status_map[payment_key]['revenue'] += row['revenue']
        payment_status_map[payment_key]['debt'] += row['debt']

    order_status_breakdown = sorted(order_status_map.values(), key=lambda row: (-row['count'], row['name']))
    payment_status_breakdown = sorted(payment_status_map.values(), key=lambda row: (-row['count'], row['name']))

    return_amount_by_return_id = {}
    return_qty_by_return_id = {}
    return_product_map = {}
    for item in return_items_for_breakdown:
        refund = float(item.total_price or 0)
        qty = float(item.quantity or 0)
        return_amount_by_return_id[item.order_return_id] = return_amount_by_return_id.get(item.order_return_id, 0) + refund
        return_qty_by_return_id[item.order_return_id] = return_qty_by_return_id.get(item.order_return_id, 0) + qty

        product_key = item.product_id or f"product:{item.product.name if item.product else 'N/A'}"
        if product_key not in return_product_map:
            return_product_map[product_key] = {
                'product_id': item.product_id,
                'name': item.product.name if item.product else 'N/A',
                'qty': 0,
                'amount': 0,
                'cost': 0,
                'return_ids': set(),
            }
        return_product_map[product_key]['qty'] += qty
        return_product_map[product_key]['amount'] += refund
        return_product_map[product_key]['cost'] += return_cost_by_item_id.get(item.id, 0)
        return_product_map[product_key]['return_ids'].add(item.order_return_id)

    return_order_rows = []
    for ret in returns_qs.select_related(
        'order', 'customer', 'warehouse', 'order__store', 'warehouse__store', 'customer__store'
    ).order_by('-return_date', '-id'):
        refund = return_amount_by_return_id.get(ret.id, float(ret.total_refund or 0))
        qty = return_qty_by_return_id.get(ret.id, 0)
        if item_scope and refund <= 0 and qty <= 0:
            continue
        order_row = order_row_map.get(ret.order_id, {})
        if ret.order and ret.order.store:
            store_name = ret.order.store.name
        elif ret.warehouse and ret.warehouse.store:
            store_name = ret.warehouse.store.name
        elif ret.customer and ret.customer.store:
            store_name = ret.customer.store.name
        else:
            store_name = 'Chưa gán cửa hàng'
        return_order_rows.append({
            'id': ret.id,
            'code': ret.code,
            'date': ret.return_date.strftime('%d/%m/%Y') if ret.return_date else '',
            'order_code': ret.order.code if ret.order else '(Thiếu đơn gốc)',
            'customer': ret.customer.name if ret.customer else 'Khách chưa gán',
            'salesperson': (ret.order.salesperson if ret.order else '') or '(Chưa gán NV)',
            'store_name': store_name,
            'qty': qty,
            'amount': refund,
            'cost': return_cost_by_return_id.get(ret.id, 0),
            'order_revenue': float(order_row.get('revenue') or (ret.order.final_amount if ret.order else 0) or 0),
            'status': ret.status,
            'status_display': ret.get_status_display(),
            'reason': ret.reason or '',
        })

    return_product_breakdown = sorted(
        [{
            'product_id': row['product_id'],
            'name': row['name'],
            'qty': row['qty'],
            'amount': row['amount'],
            'cost': row['cost'],
            'return_count': len(row['return_ids']),
        } for row in return_product_map.values()],
        key=lambda row: (-row['amount'], -row['qty'], row['name'])
    )

    top_products = product_breakdown[:10]

    managed_ids = get_managed_store_ids(request.user)
    managed_stores = Store.objects.filter(id__in=managed_ids).select_related('brand')
    has_multiple = managed_stores.count() > 1
    stores_list = [{'id': store.id, 'name': store.name, 'brand': store.brand.name if store.brand else ''} for store in managed_stores]

    store_breakdown = []
    if has_multiple and not filters['store_id']:
        store_breakdown = sorted(store_map.values(), key=lambda row: (-row['revenue'], row['store_name']))
        store_breakdown = [row for row in store_breakdown if _matches_metric_filters(row)]

    total_net_revenue = total_revenue - returns_total
    total_net_cost = total_cost - return_cost_total
    total_gross_profit = total_net_revenue - total_net_cost
    gross_margin = round(total_gross_profit / total_net_revenue * 100, 1) if total_net_revenue > 0 else 0

    payload = {
        'has_multiple_stores': has_multiple,
        'stores': stores_list,
        'summary': {
            'total_orders': total_orders,
            'total_goods_amount': total_goods_amount,
            'total_revenue': total_revenue,
            'total_net_revenue': total_net_revenue,
            'total_cost': total_net_cost,
            'total_sales_cost': total_cost,
            'total_return_cost': return_cost_total,
            'total_net_cost': total_net_cost,
            'total_order_profit': total_profit,
            'total_profit': total_gross_profit,
            'total_gross_profit': total_gross_profit,
            'total_net_profit': total_gross_profit,
            'profit_margin': gross_margin,
            'gross_margin': gross_margin,
            'total_returns': returns_total,
            'returns_count': returns_count,
            'total_debt': total_debt,
            'total_purchases': total_purchases,
            'loss_count': loss_count,
        },
        'timeline': daily_data,
        'daily': daily_data,
        'daily_finance': daily_finance,
        'time_group': filters['time_group'],
        'time_group_label': time_group_meta['label'],
        'order_details': order_rows,
        'store_breakdown': store_breakdown,
        'customer_kind_breakdown': customer_kind_breakdown,
        'group_breakdown': group_breakdown,
        'category_breakdown': category_breakdown,
        'order_status_breakdown': order_status_breakdown,
        'payment_status_breakdown': payment_status_breakdown,
        'top_products': top_products,
        'top_customers': top_customers,
        'product_breakdown': product_breakdown,
        'sku_details': sku_details,
        'customer_breakdown': customer_breakdown,
        'staff_breakdown': staff_breakdown,
        'return_orders': return_order_rows,
        'return_products': return_product_breakdown,
        'return_summary': {
            'total_returns': returns_total,
            'return_count': returns_count,
            'return_products': len(return_product_breakdown),
            'returned_qty': sum(row['qty'] for row in return_product_breakdown),
            'return_cost': return_cost_total,
            'return_rate': round(returns_total / total_revenue * 100, 1) if total_revenue > 0 else 0,
        },
        'filters_applied': filters,
    }

    if include_filter_options:
        groups = list(CustomerGroup.objects.filter(is_active=True).values('id', 'name').order_by('name'))
        categories = list(
            ProductCategory.objects.filter(is_active=True)
            .values('id', 'name', 'parent_id')
            .order_by('parent__name', 'name')
        )
        root_categories = [category for category in categories if not category['parent_id']]
        product_types = [category for category in categories if category['parent_id']]
        if filters['category_id']:
            selected_category_id = _parse_filter_int(filters['category_id'])
            if selected_category_id is not None:
                product_types = [category for category in product_types if category['parent_id'] == selected_category_id]

        category_name_map = {category['id']: category['name'] for category in categories}
        for category in product_types:
            category['parent_name'] = category_name_map.get(category['parent_id'], '')

        customers_qs = filter_by_store(Customer.objects.filter(is_active=True), request)
        products_qs = filter_by_store(Product.objects.filter(is_active=True), request)
        if filters['store_id']:
            customers_qs = customers_qs.filter(store_id=filters['store_id'])
            products_qs = products_qs.filter(store_id=filters['store_id'])
        if filters['customer_kind']:
            customers_qs = customers_qs.filter(_get_sales_report_customer_kind_q(filters['customer_kind'], ''))
        if filters['customer_group_id']:
            customers_qs = customers_qs.filter(group_id=filters['customer_group_id'])
        if filters['category_id']:
            products_qs = products_qs.filter(_get_product_category_scope_q(filters['category_id'], ''))
        if filters['product_type_id']:
            products_qs = products_qs.filter(_get_product_category_direct_q(filters['product_type_id'], ''))

        customers = list(customers_qs.values('id', 'code', 'name').order_by('name')[:300])
        products = list(products_qs.values('id', 'code', 'name').order_by('name')[:300])
        salespersons = _get_salesperson_filter_options(request, filters['store_id'])

        payload['filter_options'] = {
            'customer_kinds': CUSTOMER_KIND_OPTIONS,
            'customer_groups': groups,
            'categories': root_categories,
            'product_types': product_types,
            'customers': customers,
            'products': products,
            'salespersons': salespersons,
        }

    return payload


@login_required(login_url="/login/")
@brand_owner_required
@report_permission_required
@sales_report_privileged_required
def report_sales(request):
    """Báo cáo bán hàng"""
    context = {'active_tab': 'report_sales'}
    return render(request, "reports/report_sales.html", context)


@login_required(login_url="/login/")
@report_permission_required
@sales_report_privileged_required
def api_report_sales(request):
    """API báo cáo bán hàng — chuẩn hóa theo bộ lọc chung cho mọi tab."""
    payload = _build_sales_report_payload(request, include_filter_options=True)
    return JsonResponse({'status': 'ok', **payload})


@login_required(login_url="/login/")
@brand_owner_required
@report_permission_required
def report_purchases(request):
    from products.models import Supplier

    store_ids = get_managed_store_ids(request.user)
    suppliers = Supplier.objects.filter(
        goods_receipts__warehouse__store_id__in=store_ids,
        goods_receipts__is_deleted=False,
    ).distinct().order_by('name').values('id', 'name')
    context = {
        'active_tab': 'report_purchases',
        'suppliers': list(suppliers),
    }
    return render(request, "reports/report_purchases.html", context)


def _purchase_report_receipts(request, from_date, to_date, supplier_id=None):
    from products.models import GoodsReceipt

    receipts = GoodsReceipt.objects.filter(
        receipt_date__gte=from_date,
        receipt_date__lte=to_date,
    ).select_related('supplier', 'warehouse')
    receipts = filter_by_store(receipts, request, field_name='warehouse__store')
    if supplier_id:
        receipts = receipts.filter(supplier_id=supplier_id)
    return receipts


def _purchase_supplier_summary(receipts):
    rows = (
        receipts.filter(status=1)
        .values('supplier_id', 'supplier__name')
        .annotate(receipt_count=Count('id'), total_amount=Sum('total_amount'))
        .order_by('-total_amount', 'supplier__name')
    )
    return [{
        'supplier_id': row['supplier_id'],
        'supplier': row['supplier__name'] or 'Chưa chọn NCC',
        'receipt_count': row['receipt_count'],
        'total_amount': float(row['total_amount'] or 0),
    } for row in rows]


@login_required(login_url="/login/")
@report_permission_required
def api_report_purchases(request):
    """API báo cáo nhập hàng"""
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    today = datetime.now().date()
    if not from_date:
        from_date = today.replace(day=1).strftime('%Y-%m-%d')
    if not to_date:
        to_date = today.strftime('%Y-%m-%d')

    supplier_id = _parse_filter_int(request.GET.get('supplier_id'))
    receipts = _purchase_report_receipts(
        request,
        from_date,
        to_date,
        supplier_id=supplier_id,
    ).order_by('-receipt_date', '-id')
    supplier_summary = _purchase_supplier_summary(receipts)

    data = [{
        'id': r.id, 'code': r.code,
        'date': r.receipt_date.strftime('%d/%m/%Y') if r.receipt_date else '',
        'supplier': r.supplier.name if r.supplier else '',
        'warehouse': r.warehouse.name if r.warehouse else '',
        'total_amount': float(r.total_amount),
        'status': r.status, 'status_display': r.get_status_display(),
    } for r in receipts]

    total = sum(d['total_amount'] for d in data if d['status'] == 1)
    count = len([d for d in data if d['status'] == 1])

    return JsonResponse({
        'status': 'ok', 'data': data,
        'summary': {
            'total_amount': total,
            'total_count': count,
            'total_suppliers': sum(1 for row in supplier_summary if row['supplier_id'] is not None),
            'refreshed_at': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        },
        'supplier_summary': supplier_summary,
    })


@login_required(login_url="/login/")
@brand_owner_required
@report_permission_required
def report_inventory(request):
    context = {'active_tab': 'report_inventory'}
    return render(request, "reports/report_inventory.html", context)


@login_required(login_url="/login/")
@report_permission_required
def api_report_inventory(request):
    """API báo cáo tồn kho"""
    from products.models import ProductStock, Warehouse, ProductCategory
    from core.store_utils import filter_by_store
    warehouse_id = request.GET.get('warehouse_id')
    search = request.GET.get('search', '').strip()
    category_id = request.GET.get('category_id')
    product_type_id = request.GET.get('product_type_id')
    stock_status = request.GET.get('stock_status', '')  # positive, zero, negative

    stocks = ProductStock.objects.select_related(
        'product', 'product__category', 'product__supplier', 'warehouse',
    ).filter(
        product__is_deleted=False,
    )
    stocks = filter_by_store(stocks, request, field_name='warehouse__store')
    if warehouse_id:
        stocks = stocks.filter(warehouse_id=warehouse_id)
    if search:
        stocks = stocks.filter(
            Q(product__name__icontains=search) |
            Q(product__code__icontains=search) |
            Q(product__barcode__icontains=search)
        )
    if category_id:
        stocks = stocks.filter(
            Q(product__category_id=category_id) |
            Q(product__category__parent_id=category_id)
        )
    if product_type_id:
        stocks = stocks.filter(product__category_id=product_type_id)

    data = []
    for s in stocks:
        quantity = Decimal(str(s.quantity or 0))
        cost_price = Decimal(str(s.product.cost_price or 0))
        import_price = Decimal(str(s.product.import_price or 0))
        valuation_price, valuation_source = _inventory_valuation_unit_cost(s.product)
        # Tồn âm là chênh lệch cần xử lý, không phải tài sản âm để khấu trừ
        # khỏi giá trị của các hàng hóa thực tế đang còn trong kho.
        stock_value = max(quantity, Decimal('0')) * valuation_price
        qty = float(quantity)
        min_stock = float(s.product.min_stock or 0)
        max_stock = float(s.product.max_stock or 0)
        alert = ''
        alert_type = ''
        if qty < min_stock:
            alert = 'Dưới tối thiểu'
            alert_type = 'danger'
        elif max_stock > 0 and qty > max_stock:
            alert = 'Trên tối đa'
            alert_type = 'warning'

        data.append({
            'product_id': s.product_id,
            'product_code': s.product.code,
            'product_name': s.product.name,
            'supplier': s.product.supplier.name if s.product.supplier else '',
            'category': s.product.category.name if s.product.category else '',
            'warehouse': s.warehouse.name,
            'warehouse_id': s.warehouse_id,
            'quantity': qty,
            'min_stock': min_stock,
            'max_stock': max_stock,
            'restock_needed': max(min_stock - qty, 0) if alert_type == 'danger' else 0,
            'unit': s.product.unit or '',
            'cost_price': float(cost_price),
            'import_price': float(import_price),
            'valuation_price': float(valuation_price),
            'valuation_source': valuation_source,
            'stock_value': float(stock_value),
            'alert': alert,
            'alert_type': alert_type,
        })

    # Client-side stock status filter
    if stock_status == 'positive':
        data = [d for d in data if d['quantity'] > 0]
    elif stock_status == 'zero':
        data = [d for d in data if d['quantity'] == 0]
    elif stock_status == 'negative':
        data = [d for d in data if d['quantity'] < 0]

    warehouses_qs = Warehouse.objects.filter(is_active=True)
    warehouses_qs = filter_by_store(warehouses_qs, request)
    warehouses = [{'id': w.id, 'name': w.name} for w in warehouses_qs]

    categories_qs = ProductCategory.objects.filter(is_active=True, parent__isnull=True).order_by('name')
    categories = [{'id': c.id, 'name': c.name} for c in categories_qs]
    product_types_qs = ProductCategory.objects.filter(
        is_active=True,
        parent__isnull=False,
        parent__is_deleted=False,
    ).select_related('parent').order_by('parent__name', 'name')
    product_types = [{
        'id': item.id,
        'name': item.name,
        'parent_id': item.parent_id,
        'parent_name': item.parent.name,
    } for item in product_types_qs]

    total_value = sum(d['stock_value'] for d in data)
    total_items = sum(d['quantity'] for d in data)
    alert_count = len([d for d in data if d['alert']])
    low_stock_count = len([d for d in data if d['alert_type'] == 'danger'])
    high_stock_count = len([d for d in data if d['alert_type'] == 'warning'])

    return JsonResponse({
        'status': 'ok', 'data': data, 'warehouses': warehouses,
        'categories': categories, 'product_types': product_types,
        'summary': {
            'total_value': total_value,
            'total_items': total_items,
            'alert_count': alert_count,
            'low_stock_count': low_stock_count,
            'high_stock_count': high_stock_count,
        }
    })


@login_required(login_url="/login/")
@brand_owner_required
@report_permission_required
def report_finance(request):
    context = {'active_tab': 'report_finance'}
    return render(request, "reports/report_finance.html", context)


def _get_finance_order_queryset(request, from_date, to_date, store_id=None):
    """Các đơn hàng tạo nên số liệu đã thu và công nợ trên báo cáo tài chính."""
    orders = Order.objects.select_related('customer', 'store').filter(
        order_date__gte=from_date,
        order_date__lte=to_date,
    ).exclude(status=6)
    orders = filter_by_store(orders, request)
    if store_id:
        orders = orders.filter(store_id=store_id)
    return orders


def _with_positive_order_debt(orders):
    """Chỉ giữ đơn còn nợ và tính số nợ theo từng đơn, không để đơn dư tiền bù trừ."""
    return orders.filter(final_amount__gt=F('paid_amount')).annotate(
        debt_amount=ExpressionWrapper(
            F('final_amount') - F('paid_amount'),
            output_field=DecimalField(max_digits=18, decimal_places=0),
        ),
    )


@login_required(login_url="/login/")
@brand_owner_required
@report_permission_required
def report_finance_order_debt(request):
    """Bảng chi tiết các đơn hàng còn công nợ trong kỳ báo cáo."""
    today = datetime.now().date()
    from_date = parse_date(request.GET.get('from_date') or '') or today.replace(day=1)
    to_date = parse_date(request.GET.get('to_date') or '') or today
    if from_date > to_date:
        from_date, to_date = to_date, from_date

    store_id = _parse_filter_int(request.GET.get('store_id'))
    keyword = (request.GET.get('q') or '').strip()[:100]

    orders = _with_positive_order_debt(
        _get_finance_order_queryset(request, from_date, to_date, store_id),
    )
    if keyword:
        orders = orders.filter(
            Q(code__icontains=keyword)
            | Q(customer__code__icontains=keyword)
            | Q(customer__name__icontains=keyword)
            | Q(customer__phone__icontains=keyword)
            | Q(shipping_phone__icontains=keyword)
        )

    totals = orders.aggregate(
        order_count=Count('id'),
        final_amount=Sum('final_amount'),
        paid_amount=Sum('paid_amount'),
        total_debt_amount=Sum('debt_amount'),
    )
    totals['debt_amount'] = totals.pop('total_debt_amount') or Decimal('0')
    for key in ('final_amount', 'paid_amount'):
        totals[key] = totals[key] or Decimal('0')

    debt_descending = (F('final_amount') - F('paid_amount')).desc()
    paginator = Paginator(orders.order_by(debt_descending, '-order_date', '-id'), 30)
    page_obj = paginator.get_page(request.GET.get('page'))

    from system_management.models import Store
    stores = Store.objects.filter(
        id__in=get_managed_store_ids(request.user),
    ).select_related('brand').order_by('name', 'id')

    context = {
        'active_tab': 'report_finance',
        'page_obj': page_obj,
        'stores': stores,
        'totals': totals,
        'filters': {
            'from_date': from_date.isoformat(),
            'to_date': to_date.isoformat(),
            'store_id': store_id,
            'q': keyword,
            'sort': 'debt_desc',
        },
    }
    return render(request, 'reports/report_finance_order_debt.html', context)


def _get_finance_report_querysets(request, from_date, to_date, store_id=None):
    """Lấy đúng các chứng từ tạo nên báo cáo tài chính.

    Tổng chi trên báo cáo được cấu hình bằng tổng phiếu chi cộng tổng hàng
    nhập. Dùng chung hàm này cho API và Excel để phạm vi ngày/cửa hàng/trạng
    thái của hai đầu ra luôn giống nhau.
    """
    from finance.models import Payment, Receipt
    from products.models import GoodsReceipt

    receipts = Receipt.objects.filter(
        receipt_date__gte=from_date,
        receipt_date__lte=to_date,
        status=1,
    )
    receipts = filter_by_store(receipts, request)

    payments = Payment.objects.filter(
        payment_date__gte=from_date,
        payment_date__lte=to_date,
        status=1,
    )
    payments = filter_by_store(payments, request)

    goods_receipts = GoodsReceipt.objects.filter(
        receipt_date__gte=from_date,
        receipt_date__lte=to_date,
        status=1,
    )
    goods_receipts = filter_by_store(
        goods_receipts,
        request,
        field_name='warehouse__store',
    )

    if store_id:
        receipts = receipts.filter(store_id=store_id)
        payments = payments.filter(store_id=store_id)
        goods_receipts = goods_receipts.filter(warehouse__store_id=store_id)

    return receipts, payments, goods_receipts


@login_required(login_url="/login/")
@report_permission_required
def api_report_finance(request):
    """API báo cáo tài chính — hỗ trợ filter theo store + breakdown"""
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    store_id = request.GET.get('store_id')
    today = datetime.now().date()
    if not from_date:
        from_date = today.replace(day=1).strftime('%Y-%m-%d')
    if not to_date:
        to_date = today.strftime('%Y-%m-%d')

    from finance.models import Payment, Receipt
    from products.models import GoodsReceipt

    receipts, payments, goods_receipts = _get_finance_report_querysets(
        request,
        from_date,
        to_date,
        store_id,
    )

    # Phiếu thu (hoàn thành)
    total_income = float(receipts.aggregate(s=Sum('amount'))['s'] or 0)

    # Thu theo danh mục
    income_by_cat = receipts.values('category__name').annotate(
        amount=Sum('amount')
    ).order_by('-amount')

    # Tổng chi = phiếu chi hoàn thành + phiếu nhập hoàn thành.
    payment_expense = float(payments.aggregate(s=Sum('amount'))['s'] or 0)
    goods_receipt_expense = float(
        goods_receipts.aggregate(s=Sum('total_amount'))['s'] or 0
    )
    total_expense = payment_expense + goods_receipt_expense

    # Chi theo danh mục
    expense_by_cat = payments.values('category__name').annotate(
        amount=Sum('amount')
    ).order_by('-amount')

    # Doanh thu từ đơn hàng
    orders_revenue = _get_finance_order_queryset(
        request,
        from_date,
        to_date,
        store_id,
    )
    order_revenue = float(orders_revenue.aggregate(s=Sum('paid_amount'))['s'] or 0)
    order_debt = float(
        _with_positive_order_debt(orders_revenue).aggregate(s=Sum('debt_amount'))['s'] or 0
    )

    rows = []
    for c in income_by_cat:
        rows.append({'name': c['category__name'] or 'Khác', 'income': float(c['amount'] or 0), 'expense': 0})
    for c in expense_by_cat:
        existing = next((r for r in rows if r['name'] == (c['category__name'] or 'Khác')), None)
        if existing:
            existing['expense'] = float(c['amount'] or 0)
        else:
            rows.append({'name': c['category__name'] or 'Khác', 'income': 0, 'expense': float(c['amount'] or 0)})

    # Đưa hàng nhập vào bảng danh mục để tổng bảng và biểu đồ khớp Tổng chi.
    if goods_receipt_expense:
        goods_receipt_category = 'Hàng nhập (phiếu nhập)'
        existing = next((r for r in rows if r['name'] == goods_receipt_category), None)
        if existing:
            existing['expense'] += goods_receipt_expense
        else:
            rows.append({
                'name': goods_receipt_category,
                'income': 0,
                'expense': goods_receipt_expense,
            })

    # === STORE BREAKDOWN ===
    from core.store_utils import get_managed_store_ids
    from system_management.models import Store
    managed_ids = get_managed_store_ids(request.user)
    managed_stores = Store.objects.filter(id__in=managed_ids).select_related('brand')
    has_multiple = managed_stores.count() > 1

    stores_list = [{'id': s.id, 'name': s.name, 'brand': s.brand.name if s.brand else ''} for s in managed_stores]

    store_breakdown = []
    if has_multiple and not store_id:
        for st in managed_stores:
            st_receipts = Receipt.objects.filter(
                receipt_date__gte=from_date, receipt_date__lte=to_date, status=1, store=st
            )
            st_payments = Payment.objects.filter(
                payment_date__gte=from_date, payment_date__lte=to_date, status=1, store=st
            )
            st_goods_receipts = GoodsReceipt.objects.filter(
                receipt_date__gte=from_date,
                receipt_date__lte=to_date,
                status=1,
                warehouse__store=st,
            )
            st_income = float(st_receipts.aggregate(s=Sum('amount'))['s'] or 0)
            st_payment_expense = float(st_payments.aggregate(s=Sum('amount'))['s'] or 0)
            st_goods_receipt_expense = float(
                st_goods_receipts.aggregate(s=Sum('total_amount'))['s'] or 0
            )
            st_expense = st_payment_expense + st_goods_receipt_expense
            store_breakdown.append({
                'store_id': st.id,
                'store_name': st.name,
                'brand_name': st.brand.name if st.brand else '',
                'income': st_income,
                'payment_expense': st_payment_expense,
                'goods_receipt_expense': st_goods_receipt_expense,
                'expense': st_expense,
                'net': st_income - st_expense,
            })

    return JsonResponse({
        'status': 'ok',
        'has_multiple_stores': has_multiple,
        'stores': stores_list,
        'summary': {
            'total_income': total_income,
            'payment_expense': payment_expense,
            'goods_receipt_expense': goods_receipt_expense,
            'total_expense': total_expense,
            'net_profit': total_income - total_expense,
            'order_revenue': order_revenue,
            'order_debt': order_debt,
            'income_cash': float(receipts.filter(payment_method=1).aggregate(s=Sum('amount'))['s'] or 0),
            'income_transfer': float(receipts.filter(payment_method=2).aggregate(s=Sum('amount'))['s'] or 0),
            'expense_cash': float(payments.filter(payment_method=1).aggregate(s=Sum('amount'))['s'] or 0),
            'expense_transfer': float(payments.filter(payment_method=2).aggregate(s=Sum('amount'))['s'] or 0),
        },
        'categories': rows,
        'store_breakdown': store_breakdown,
    })


@login_required(login_url="/login/")
@brand_owner_required
@report_permission_required
def report_customers(request):
    context = {'active_tab': 'report_customers'}
    return render(request, "reports/report_customers.html", context)


@login_required(login_url="/login/")
@report_permission_required
def api_report_customers(request):
    """API báo cáo khách hàng — hỗ trợ filter theo store"""
    from customers.models import Customer
    store_id = request.GET.get('store_id')

    customers = Customer.objects.filter(is_active=True).select_related('group', 'store')
    customers = filter_by_store(customers, request)
    if store_id:
        customers = customers.filter(store_id=store_id)

    data = []
    for c in customers:
        orders = Order.objects.filter(customer=c).exclude(status=6)
        order_count = orders.count()
        total = float(orders.aggregate(s=Sum('final_amount'))['s'] or 0)
        paid = float(orders.aggregate(s=Sum('paid_amount'))['s'] or 0)
        debt = total - paid
        last_order = orders.order_by('-order_date').first()
        last_date = last_order.order_date.strftime('%d/%m/%Y') if last_order else ''

        data.append({
            'code': c.code, 'name': c.name,
            'group': c.group.name if c.group else '',
            'phone': c.phone or '',
            'email': c.email or '',
            'store_id': c.store_id,
            'store_name': c.store.name if c.store else '',
            'order_count': order_count,
            'total_purchased': total,
            'total_debt': debt,
            'last_order_date': last_date,
        })

    data.sort(key=lambda x: -x['total_purchased'])
    total_revenue = sum(d['total_purchased'] for d in data)
    total_debt = sum(d['total_debt'] for d in data)

    # Store breakdown
    from core.store_utils import get_managed_store_ids
    from system_management.models import Store
    managed_ids = get_managed_store_ids(request.user)
    managed_stores = Store.objects.filter(id__in=managed_ids).select_related('brand')
    has_multiple = managed_stores.count() > 1
    stores_list = [{'id': s.id, 'name': s.name, 'brand': s.brand.name if s.brand else ''} for s in managed_stores]

    store_breakdown = []
    if has_multiple and not store_id:
        for st in managed_stores:
            st_customers = [d for d in data if d['store_id'] == st.id]
            st_count = len(st_customers)
            st_revenue = sum(d['total_purchased'] for d in st_customers)
            st_debt = sum(d['total_debt'] for d in st_customers)
            store_breakdown.append({
                'store_id': st.id,
                'store_name': st.name,
                'brand_name': st.brand.name if st.brand else '',
                'customer_count': st_count,
                'revenue': st_revenue,
                'debt': st_debt,
            })
        # Khách chưa gán CH
        no_store = [d for d in data if not d['store_id']]
        if no_store:
            store_breakdown.append({
                'store_id': None,
                'store_name': 'Chưa gán cửa hàng',
                'brand_name': '',
                'customer_count': len(no_store),
                'revenue': sum(d['total_purchased'] for d in no_store),
                'debt': sum(d['total_debt'] for d in no_store),
            })

    return JsonResponse({
        'status': 'ok', 'data': data,
        'has_multiple_stores': has_multiple,
        'stores': stores_list,
        'store_breakdown': store_breakdown,
        'summary': {'total_customers': len(data), 'total_revenue': total_revenue, 'total_debt': total_debt}
    })


@login_required(login_url="/login/")
@brand_owner_required
@report_permission_required
def report_staff_sales(request):
    """Báo cáo doanh thu nhân viên bán hàng"""
    context = {'active_tab': 'report_staff_sales'}
    return render(request, "reports/report_staff_sales.html", context)


@login_required(login_url="/login/")
@report_permission_required
def api_report_staff_sales(request):
    """API báo cáo doanh thu theo nhân viên bán hàng — phục vụ tính KPI & lương"""
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    store_id = request.GET.get('store_id')
    salesperson_filter = request.GET.get('salesperson', '')

    today = datetime.now().date()
    if not from_date:
        from_date = today.replace(day=1).strftime('%Y-%m-%d')
    if not to_date:
        to_date = today.strftime('%Y-%m-%d')

    # Base queryset: đơn hàng không bị hủy
    orders = Order.objects.filter(
        order_date__gte=from_date, order_date__lte=to_date
    ).exclude(status=6)
    orders = filter_by_store(orders, request)
    if store_id:
        orders = orders.filter(store_id=store_id)

    # Lấy danh sách unique salesperson
    salesperson_names = list(
        orders.exclude(salesperson__isnull=True).exclude(salesperson='')
        .values_list('salesperson', flat=True).distinct()
    )
    # Thêm nhóm "Chưa gán NV"
    has_no_salesperson = orders.filter(
        Q(salesperson__isnull=True) | Q(salesperson='')
    ).exists()

    # Tổng doanh thu toàn bộ (dùng để tính tỷ lệ đóng góp)
    grand_total_revenue = float(orders.aggregate(s=Sum('final_amount'))['s'] or 0)

    staff_data = []

    def calc_staff(name, staff_orders):
        order_count = staff_orders.count()
        if order_count == 0:
            return None

        revenue = float(staff_orders.aggregate(s=Sum('final_amount'))['s'] or 0)
        paid = float(staff_orders.aggregate(s=Sum('paid_amount'))['s'] or 0)
        bonus = float(staff_orders.aggregate(s=Sum('bonus_amount'))['s'] or 0)
        discount = float(staff_orders.aggregate(s=Sum('discount_amount'))['s'] or 0)

        # Giá vốn
        cost_data = OrderItem.objects.filter(order__in=staff_orders).aggregate(
            total_cost=Sum(F('cost_price') * F('quantity'))
        )
        cost = float(cost_data['total_cost'] or 0)
        profit = revenue - cost

        # Trả hàng liên quan (theo customer từ order)
        staff_order_ids = list(staff_orders.values_list('id', flat=True))
        returns_data = OrderReturn.objects.filter(
            order_id__in=staff_order_ids,
            return_date__gte=from_date, return_date__lte=to_date
        ).exclude(status=3).aggregate(
            total_refund=Sum('total_refund'),
            count=Count('id')
        )
        returns_amount = float(returns_data['total_refund'] or 0)
        returns_count = returns_data['count'] or 0

        net_revenue = revenue - returns_amount
        debt = revenue - paid
        contribution = (revenue / grand_total_revenue * 100) if grand_total_revenue > 0 else 0
        avg_per_order = revenue / order_count if order_count > 0 else 0

        # Top 3 sản phẩm bán chạy của NV này
        top_products = OrderItem.objects.filter(
            order__in=staff_orders
        ).values('product__name').annotate(
            total_qty=Sum('quantity'),
            total_amount=Sum('total_price')
        ).order_by('-total_qty')[:3]

        # Đơn hàng chi tiết (cho phần mở rộng)
        order_details = [{
            'code': o.code,
            'date': o.order_date.strftime('%d/%m/%Y') if o.order_date else '',
            'customer': o.customer.name if o.customer else 'N/A',
            'final_amount': float(o.final_amount),
            'paid_amount': float(o.paid_amount),
            'bonus_amount': float(o.bonus_amount),
            'status': o.status,
            'status_display': o.get_status_display(),
        } for o in staff_orders.select_related('customer').order_by('-order_date')[:50]]

        return {
            'salesperson': name,
            'order_count': order_count,
            'revenue': revenue,
            'cost': cost,
            'profit': profit,
            'discount': discount,
            'returns_amount': returns_amount,
            'returns_count': returns_count,
            'net_revenue': net_revenue,
            'bonus': bonus,
            'debt': debt,
            'paid': paid,
            'contribution': round(contribution, 1),
            'avg_per_order': round(avg_per_order),
            'top_products': [
                {'name': p['product__name'], 'qty': float(p['total_qty'] or 0), 'amount': float(p['total_amount'] or 0)}
                for p in top_products
            ],
            'orders': order_details,
        }

    # Tính cho từng NV
    for sp_name in sorted(salesperson_names):
        if salesperson_filter and salesperson_filter != sp_name:
            continue
        sp_orders = orders.filter(salesperson=sp_name)
        result = calc_staff(sp_name, sp_orders)
        if result:
            staff_data.append(result)

    # Nhóm "Chưa gán NV"
    if has_no_salesperson and not salesperson_filter:
        no_sp_orders = orders.filter(Q(salesperson__isnull=True) | Q(salesperson=''))
        result = calc_staff('(Chưa gán NV)', no_sp_orders)
        if result:
            staff_data.append(result)

    # Sắp xếp theo doanh thu giảm dần
    staff_data.sort(key=lambda x: -x['revenue'])

    # Gán rank
    for i, d in enumerate(staff_data):
        d['rank'] = i + 1

    # Tổng cộng
    summary = {
        'total_staff': len([d for d in staff_data if d['salesperson'] != '(Chưa gán NV)']),
        'grand_revenue': grand_total_revenue,
        'grand_cost': sum(d['cost'] for d in staff_data),
        'grand_profit': sum(d['profit'] for d in staff_data),
        'grand_orders': sum(d['order_count'] for d in staff_data),
        'grand_returns': sum(d['returns_amount'] for d in staff_data),
        'grand_bonus': sum(d['bonus'] for d in staff_data),
        'grand_debt': sum(d['debt'] for d in staff_data),
        'grand_paid': sum(d['paid'] for d in staff_data),
    }

    # Danh sách NV cho dropdown filter lấy từ user/store, không phụ thuộc kỳ báo cáo.
    all_salespersons = _get_salesperson_filter_options(request, store_id)

    # Store list
    from core.store_utils import get_managed_store_ids
    from system_management.models import Store
    managed_ids = get_managed_store_ids(request.user)
    managed_stores = Store.objects.filter(id__in=managed_ids).select_related('brand')
    has_multiple = managed_stores.count() > 1
    stores_list = [{'id': s.id, 'name': s.name, 'brand': s.brand.name if s.brand else ''} for s in managed_stores]

    return JsonResponse({
        'status': 'ok',
        'has_multiple_stores': has_multiple,
        'stores': stores_list,
        'salespersons': all_salespersons,
        'staff_data': staff_data,
        'summary': summary,
    })


@login_required(login_url="/login/")
@report_permission_required
def export_staff_sales_excel(request):
    """Xuất báo cáo doanh thu nhân viên ra Excel"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse

    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    store_id = request.GET.get('store_id')

    today = datetime.now().date()
    if not from_date:
        from_date = today.replace(day=1).strftime('%Y-%m-%d')
    if not to_date:
        to_date = today.strftime('%Y-%m-%d')

    # Lấy dữ liệu (tái sử dụng logic)
    orders = Order.objects.filter(
        order_date__gte=from_date, order_date__lte=to_date
    ).exclude(status=6)
    orders = filter_by_store(orders, request)
    if store_id:
        orders = orders.filter(store_id=store_id)

    salesperson_names = list(
        orders.exclude(salesperson__isnull=True).exclude(salesperson='')
        .values_list('salesperson', flat=True).distinct()
    )
    grand_total_revenue = float(orders.aggregate(s=Sum('final_amount'))['s'] or 0)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'BC Doanh thu NV'

    # Styles
    header_font = Font(bold=True, size=14, color='FFFFFF')
    header_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
    sub_header_font = Font(bold=True, size=10, color='FFFFFF')
    sub_header_fill = PatternFill(start_color='2E75B6', end_color='2E75B6', fill_type='solid')
    money_format = '#,##0'
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    total_fill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
    total_font = Font(bold=True, size=10)

    # Title
    ws.merge_cells('A1:L1')
    ws['A1'] = 'BÁO CÁO DOANH THU NHÂN VIÊN BÁN HÀNG'
    ws['A1'].font = header_font
    ws['A1'].fill = header_fill
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:L2')
    ws['A2'] = f'Từ ngày {from_date} đến ngày {to_date}'
    ws['A2'].font = Font(italic=True, size=10)
    ws['A2'].alignment = Alignment(horizontal='center')

    # Column headers
    headers = ['STT', 'Nhân viên', 'Số đơn', 'Doanh thu', 'Giá vốn', 'Lợi nhuận',
               'Trả hàng', 'DT ròng', 'Bonus', 'Công nợ', 'Đã thu', 'Tỷ lệ (%)']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.font = sub_header_font
        cell.fill = sub_header_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border

    # Data rows
    row = 5
    sorted_names = sorted(salesperson_names)
    # Include "Chưa gán NV"
    has_no_sp = orders.filter(Q(salesperson__isnull=True) | Q(salesperson='')).exists()
    if has_no_sp:
        sorted_names.append('(Chưa gán NV)')

    grand = {'orders': 0, 'revenue': 0, 'cost': 0, 'profit': 0,
             'returns': 0, 'net': 0, 'bonus': 0, 'debt': 0, 'paid': 0}

    for idx, sp_name in enumerate(sorted_names, 1):
        if sp_name == '(Chưa gán NV)':
            sp_orders = orders.filter(Q(salesperson__isnull=True) | Q(salesperson=''))
        else:
            sp_orders = orders.filter(salesperson=sp_name)

        count = sp_orders.count()
        if count == 0:
            continue
        revenue = float(sp_orders.aggregate(s=Sum('final_amount'))['s'] or 0)
        paid = float(sp_orders.aggregate(s=Sum('paid_amount'))['s'] or 0)
        bonus = float(sp_orders.aggregate(s=Sum('bonus_amount'))['s'] or 0)
        cost_data = OrderItem.objects.filter(order__in=sp_orders).aggregate(
            c=Sum(F('cost_price') * F('quantity'))
        )
        cost = float(cost_data['c'] or 0)
        profit = revenue - cost

        sp_ids = list(sp_orders.values_list('id', flat=True))
        ret = OrderReturn.objects.filter(
            order_id__in=sp_ids, return_date__gte=from_date, return_date__lte=to_date
        ).exclude(status=3).aggregate(s=Sum('total_refund'))
        returns_amt = float(ret['s'] or 0)

        net_revenue = revenue - returns_amt
        debt = revenue - paid
        contribution = (revenue / grand_total_revenue * 100) if grand_total_revenue > 0 else 0

        data_row = [idx, sp_name, count, revenue, cost, profit,
                    returns_amt, net_revenue, bonus, debt, paid, round(contribution, 1)]
        for col, val in enumerate(data_row, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = thin_border
            if col >= 4 and col <= 11:
                cell.number_format = money_format
            if col == 12:
                cell.number_format = '0.0'
            if col in (1, 3):
                cell.alignment = Alignment(horizontal='center')

        grand['orders'] += count
        grand['revenue'] += revenue
        grand['cost'] += cost
        grand['profit'] += profit
        grand['returns'] += returns_amt
        grand['net'] += net_revenue
        grand['bonus'] += bonus
        grand['debt'] += debt
        grand['paid'] += paid
        row += 1

    # Total row
    total_row = [
        '', 'TỔNG CỘNG', grand['orders'], grand['revenue'], grand['cost'],
        grand['profit'], grand['returns'], grand['net'], grand['bonus'],
        grand['debt'], grand['paid'], 100
    ]
    for col, val in enumerate(total_row, 1):
        cell = ws.cell(row=row, column=col, value=val)
        cell.font = total_font
        cell.fill = total_fill
        cell.border = thin_border
        if col >= 4 and col <= 11:
            cell.number_format = money_format
        if col == 12:
            cell.number_format = '0.0'

    # Column widths
    col_widths = [6, 25, 10, 18, 18, 18, 15, 18, 15, 15, 15, 12]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f'BC_Doanh_thu_NV_{from_date}_{to_date}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required(login_url="/login/")
@report_permission_required
@sales_report_privileged_required
def export_sales_excel(request):
    """Xuất báo cáo bán hàng ra Excel theo đúng bộ lọc hiện tại."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse

    filters = _get_sales_report_filters(request)
    payload = _build_sales_report_payload(request, include_filter_options=False)
    summary = payload.get('summary', {})
    daily = payload.get('daily', [])
    daily_finance = payload.get('daily_finance') or daily
    product_breakdown = payload.get('product_breakdown', [])
    sku_details = payload.get('sku_details', [])
    category_breakdown = payload.get('category_breakdown', [])
    customer_kind_breakdown = payload.get('customer_kind_breakdown', [])
    group_breakdown = payload.get('group_breakdown', [])
    order_details = payload.get('order_details', [])
    time_group_label = payload.get('time_group_label', 'Ngày')

    # Styles
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Doanh thu theo {time_group_label.lower()}"[:31]
    header_font = Font(bold=True, size=14, color='FFFFFF')
    header_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
    sub_font = Font(bold=True, size=10, color='FFFFFF')
    sub_fill = PatternFill(start_color='2E75B6', end_color='2E75B6', fill_type='solid')
    thin = Border(left=Side(style='thin'), right=Side(style='thin'),
                  top=Side(style='thin'), bottom=Side(style='thin'))
    total_fill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
    loss_fill = PatternFill(start_color='FCE4EC', end_color='FCE4EC', fill_type='solid')
    money_fmt = '#,##0'

    ws.merge_cells('A1:G1')
    ws['A1'] = 'BÁO CÁO BÁN HÀNG'
    ws['A1'].font = header_font
    ws['A1'].fill = header_fill
    ws['A1'].alignment = Alignment(horizontal='center')
    ws.merge_cells('A2:G2')
    ws['A2'] = f"Từ {filters['from_date']} đến {filters['to_date']}"
    ws['A2'].font = Font(italic=True, size=10)
    ws['A2'].alignment = Alignment(horizontal='center')

    filter_labels = _get_sales_report_filter_labels(filters)
    if filter_labels:
        ws.merge_cells('A3:G3')
        ws['A3'] = 'Bộ lọc: ' + ' | '.join(filter_labels)
        ws['A3'].font = Font(italic=True, size=9)
        ws['A3'].alignment = Alignment(horizontal='center')

    headers = ['STT', time_group_label, 'Số ĐH', 'Doanh thu', 'Giá vốn thuần', 'Lợi nhuận', 'Trả hàng']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.font = sub_font
        cell.fill = sub_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin

    row = 5
    for idx, d in enumerate(daily, 1):
        vals = [idx, d['date'], d['count'], d['revenue'], d['cost'], d['profit'], d['returns']]
        for col, val in enumerate(vals, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = thin
            if col >= 4:
                cell.number_format = money_fmt
            # Highlight negative profit
            if col == 6 and val < 0:
                cell.font = Font(bold=True, color='FF0000')
        row += 1

    # Total row
    totals = [
        '', 'TỔNG', summary.get('total_orders', 0), summary.get('total_revenue', 0),
        summary.get('total_cost', 0), summary.get('total_profit', 0), summary.get('total_returns', 0)
    ]
    for col, val in enumerate(totals, 1):
        cell = ws.cell(row=row, column=col, value=val)
        cell.font = Font(bold=True)
        cell.fill = total_fill
        cell.border = thin
        if col >= 4:
            cell.number_format = money_fmt

    for i, w in enumerate([6, 20, 12, 18, 18, 18, 15], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # ===== Sheet 2: Tổng hợp ngày =====
    ws_daily = wb.create_sheet('Tổng hợp ngày')
    daily_headers = [
        'Ngày', 'Tiền hàng', 'Doanh thu', 'Doanh thu thuần', 'Giá vốn thuần',
        'Lợi nhuận gộp', 'Tỷ suất lợi nhuận gộp', 'Lợi nhuận ròng',
    ]
    for col, h in enumerate(daily_headers, 1):
        cell = ws_daily.cell(row=1, column=col, value=h)
        cell.font = sub_font
        cell.fill = sub_fill
        cell.border = thin

    daily_totals = {
        'goods_amount': 0,
        'revenue': 0,
        'net_revenue': 0,
        'cost': 0,
        'gross_profit': 0,
        'net_profit': 0,
    }
    for idx, row in enumerate(daily_finance, 2):
        goods_amount = float(row.get('goods_amount') or 0)
        revenue = float(row.get('revenue') or 0)
        net_revenue = float(row.get('net_revenue') or 0)
        cost = float(row.get('cost') or 0)
        gross_profit = float(row.get('gross_profit') or 0)
        gross_margin = float(row.get('gross_margin') or 0)
        net_profit = float(row.get('net_profit') or 0)
        values = [
            row.get('date') or '',
            goods_amount,
            revenue,
            net_revenue,
            cost,
            gross_profit,
            gross_margin / 100,
            net_profit,
        ]
        for col, val in enumerate(values, 1):
            cell = ws_daily.cell(row=idx, column=col, value=val)
            cell.border = thin
            if col in (2, 3, 4, 5, 6, 8):
                cell.number_format = money_fmt
            if col == 7:
                cell.number_format = '0.0%'
            if col in (6, 8) and float(val or 0) < 0:
                cell.font = Font(bold=True, color='FF0000')
        daily_totals['goods_amount'] += goods_amount
        daily_totals['revenue'] += revenue
        daily_totals['net_revenue'] += net_revenue
        daily_totals['cost'] += cost
        daily_totals['gross_profit'] += gross_profit
        daily_totals['net_profit'] += net_profit

    total_margin = (
        daily_totals['gross_profit'] / daily_totals['net_revenue']
        if daily_totals['net_revenue'] > 0 else 0
    )
    daily_total_row = len(daily_finance) + 2
    for col, val in enumerate([
        'TỔNG',
        daily_totals['goods_amount'],
        daily_totals['revenue'],
        daily_totals['net_revenue'],
        daily_totals['cost'],
        daily_totals['gross_profit'],
        total_margin,
        daily_totals['net_profit'],
    ], 1):
        cell = ws_daily.cell(row=daily_total_row, column=col, value=val)
        cell.font = Font(bold=True)
        cell.fill = total_fill
        cell.border = thin
        if col in (2, 3, 4, 5, 6, 8):
            cell.number_format = money_fmt
        if col == 7:
            cell.number_format = '0.0%'

    for i, w in enumerate([16, 18, 18, 18, 18, 18, 20, 18], 1):
        ws_daily.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # ===== Sheet 3: Mặt hàng =====
    ws2 = wb.create_sheet('Mặt hàng')
    sp_headers = ['STT', 'Sản phẩm', 'Nhóm mặt hàng', 'Loại SP', 'SL bán', 'Doanh thu', 'Giá vốn', 'LN dòng', 'Biên LN']
    for col, h in enumerate(sp_headers, 1):
        cell = ws2.cell(row=1, column=col, value=h)
        cell.font = sub_font
        cell.fill = sub_fill
        cell.border = thin

    for idx, p in enumerate(product_breakdown, 1):
        amt = float(p.get('amount') or 0)
        cst = float(p.get('cost') or 0)
        profit = float(p.get('profit') or 0)
        margin = round((profit / amt) * 100, 1) if amt > 0 else 0
        ws2.cell(row=idx + 1, column=1, value=idx).border = thin
        ws2.cell(row=idx + 1, column=2, value=p.get('name') or '').border = thin
        ws2.cell(row=idx + 1, column=3, value=p.get('category') or '').border = thin
        ws2.cell(row=idx + 1, column=4, value=p.get('product_type') or '').border = thin
        ws2.cell(row=idx + 1, column=5, value=float(p.get('qty') or 0)).border = thin
        c = ws2.cell(row=idx + 1, column=6, value=amt)
        c.number_format = money_fmt
        c.border = thin
        c = ws2.cell(row=idx + 1, column=7, value=cst)
        c.number_format = money_fmt
        c.border = thin
        c = ws2.cell(row=idx + 1, column=8, value=profit)
        c.number_format = money_fmt
        c.border = thin
        ws2.cell(row=idx + 1, column=9, value=margin / 100).number_format = '0.0%'
        ws2.cell(row=idx + 1, column=9).border = thin
        if profit < 0:
            c.font = Font(bold=True, color='FF0000')

    for i, w in enumerate([6, 35, 20, 18, 12, 18, 18, 18, 12], 1):
        ws2.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # ===== Sheet 4: Chi tiết SKU =====
    ws_sku = wb.create_sheet('Chi tiết SKU')
    sku_headers = [
        'Ngày', 'Tên khách hàng', 'Tên sản phẩm', 'Mã SKU', 'Mã đơn hàng',
        'Tên nhân viên', 'Doanh thu thuần', 'Tiền vốn', 'Lợi nhuận gộp',
    ]
    for col, h in enumerate(sku_headers, 1):
        cell = ws_sku.cell(row=1, column=col, value=h)
        cell.font = sub_font
        cell.fill = sub_fill
        cell.border = thin

    sku_totals = {'revenue': 0, 'cost': 0, 'profit': 0}
    for idx, row in enumerate(sku_details, 2):
        revenue = float(row.get('revenue') or 0)
        cost = float(row.get('cost') or 0)
        profit = float(row.get('profit') or 0)
        values = [
            row.get('date') or '',
            row.get('customer') or '',
            row.get('product_name') or '',
            row.get('sku') or '',
            row.get('order_code') or '',
            row.get('salesperson') or '',
            revenue,
            cost,
            profit,
        ]
        for col, val in enumerate(values, 1):
            cell = ws_sku.cell(row=idx, column=col, value=val)
            cell.border = thin
            if col in (7, 8, 9):
                cell.number_format = money_fmt
            if profit < 0:
                cell.fill = loss_fill
            if col == 9 and profit < 0:
                cell.font = Font(bold=True, color='FF0000')
        sku_totals['revenue'] += revenue
        sku_totals['cost'] += cost
        sku_totals['profit'] += profit

    sku_total_row = len(sku_details) + 2
    for col, val in enumerate([
        '', '', '', '', '', 'TỔNG',
        sku_totals['revenue'], sku_totals['cost'], sku_totals['profit'],
    ], 1):
        cell = ws_sku.cell(row=sku_total_row, column=col, value=val)
        cell.font = Font(bold=True)
        cell.fill = total_fill
        cell.border = thin
        if col in (7, 8, 9):
            cell.number_format = money_fmt

    for i, w in enumerate([14, 28, 36, 18, 16, 22, 18, 18, 18], 1):
        ws_sku.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # ===== Sheet 5: Nhóm mặt hàng =====
    ws3 = wb.create_sheet('Nhóm mặt hàng')
    cat_headers = ['STT', 'Nhóm mặt hàng', 'SL bán', 'Doanh thu', 'Giá vốn', 'Lợi nhuận', 'Biên LN']
    for col, h in enumerate(cat_headers, 1):
        cell = ws3.cell(row=1, column=col, value=h)
        cell.font = sub_font
        cell.fill = sub_fill
        cell.border = thin

    for idx, row in enumerate(category_breakdown, 1):
        revenue = float(row.get('revenue') or 0)
        cost = float(row.get('cost') or 0)
        profit = float(row.get('profit') or 0)
        margin = round((profit / revenue) * 100, 1) if revenue > 0 else 0
        values = [idx, row.get('name') or '', float(row.get('qty') or 0), revenue, cost, profit, margin / 100]
        for col, val in enumerate(values, 1):
            cell = ws3.cell(row=idx + 1, column=col, value=val)
            cell.border = thin
            if col in (4, 5, 6):
                cell.number_format = money_fmt
            if col == 7:
                cell.number_format = '0.0%'
            if col == 6 and profit < 0:
                cell.font = Font(bold=True, color='FF0000')

    for i, w in enumerate([6, 28, 12, 18, 18, 18, 12], 1):
        ws3.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # ===== Sheet 6: Khách buôn/lẻ =====
    ws_kind = wb.create_sheet('Khách buôn lẻ')
    kind_headers = ['STT', 'Kiểu khách', 'Số ĐH', 'Doanh thu', 'Giá vốn', 'Lợi nhuận', 'Đã thu', 'Công nợ', 'Tỷ trọng']
    for col, h in enumerate(kind_headers, 1):
        cell = ws_kind.cell(row=1, column=col, value=h)
        cell.font = sub_font
        cell.fill = sub_fill
        cell.border = thin

    for idx, row in enumerate(customer_kind_breakdown, 1):
        values = [
            idx,
            row.get('name') or '',
            int(row.get('orders') or 0),
            float(row.get('amount') or 0),
            float(row.get('cost') or 0),
            float(row.get('profit') or 0),
            float(row.get('paid') or 0),
            float(row.get('debt') or 0),
            (float(row.get('contribution') or 0) / 100),
        ]
        for col, val in enumerate(values, 1):
            cell = ws_kind.cell(row=idx + 1, column=col, value=val)
            cell.border = thin
            if col in (4, 5, 6, 7, 8):
                cell.number_format = money_fmt
            if col == 9:
                cell.number_format = '0.0%'
            if col == 6 and float(row.get('profit') or 0) < 0:
                cell.font = Font(bold=True, color='FF0000')

    for i, w in enumerate([6, 22, 12, 18, 18, 18, 18, 18, 12], 1):
        ws_kind.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # ===== Sheet 7: Nhóm khách hàng =====
    ws4 = wb.create_sheet('Nhóm khách hàng')
    grp_headers = ['STT', 'Nhóm KH', 'Số ĐH', 'Doanh thu', 'Giá vốn', 'Lợi nhuận', 'Đã thu', 'Công nợ', 'Tỷ trọng']
    for col, h in enumerate(grp_headers, 1):
        cell = ws4.cell(row=1, column=col, value=h)
        cell.font = sub_font
        cell.fill = sub_fill
        cell.border = thin

    for idx, row in enumerate(group_breakdown, 1):
        values = [
            idx,
            row.get('name') or '',
            int(row.get('orders') or 0),
            float(row.get('amount') or 0),
            float(row.get('cost') or 0),
            float(row.get('profit') or 0),
            float(row.get('paid') or 0),
            float(row.get('debt') or 0),
            (float(row.get('contribution') or 0) / 100),
        ]
        for col, val in enumerate(values, 1):
            cell = ws4.cell(row=idx + 1, column=col, value=val)
            cell.border = thin
            if col in (4, 5, 6, 7, 8):
                cell.number_format = money_fmt
            if col == 9:
                cell.number_format = '0.0%'
            if col == 6 and float(row.get('profit') or 0) < 0:
                cell.font = Font(bold=True, color='FF0000')

    for i, w in enumerate([6, 24, 12, 18, 18, 18, 18, 18, 12], 1):
        ws4.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # ===== Sheet 8: Chi tiết đơn hàng =====
    ws5 = wb.create_sheet('Chi tiết đơn hàng')
    od_headers = [
        'STT', 'Mã ĐH', 'Ngày', 'Khách hàng', 'Kiểu khách', 'Nhóm KH',
        'Sản phẩm lỗ', 'Doanh thu', 'Đã thu', 'Công nợ', 'Giá vốn', 'Lợi nhuận', 'Báo lỗ',
        'TT đơn', 'TT thanh toán',
    ]
    for col, h in enumerate(od_headers, 1):
        cell = ws5.cell(row=1, column=col, value=h)
        cell.font = sub_font
        cell.fill = sub_fill
        cell.border = thin

    od_row = 2
    od_grand = {'revenue': 0, 'paid': 0, 'debt': 0, 'cost': 0, 'profit': 0}
    for idx, o in enumerate(order_details, 1):
        is_loss = bool(o.get('is_loss'))
        vals = [
            idx,
            o.get('code') or '',
            o.get('date') or '',
            o.get('customer') or '',
            o.get('customer_kind_label') or '',
            o.get('customer_group') or '',
            o.get('loss_product_names') or '',
            float(o.get('revenue') or 0),
            float(o.get('paid') or 0),
            float(o.get('debt') or 0),
            float(o.get('cost') or 0),
            float(o.get('profit') or 0),
            'Lỗ' if is_loss else '',
            o.get('status_display') or '',
            o.get('payment_status_display') or '',
        ]
        for col, val in enumerate(vals, 1):
            cell = ws5.cell(row=od_row, column=col, value=val)
            cell.border = thin
            if col in (8, 9, 10, 11, 12):
                cell.number_format = money_fmt
            if is_loss:
                cell.fill = loss_fill
            if col == 12 and is_loss:
                cell.font = Font(bold=True, color='FF0000')

        od_grand['revenue'] += float(o.get('revenue') or 0)
        od_grand['paid'] += float(o.get('paid') or 0)
        od_grand['debt'] += float(o.get('debt') or 0)
        od_grand['cost'] += float(o.get('cost') or 0)
        od_grand['profit'] += float(o.get('profit') or 0)
        od_row += 1

    # Total row for order detail
    for col, val in enumerate([
        '', 'TỔNG', '', '', '', '', '',
        od_grand['revenue'], od_grand['paid'], od_grand['debt'],
        od_grand['cost'], od_grand['profit'], '', '', '',
    ], 1):
        cell = ws5.cell(row=od_row, column=col, value=val)
        cell.font = Font(bold=True)
        cell.fill = total_fill
        cell.border = thin
        if col in (8, 9, 10, 11, 12):
            cell.number_format = money_fmt

    for i, w in enumerate([6, 12, 12, 25, 18, 15, 36, 18, 18, 18, 18, 18, 10, 15, 18], 1):
        ws5.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"BC_Ban_hang_{filters['from_date']}_{filters['to_date']}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required(login_url="/login/")
@report_permission_required
def export_inventory_excel(request):
    """Xuất báo cáo tồn kho ra Excel"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse
    from products.models import ProductStock

    warehouse_id = request.GET.get('warehouse_id')
    search = request.GET.get('search', '').strip()
    category_id = request.GET.get('category_id')
    product_type_id = request.GET.get('product_type_id')

    stocks = ProductStock.objects.select_related('product', 'product__category', 'warehouse').filter(
        product__is_deleted=False,
    )
    stocks = filter_by_store(stocks, request, field_name='warehouse__store')
    if warehouse_id:
        stocks = stocks.filter(warehouse_id=warehouse_id)
    if search:
        stocks = stocks.filter(
            Q(product__name__icontains=search) |
            Q(product__code__icontains=search) |
            Q(product__barcode__icontains=search)
        )
    if category_id:
        stocks = stocks.filter(
            Q(product__category_id=category_id) |
            Q(product__category__parent_id=category_id)
        )
    if product_type_id:
        stocks = stocks.filter(product__category_id=product_type_id)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Tồn kho'
    header_font = Font(bold=True, size=14, color='FFFFFF')
    header_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
    sub_font = Font(bold=True, size=10, color='FFFFFF')
    sub_fill = PatternFill(start_color='2E75B6', end_color='2E75B6', fill_type='solid')
    thin = Border(left=Side(style='thin'), right=Side(style='thin'),
                  top=Side(style='thin'), bottom=Side(style='thin'))
    danger_fill = PatternFill(start_color='FCE4EC', end_color='FCE4EC', fill_type='solid')
    warning_fill = PatternFill(start_color='FFF3E0', end_color='FFF3E0', fill_type='solid')
    money_fmt = '#,##0'

    ws.merge_cells('A1:L1')
    ws['A1'] = 'BÁO CÁO TỒN KHO'
    ws['A1'].font = header_font
    ws['A1'].fill = header_fill
    ws['A1'].alignment = Alignment(horizontal='center')
    ws.merge_cells('A2:L2')
    ws['A2'] = f'Ngày xuất: {datetime.now().strftime("%d/%m/%Y %H:%M")}'
    ws['A2'].font = Font(italic=True, size=10)
    ws['A2'].alignment = Alignment(horizontal='center')

    headers = ['STT', 'Mã SP', 'Tên sản phẩm', 'Danh mục', 'ĐVT', 'Kho', 'Tồn kho',
               'Tối thiểu', 'Tối đa', 'Giá tính tồn', 'Giá trị tồn', 'Cảnh báo']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.font = sub_font
        cell.fill = sub_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin

    row = 5
    total_value = 0
    total_qty = 0
    for idx, s in enumerate(stocks, 1):
        qty = float(s.quantity)
        valuation_price, _ = _inventory_valuation_unit_cost(s.product)
        valuation_price = float(valuation_price)
        value = valuation_price * max(qty, 0)
        total_value += value
        total_qty += qty

        alert = ''
        fill = None
        if s.product.min_stock and qty < s.product.min_stock:
            alert = 'Dưới tối thiểu'
            fill = danger_fill
        elif s.product.max_stock and qty > s.product.max_stock:
            alert = 'Trên tối đa'
            fill = warning_fill

        cat_name = s.product.category.name if s.product.category else ''
        vals = [idx, s.product.code, s.product.name, cat_name, s.product.unit or '',
                s.warehouse.name, qty, s.product.min_stock or 0,
                s.product.max_stock or 0, valuation_price, value, alert]
        for col, val in enumerate(vals, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = thin
            if col in (10, 11):
                cell.number_format = money_fmt
            if fill:
                cell.fill = fill
        row += 1

    # Total
    ws.cell(row=row, column=1, value='').border = thin
    c = ws.cell(row=row, column=2, value='TỔNG CỘNG')
    c.font = Font(bold=True)
    c.border = thin
    for col in range(3, 7):
        ws.cell(row=row, column=col, value='').border = thin
    c = ws.cell(row=row, column=7, value=total_qty)
    c.font = Font(bold=True)
    c.border = thin
    for col in range(8, 11):
        ws.cell(row=row, column=col, value='').border = thin
    c = ws.cell(row=row, column=11, value=total_value)
    c.font = Font(bold=True)
    c.number_format = money_fmt
    c.border = thin
    ws.cell(row=row, column=12, value='').border = thin

    col_widths = [6, 12, 30, 18, 8, 15, 12, 12, 12, 15, 18, 15]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f'BC_Ton_kho_{datetime.now().strftime("%Y%m%d")}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required(login_url="/login/")
@report_permission_required
def export_orders_excel(request):
    """Xuất danh sách đơn hàng ra Excel"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse

    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    status = request.GET.get('status')
    payment_status = request.GET.get('payment_status')

    orders = Order.objects.select_related('customer', 'warehouse').all()
    orders = filter_by_store(orders, request)
    if from_date:
        orders = orders.filter(order_date__gte=from_date)
    if to_date:
        orders = orders.filter(order_date__lte=to_date)
    if status:
        orders = orders.filter(status=int(status))
    if payment_status:
        orders = orders.filter(payment_status=int(payment_status))
    orders = orders.order_by('-order_date')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Danh sách đơn hàng'
    header_font = Font(bold=True, size=14, color='FFFFFF')
    header_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
    sub_font = Font(bold=True, size=10, color='FFFFFF')
    sub_fill = PatternFill(start_color='2E75B6', end_color='2E75B6', fill_type='solid')
    thin = Border(left=Side(style='thin'), right=Side(style='thin'),
                  top=Side(style='thin'), bottom=Side(style='thin'))
    total_fill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
    money_fmt = '#,##0'

    ws.merge_cells('A1:J1')
    ws['A1'] = 'DANH SÁCH ĐƠN HÀNG'
    ws['A1'].font = header_font
    ws['A1'].fill = header_fill
    ws['A1'].alignment = Alignment(horizontal='center')
    date_range = ''
    if from_date and to_date:
        date_range = f'Từ {from_date} đến {to_date}'
    elif from_date:
        date_range = f'Từ {from_date}'
    elif to_date:
        date_range = f'Đến {to_date}'
    else:
        date_range = 'Tất cả'
    ws.merge_cells('A2:J2')
    ws['A2'] = date_range
    ws['A2'].font = Font(italic=True, size=10)
    ws['A2'].alignment = Alignment(horizontal='center')

    headers = ['STT', 'Mã ĐH', 'Khách hàng', 'Kho', 'Ngày đặt',
               'Tổng tiền', 'Đã thanh toán', 'Còn nợ', 'Trạng thái', 'TT thanh toán']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.font = sub_font
        cell.fill = sub_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin

    row = 5
    grand = {'total': 0, 'paid': 0, 'debt': 0}
    for idx, o in enumerate(orders, 1):
        total = float(o.final_amount)
        paid = float(o.paid_amount)
        debt = total - paid
        grand['total'] += total
        grand['paid'] += paid
        grand['debt'] += debt

        vals = [
            idx, o.code,
            o.customer.name if o.customer else '',
            o.warehouse.name if o.warehouse else '',
            o.order_date.strftime('%d/%m/%Y') if o.order_date else '',
            total, paid, debt,
            o.get_status_display(),
            o.get_payment_status_display(),
        ]
        for col, val in enumerate(vals, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = thin
            if col in (6, 7, 8):
                cell.number_format = money_fmt
        row += 1

    # Total row
    totals = ['', 'TỔNG', '', '', '', grand['total'], grand['paid'], grand['debt'], '', '']
    for col, val in enumerate(totals, 1):
        cell = ws.cell(row=row, column=col, value=val)
        cell.font = Font(bold=True)
        cell.fill = total_fill
        cell.border = thin
        if col in (6, 7, 8):
            cell.number_format = money_fmt

    col_widths = [6, 15, 25, 15, 12, 18, 18, 18, 15, 15]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f'DS_Don_hang_{datetime.now().strftime("%Y%m%d")}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required(login_url="/login/")
@report_permission_required
def export_customers_excel(request):
    """Xuất báo cáo khách hàng ra Excel"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse
    from customers.models import Customer

    store_id = request.GET.get('store_id')

    customers = Customer.objects.filter(is_active=True).select_related('group', 'store')
    customers = filter_by_store(customers, request)
    if store_id:
        customers = customers.filter(store_id=store_id)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Khách hàng'
    header_font = Font(bold=True, size=14, color='FFFFFF')
    header_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
    sub_font = Font(bold=True, size=10, color='FFFFFF')
    sub_fill = PatternFill(start_color='2E75B6', end_color='2E75B6', fill_type='solid')
    thin = Border(left=Side(style='thin'), right=Side(style='thin'),
                  top=Side(style='thin'), bottom=Side(style='thin'))
    debt_fill = PatternFill(start_color='FFF3E0', end_color='FFF3E0', fill_type='solid')
    money_fmt = '#,##0'

    ws.merge_cells('A1:I1')
    ws['A1'] = 'BÁO CÁO KHÁCH HÀNG'
    ws['A1'].font = header_font
    ws['A1'].fill = header_fill
    ws['A1'].alignment = Alignment(horizontal='center')
    ws.merge_cells('A2:I2')
    ws['A2'] = f'Ngày xuất: {datetime.now().strftime("%d/%m/%Y %H:%M")}'
    ws['A2'].font = Font(italic=True, size=10)
    ws['A2'].alignment = Alignment(horizontal='center')

    headers = ['STT', 'Mã KH', 'Tên KH', 'SĐT', 'Email', 'Nhóm',
               'Số ĐH', 'Tổng mua', 'Công nợ']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.font = sub_font
        cell.fill = sub_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin

    row = 5
    grand = {'orders': 0, 'revenue': 0, 'debt': 0}
    for idx, c in enumerate(customers, 1):
        orders = Order.objects.filter(customer=c).exclude(status=6)
        order_count = orders.count()
        total = float(orders.aggregate(s=Sum('final_amount'))['s'] or 0)
        paid = float(orders.aggregate(s=Sum('paid_amount'))['s'] or 0)
        debt = total - paid
        grand['orders'] += order_count
        grand['revenue'] += total
        grand['debt'] += debt

        vals = [idx, c.code, c.name, c.phone or '', c.email or '',
                c.group.name if c.group else '', order_count, total, debt]
        for col, val in enumerate(vals, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = thin
            if col in (8, 9):
                cell.number_format = money_fmt
            if debt > 0:
                cell.fill = debt_fill
        row += 1

    # Total
    total_fill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
    totals = ['', 'TỔNG', '', '', '', '', grand['orders'], grand['revenue'], grand['debt']]
    for col, val in enumerate(totals, 1):
        cell = ws.cell(row=row, column=col, value=val)
        cell.font = Font(bold=True)
        cell.fill = total_fill
        cell.border = thin
        if col in (8, 9):
            cell.number_format = money_fmt

    col_widths = [6, 12, 25, 15, 25, 15, 10, 18, 18]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f'BC_Khach_hang_{datetime.now().strftime("%Y%m%d")}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required(login_url="/login/")
@report_permission_required
def export_purchases_excel(request):
    """Xuất báo cáo nhập hàng ra Excel"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    today = datetime.now().date()
    if not from_date:
        from_date = today.replace(day=1).strftime('%Y-%m-%d')
    if not to_date:
        to_date = today.strftime('%Y-%m-%d')

    supplier_id = _parse_filter_int(request.GET.get('supplier_id'))
    receipts = _purchase_report_receipts(
        request,
        from_date,
        to_date,
        supplier_id=supplier_id,
    ).order_by('-receipt_date', '-id')
    supplier_summary = _purchase_supplier_summary(receipts)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Nhập hàng'
    hf = Font(bold=True, size=14, color='FFFFFF')
    hfill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
    sf = Font(bold=True, size=10, color='FFFFFF')
    sfill = PatternFill(start_color='2E75B6', end_color='2E75B6', fill_type='solid')
    thin = Border(left=Side(style='thin'), right=Side(style='thin'),
                  top=Side(style='thin'), bottom=Side(style='thin'))
    cancel_fill = PatternFill(start_color='FCE4EC', end_color='FCE4EC', fill_type='solid')
    tfill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
    mfmt = '#,##0'

    ws.merge_cells('A1:G1')
    ws['A1'] = 'BÁO CÁO NHẬP HÀNG'
    ws['A1'].font = hf
    ws['A1'].fill = hfill
    ws['A1'].alignment = Alignment(horizontal='center')
    ws.merge_cells('A2:G2')
    ws['A2'] = f'Từ {from_date} đến {to_date}'
    ws['A2'].font = Font(italic=True, size=10)
    ws['A2'].alignment = Alignment(horizontal='center')

    headers = ['STT', 'Mã phiếu', 'Ngày', 'Nhà cung cấp', 'Kho', 'Tổng tiền', 'Trạng thái']
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=4, column=col, value=h)
        c.font = sf
        c.fill = sfill
        c.alignment = Alignment(horizontal='center')
        c.border = thin

    row = 5
    total = 0
    for idx, r in enumerate(receipts, 1):
        amt = float(r.total_amount)
        is_cancel = (r.status == 2)
        if r.status == 1:
            total += amt
        vals = [idx, r.code,
                r.receipt_date.strftime('%d/%m/%Y') if r.receipt_date else '',
                r.supplier.name if r.supplier else '',
                r.warehouse.name if r.warehouse else '',
                amt, r.get_status_display()]
        for col, val in enumerate(vals, 1):
            c = ws.cell(row=row, column=col, value=val)
            c.border = thin
            if col == 6:
                c.number_format = mfmt
            if is_cancel:
                c.fill = cancel_fill
        row += 1

    totals = ['', 'TỔNG', '', '', '', total, '']
    for col, val in enumerate(totals, 1):
        c = ws.cell(row=row, column=col, value=val)
        c.font = Font(bold=True)
        c.fill = tfill
        c.border = thin
        if col == 6:
            c.number_format = mfmt

    for i, w in enumerate([6, 15, 12, 25, 15, 18, 12], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    summary_ws = wb.create_sheet('Tổng hợp NCC')
    summary_ws.merge_cells('A1:D1')
    summary_ws['A1'] = 'TỔNG HỢP NHẬP HÀNG THEO NHÀ CUNG CẤP'
    summary_ws['A1'].font = hf
    summary_ws['A1'].fill = hfill
    summary_ws['A1'].alignment = Alignment(horizontal='center')
    summary_ws.merge_cells('A2:D2')
    summary_ws['A2'] = f'Từ {from_date} đến {to_date} · Chỉ tính phiếu hoàn thành'
    summary_ws['A2'].font = Font(italic=True, size=10)
    summary_ws['A2'].alignment = Alignment(horizontal='center')

    summary_headers = ['STT', 'Nhà cung cấp', 'Số phiếu hoàn thành', 'Tổng tiền hàng']
    for col, header in enumerate(summary_headers, 1):
        cell = summary_ws.cell(row=4, column=col, value=header)
        cell.font = sf
        cell.fill = sfill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin

    summary_row = 5
    for index, item in enumerate(supplier_summary, 1):
        values = [index, item['supplier'], item['receipt_count'], item['total_amount']]
        for col, value in enumerate(values, 1):
            cell = summary_ws.cell(row=summary_row, column=col, value=value)
            cell.border = thin
            if col == 4:
                cell.number_format = mfmt
        summary_row += 1

    summary_totals = ['', 'TỔNG', sum(item['receipt_count'] for item in supplier_summary), total]
    for col, value in enumerate(summary_totals, 1):
        cell = summary_ws.cell(row=summary_row, column=col, value=value)
        cell.font = Font(bold=True)
        cell.fill = tfill
        cell.border = thin
        if col == 4:
            cell.number_format = mfmt
    for index, width in enumerate([6, 32, 22, 20], 1):
        summary_ws.column_dimensions[openpyxl.utils.get_column_letter(index)].width = width

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="BC_Nhap_hang_{from_date}_{to_date}.xlsx"'
    wb.save(response)
    return response


@login_required(login_url="/login/")
@report_permission_required
def export_finance_excel(request):
    """Xuất báo cáo tài chính ra Excel"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse

    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    store_id = request.GET.get('store_id')
    today = datetime.now().date()
    if not from_date:
        from_date = today.replace(day=1).strftime('%Y-%m-%d')
    if not to_date:
        to_date = today.strftime('%Y-%m-%d')

    receipts, payments, goods_receipts = _get_finance_report_querysets(
        request,
        from_date,
        to_date,
        store_id,
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Thu chi'
    hf = Font(bold=True, size=14, color='FFFFFF')
    hfill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
    sf = Font(bold=True, size=10, color='FFFFFF')
    sfill = PatternFill(start_color='2E75B6', end_color='2E75B6', fill_type='solid')
    thin = Border(left=Side(style='thin'), right=Side(style='thin'),
                  top=Side(style='thin'), bottom=Side(style='thin'))
    green_fill = PatternFill(start_color='E8F5E9', end_color='E8F5E9', fill_type='solid')
    red_fill = PatternFill(start_color='FFEBEE', end_color='FFEBEE', fill_type='solid')
    goods_fill = PatternFill(start_color='FFF3E0', end_color='FFF3E0', fill_type='solid')
    tfill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
    mfmt = '#,##0'

    ws.merge_cells('A1:G1')
    ws['A1'] = 'BÁO CÁO TÀI CHÍNH'
    ws['A1'].font = hf
    ws['A1'].fill = hfill
    ws['A1'].alignment = Alignment(horizontal='center')
    ws.merge_cells('A2:G2')
    ws['A2'] = f'Từ {from_date} đến {to_date}'
    ws['A2'].font = Font(italic=True, size=10)
    ws['A2'].alignment = Alignment(horizontal='center')

    # Summary row
    total_income = float(receipts.aggregate(s=Sum('amount'))['s'] or 0)
    payment_expense = float(payments.aggregate(s=Sum('amount'))['s'] or 0)
    goods_receipt_expense = float(
        goods_receipts.aggregate(s=Sum('total_amount'))['s'] or 0
    )
    total_expense = payment_expense + goods_receipt_expense
    net = total_income - total_expense
    ws['A3'] = (
        f'Tổng thu: {total_income:,.0f}đ  |  '
        f'Tổng phiếu chi: {payment_expense:,.0f}đ  |  '
        f'Tổng hàng nhập: {goods_receipt_expense:,.0f}đ'
    )
    ws['A3'].font = Font(bold=True, size=10)
    ws.merge_cells('A3:G3')
    ws['A4'] = (
        f'Tổng chi = Tổng phiếu chi + Tổng hàng nhập: {total_expense:,.0f}đ  |  '
        f'Lãi/Lỗ: {net:,.0f}đ'
    )
    ws['A4'].font = Font(bold=True, size=10)
    ws.merge_cells('A4:G4')

    headers = ['STT', 'Loại', 'Mã phiếu', 'Ngày', 'Danh mục', 'Diễn giải', 'Số tiền']
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=5, column=col, value=h)
        c.font = sf
        c.fill = sfill
        c.alignment = Alignment(horizontal='center')
        c.border = thin

    row = 6
    idx = 1
    # Ghi phiếu thu
    for r in receipts.select_related('category').order_by('-receipt_date'):
        vals = [idx, 'THU', r.code,
                r.receipt_date.strftime('%d/%m/%Y') if r.receipt_date else '',
                r.category.name if r.category else '',
                r.description or '', float(r.amount)]
        for col, val in enumerate(vals, 1):
            c = ws.cell(row=row, column=col, value=val)
            c.border = thin
            c.fill = green_fill
            if col == 7:
                c.number_format = mfmt
        idx += 1
        row += 1

    # Ghi phiếu chi
    for p in payments.select_related('category').order_by('-payment_date'):
        vals = [idx, 'CHI', p.code,
                p.payment_date.strftime('%d/%m/%Y') if p.payment_date else '',
                p.category.name if p.category else '',
                p.description or '', float(p.amount)]
        for col, val in enumerate(vals, 1):
            c = ws.cell(row=row, column=col, value=val)
            c.border = thin
            c.fill = red_fill
            if col == 7:
                c.number_format = mfmt
        idx += 1
        row += 1

    # Ghi phiếu nhập hàng
    for goods_receipt in goods_receipts.select_related(
        'supplier',
        'warehouse',
    ).order_by('-receipt_date'):
        description_parts = []
        if goods_receipt.supplier:
            description_parts.append(f'NCC: {goods_receipt.supplier.name}')
        if goods_receipt.warehouse:
            description_parts.append(f'Kho: {goods_receipt.warehouse.name}')
        if goods_receipt.note:
            description_parts.append(goods_receipt.note)
        vals = [
            idx,
            'NHẬP HÀNG',
            goods_receipt.code,
            goods_receipt.receipt_date.strftime('%d/%m/%Y') if goods_receipt.receipt_date else '',
            'Hàng nhập (phiếu nhập)',
            ' · '.join(description_parts),
            float(goods_receipt.total_amount),
        ]
        for col, val in enumerate(vals, 1):
            c = ws.cell(row=row, column=col, value=val)
            c.border = thin
            c.fill = goods_fill
            if col == 7:
                c.number_format = mfmt
        idx += 1
        row += 1

    # Total rows
    for label, amt, fill in [('TỔNG THU', total_income, green_fill),
                             ('TỔNG PHIẾU CHI', payment_expense, red_fill),
                             ('TỔNG HÀNG NHẬP', goods_receipt_expense, goods_fill),
                             ('TỔNG CHI', total_expense, red_fill)]:
        for col, val in enumerate(['', label, '', '', '', '', amt], 1):
            c = ws.cell(row=row, column=col, value=val)
            c.font = Font(bold=True)
            c.fill = fill
            c.border = thin
            if col == 7:
                c.number_format = mfmt
        row += 1
    for col, val in enumerate(['', 'LÃI/LỖ', '', '', '', '', net], 1):
        c = ws.cell(row=row, column=col, value=val)
        c.font = Font(bold=True, color='006600' if net >= 0 else 'CC0000')
        c.fill = tfill
        c.border = thin
        if col == 7:
            c.number_format = mfmt

    for i, w in enumerate([6, 13, 18, 12, 24, 38, 18], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="BC_Thu_chi_{from_date}_{to_date}.xlsx"'
    wb.save(response)
    return response
