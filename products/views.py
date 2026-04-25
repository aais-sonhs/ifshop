import json
import logging
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone
from .models import (
    Product, ProductCategory, ProductVariant, ProductStock, Supplier, Warehouse,
    GoodsReceipt, GoodsReceiptItem, PurchaseOrder, PurchaseOrderItem,
    StockCheck, StockCheckItem, StockTransfer, StockTransferItem, CostAdjustment,
    ComboItem, ProductLocation
)

from core.store_utils import (
    can_manage_users,
    filter_by_store,
    get_user_store,
    get_managed_store_ids,
    brand_owner_required,
)

logger = logging.getLogger(__name__)


def _forbid_json(message='Bạn không có quyền thực hiện thao tác này'):
    return JsonResponse({'status': 'error', 'message': message}, status=403)


def _generate_next_goods_receipt_code():
    last_receipt = (
        GoodsReceipt.objects
        .select_for_update()
        .filter(code__startswith='P')
        .order_by('-id')
        .first()
    )
    if last_receipt and last_receipt.code and last_receipt.code.startswith('P'):
        try:
            next_number = int(last_receipt.code[1:]) + 1
        except ValueError:
            next_number = GoodsReceipt.objects.filter(code__startswith='P').count() + 1
    else:
        next_number = 1

    candidate = f'P{next_number:05d}'
    while GoodsReceipt.objects.filter(code=candidate).exists():
        next_number += 1
        candidate = f'P{next_number:05d}'
    return candidate


def _get_default_store_for_request(request):
    """Return the store new business records should belong to."""
    from system_management.models import Store

    store = get_user_store(request)
    if store:
        return store

    store_ids = get_managed_store_ids(request.user)
    if not store_ids:
        return None
    return Store.objects.filter(id__in=store_ids).order_by('id').first()


def _product_queryset_for_request(request):
    return filter_by_store(Product.objects.all(), request)


def _parse_positive_decimal(value, default='0'):
    try:
        parsed = Decimal(str(value if value not in (None, '') else default))
    except (InvalidOperation, TypeError, ValueError):
        parsed = Decimal(default)
    return parsed


def _to_decimal(value, default='0'):
    try:
        return Decimal(str(value if value not in (None, '') else default))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(str(default))


def _adjust_stock_quantity(stock, delta):
    """Cộng/trừ tồn kho bằng Decimal để tránh lệch số sau nhiều lần cập nhật."""
    stock.quantity = _to_decimal(stock.quantity) + _to_decimal(delta)
    stock.save(update_fields=['quantity'])


def _get_locked_stock(product_id, warehouse_id):
    stock, _ = ProductStock.objects.select_for_update().get_or_create(
        product_id=product_id,
        warehouse_id=warehouse_id,
        defaults={'quantity': 0},
    )
    return stock


def _allow_negative_stock_for_warehouse_id(warehouse_id):
    if not warehouse_id:
        return False
    try:
        from system_management.models import BusinessConfig

        warehouse = Warehouse.objects.select_related('store__brand').filter(id=warehouse_id).first()
        if not warehouse or not warehouse.store:
            return False
        brand = warehouse.store.brand if warehouse.store.brand_id else None
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


def _get_goods_receipt_for_user(request, receipt_id, queryset=None):
    """Lấy phiếu nhập trong phạm vi store mà user được phép thao tác."""
    if not receipt_id:
        return None
    base_queryset = queryset if queryset is not None else GoodsReceipt.objects.all()
    return filter_by_store(base_queryset, request, field_name='warehouse__store').filter(id=receipt_id).first()


def _get_warehouse_for_user(request, warehouse_id):
    if not warehouse_id:
        return None
    return filter_by_store(Warehouse.objects.filter(id=warehouse_id), request).first()


def _get_product_for_user(request, product_id):
    if not product_id:
        return None
    return _product_queryset_for_request(request).filter(id=product_id).first()


def _get_variant_for_product(product, variant_id):
    if not variant_id:
        return None
    return ProductVariant.objects.filter(id=variant_id, product=product).first()


def _ensure_product_matches_store(product, store_id, context='chứng từ'):
    if product and store_id and product.store_id and product.store_id != store_id:
        raise ValueError(f'Sản phẩm "{product.name}" không cùng cửa hàng với {context}.')


def _ensure_warehouses_same_store(from_warehouse, to_warehouse):
    if (
        from_warehouse and to_warehouse and
        from_warehouse.store_id and to_warehouse.store_id and
        from_warehouse.store_id != to_warehouse.store_id
    ):
        raise ValueError('Kho xuất và kho nhập phải thuộc cùng cửa hàng.')


def _get_stock_transfer_for_user(request, transfer_id, queryset=None):
    """Lấy phiếu chuyển kho trong phạm vi store mà user được phép thao tác."""
    if not transfer_id:
        return None
    base_queryset = queryset if queryset is not None else StockTransfer.objects.all()
    return filter_by_store(base_queryset, request, field_name='from_warehouse__store').filter(id=transfer_id).first()


def _get_stock_check_for_user(request, check_id, queryset=None):
    if not check_id:
        return None
    base_queryset = queryset if queryset is not None else StockCheck.objects.all()
    return filter_by_store(base_queryset, request, field_name='warehouse__store').filter(id=check_id).first()


def _get_purchase_order_for_user(request, purchase_order_id, queryset=None):
    if not purchase_order_id:
        return None
    base_queryset = queryset if queryset is not None else PurchaseOrder.objects.all()
    return filter_by_store(base_queryset, request, field_name='warehouse__store').filter(id=purchase_order_id).first()


def _normalize_goods_receipt_items(items_data):
    """Chuẩn hóa danh sách item phiếu nhập về Decimal để tái sử dụng an toàn."""
    normalized_items = []
    total_amount = Decimal('0')

    for item in items_data:
        quantity = _to_decimal(item.get('quantity', 0))
        unit_price = _to_decimal(item.get('unit_price', 0))
        line_total = quantity * unit_price
        normalized_items.append({
            'product_id': item.get('product_id'),
            'variant_id': item.get('variant_id') or None,
            'quantity': quantity,
            'unit_price': unit_price,
            'total_price': line_total,
        })
        total_amount += line_total

    return normalized_items, total_amount


def _calculate_goods_receipt_totals(items):
    """Tính tổng số lượng và tổng tiền trực tiếp từ dòng chi tiết phiếu nhập."""
    total_quantity = Decimal('0')
    total_amount = Decimal('0')
    for item in items:
        quantity = _to_decimal(item.quantity)
        unit_price = _to_decimal(item.unit_price)
        total_quantity += quantity
        total_amount += quantity * unit_price
    return total_quantity, total_amount


def _apply_goods_receipt_stock_adjustment(receipt, warehouse_id, multiplier):
    """Áp biến động tồn kho cho phiếu nhập theo chiều cộng hoặc hoàn tác.

    - `multiplier = 1`: cộng tồn theo item phiếu nhập
    - `multiplier = -1`: hoàn tác phần tồn đã cộng trước đó
    """
    if not warehouse_id:
        return

    allow_negative = True
    if _to_decimal(multiplier) < 0:
        allow_negative = _allow_negative_stock_for_warehouse_id(warehouse_id)

    for item in receipt.items.all():
        stock = _get_locked_stock(item.product_id, warehouse_id)
        _adjust_locked_stock(
            stock,
            _to_decimal(item.quantity) * _to_decimal(multiplier),
            allow_negative=allow_negative,
        )


def _sync_product_cost_after_goods_receipt(product_id, received_quantity, received_price):
    """Cập nhật giá vốn tham chiếu và giá nhập mới nhất sau khi nhập hàng hoàn thành."""
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return

    total_old_stock = Decimal(str(sum(
        float(stock.quantity) for stock in ProductStock.objects.filter(product_id=product_id)
    ))) - received_quantity
    if total_old_stock < 0:
        total_old_stock = Decimal('0')

    total_new_stock = total_old_stock + received_quantity
    if total_new_stock > 0:
        old_cost = product.cost_price or Decimal('0')
        weighted_avg = (
            (total_old_stock * old_cost) + (received_quantity * received_price)
        ) / total_new_stock
        product.cost_price = round(weighted_avg)

    product.import_price = received_price
    product.save(update_fields=['cost_price', 'import_price'])


def _recreate_goods_receipt_items(receipt, normalized_items):
    """Xóa item cũ và tạo lại item mới cho phiếu nhập."""
    receipt.items.all().delete()
    for item in normalized_items:
        GoodsReceiptItem.objects.create(
            goods_receipt=receipt,
            product_id=item['product_id'],
            variant_id=item['variant_id'],
            quantity=item['quantity'],
            unit_price=item['unit_price'],
            total_price=item['total_price'],
        )


def _normalize_stock_transfer_items(items_data):
    """Chuẩn hóa danh sách item phiếu chuyển kho về Decimal để tái sử dụng an toàn."""
    normalized_items = []
    for item in items_data:
        normalized_items.append({
            'product_id': item.get('product_id'),
            'variant_id': item.get('variant_id') or None,
            'quantity': _to_decimal(item.get('quantity', 0)),
        })
    return normalized_items


def _apply_stock_transfer_adjustment(transfer, from_warehouse_id, to_warehouse_id, reverse=False):
    """Áp hoặc hoàn tác tồn kho cho phiếu chuyển kho.

    - `reverse=False`: trừ kho xuất, cộng kho nhập
    - `reverse=True`: hoàn tác phiếu đã hoàn thành trước đó
    """
    if not from_warehouse_id or not to_warehouse_id:
        return

    from_multiplier = Decimal('1') if reverse else Decimal('-1')
    to_multiplier = Decimal('-1') if reverse else Decimal('1')

    for item in transfer.items.all():
        quantity = _to_decimal(item.quantity)
        from_stock = _get_locked_stock(item.product_id, from_warehouse_id)
        from_delta = quantity * from_multiplier
        _adjust_locked_stock(
            from_stock,
            from_delta,
            allow_negative=from_delta >= 0 or _allow_negative_stock_for_warehouse_id(from_warehouse_id),
        )

        to_stock = _get_locked_stock(item.product_id, to_warehouse_id)
        to_delta = quantity * to_multiplier
        _adjust_locked_stock(
            to_stock,
            to_delta,
            allow_negative=to_delta >= 0 or _allow_negative_stock_for_warehouse_id(to_warehouse_id),
        )


def _recreate_stock_transfer_items(transfer, normalized_items):
    """Xóa item cũ và tạo lại item mới cho phiếu chuyển kho."""
    transfer.items.all().delete()
    for item in normalized_items:
        StockTransferItem.objects.create(
            transfer=transfer,
            product_id=item['product_id'],
            variant_id=item['variant_id'],
            quantity=item['quantity'],
        )


def _combo_signature(combo_product):
    return {
        (item.product_id, Decimal(str(item.quantity)).normalize())
        for item in combo_product.combo_items.all()
    }


def _validate_combo_items(product, combo_data, request):
    if not isinstance(combo_data, list):
        raise ValueError('Danh sách thành phần combo không hợp lệ.')
    if len(combo_data) > 20:
        raise ValueError('Một combo chỉ nên có tối đa 20 sản phẩm thành phần.')

    seen = set()
    normalized = []
    for item in combo_data:
        product_id = item.get('product_id') if isinstance(item, dict) else None
        if not product_id:
            continue
        product_id = int(product_id)
        if product.id and product_id == product.id:
            raise ValueError('Combo không được chứa chính nó trong thành phần.')
        if product_id in seen:
            raise ValueError('Không được chọn trùng sản phẩm trong cùng một combo.')
        seen.add(product_id)

        quantity = _parse_positive_decimal(item.get('quantity'), '1')
        if quantity <= 0:
            raise ValueError('Số lượng thành phần combo phải lớn hơn 0.')

        component = _product_queryset_for_request(request).filter(
            id=product_id,
            is_active=True,
        ).first()
        if not component:
            raise ValueError('Có sản phẩm thành phần không tồn tại hoặc không thuộc cửa hàng hiện tại.')
        if component.is_combo:
            raise ValueError(f'Không thể dùng combo "{component.name}" làm thành phần của combo khác.')
        normalized.append((component, quantity))

    if not normalized:
        raise ValueError('Vui lòng chọn ít nhất 1 sản phẩm thành phần cho combo.')
    return normalized


def _combo_stock_by_warehouse(product):
    """
    Combo không có tồn kho riêng; tồn khả dụng = min(tồn thành phần / định lượng)
    theo từng kho. Thành phần dịch vụ không giới hạn tồn combo.
    """
    capacities = None
    warehouse_names = {}

    combo_items = product.combo_items.select_related('product').prefetch_related(
        'product__stocks__warehouse'
    )
    for item in combo_items:
        component = item.product
        if not component or component.is_service:
            continue
        required_qty = _parse_positive_decimal(item.quantity, '0')
        if required_qty <= 0:
            continue

        component_capacity = {}
        for stock in component.stocks.all():
            if not stock.warehouse_id:
                continue
            warehouse_names[stock.warehouse_id] = stock.warehouse.name if stock.warehouse else ''
            stock_qty = _parse_positive_decimal(stock.quantity, '0')
            capacity = (stock_qty / required_qty).to_integral_value(rounding=ROUND_FLOOR)
            component_capacity[stock.warehouse_id] = int(capacity)

        if capacities is None:
            capacities = component_capacity
        else:
            warehouse_ids = set(capacities.keys()) | set(component_capacity.keys())
            capacities = {
                warehouse_id: min(capacities.get(warehouse_id, 0), component_capacity.get(warehouse_id, 0))
                for warehouse_id in warehouse_ids
            }

    if capacities is None:
        return [], 0

    rows = []
    total_stock = 0
    for warehouse_id, quantity in sorted(capacities.items(), key=lambda row: warehouse_names.get(row[0], '')):
        total_stock += quantity
        if quantity != 0:
            rows.append({
                'warehouse': warehouse_names.get(warehouse_id, ''),
                'warehouse_id': warehouse_id,
                'quantity': float(quantity),
            })
    return rows, float(total_stock)


def _build_receipt_history_map(products):
    product_ids = [p.id for p in products]
    if not product_ids:
        return {}

    all_receipt_items = (
        GoodsReceiptItem.objects
        .filter(
            product_id__in=product_ids,
            goods_receipt__status=1,
        )
        .select_related('goods_receipt', 'goods_receipt__supplier', 'goods_receipt__warehouse', 'variant')
        .order_by('-goods_receipt__receipt_date', '-goods_receipt__id', '-id')
    )

    receipt_map = {}
    for receipt_item in all_receipt_items:
        receipt_map.setdefault(receipt_item.product_id, []).append(receipt_item)
    return receipt_map


def _calc_on_hand_cost_price(product_id, total_stock, receipt_map):
    """
    Giá vốn tồn hiện tại = tổng giá trị các lô nhập còn lại / tổng SL tồn hiện tại.
    Duyệt phiếu nhập mới nhất -> cũ nhất để xác định những lô còn nằm trong số tồn.
    """
    if total_stock <= 0:
        return 0

    receipt_items = receipt_map.get(product_id, [])
    if not receipt_items:
        return 0

    remaining = total_stock
    weighted_sum = 0.0
    for receipt_item in receipt_items:
        quantity = float(receipt_item.quantity)
        unit_price = float(receipt_item.unit_price)
        if quantity <= 0:
            continue

        allocated = min(remaining, quantity)
        weighted_sum += allocated * unit_price
        remaining -= allocated
        if remaining <= 0:
            break

    return round(weighted_sum / total_stock) if total_stock > 0 else 0


# ============ PAGE VIEWS ============

@login_required(login_url="/login/")
@brand_owner_required
def product_tbl(request):
    store_ids = get_managed_store_ids(request.user)
    context = {
        'active_tab': 'product_tbl',
        'categories': list(ProductCategory.objects.filter(is_active=True).values('id', 'name')),
        'suppliers': list(Supplier.objects.filter(is_active=True).values('id', 'name')),
        'locations': list(ProductLocation.objects.filter(is_active=True).values('id', 'name')),
        'warehouses': list(Warehouse.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'name')),
    }
    return render(request, "products/product_list.html", context)


@login_required(login_url="/login/")
@brand_owner_required
def warehouse_tbl(request):
    context = {'active_tab': 'warehouse_tbl'}
    return render(request, "products/warehouse_list.html", context)


@login_required(login_url="/login/")
@brand_owner_required
def purchase_order_tbl(request):
    store_ids = get_managed_store_ids(request.user)
    context = {
        'active_tab': 'purchase_order_tbl',
        'suppliers': list(Supplier.objects.filter(is_active=True).values('id', 'name')),
        'warehouses': list(Warehouse.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'name')),
        'products': list(Product.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'code', 'name', 'cost_price', 'unit')),
    }
    return render(request, "products/purchase_order_list.html", context)


@login_required(login_url="/login/")
@brand_owner_required
def goods_receipt_tbl(request):
    store_ids = get_managed_store_ids(request.user)
    context = {
        'active_tab': 'goods_receipt_tbl',
        'suppliers': list(Supplier.objects.filter(is_active=True).values('id', 'name')),
        'warehouses': list(Warehouse.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'name')),
        'products': list(Product.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'code', 'name', 'cost_price', 'unit')),
    }
    return render(request, "products/goods_receipt_list.html", context)


@login_required(login_url="/login/")
@brand_owner_required
def stock_check_tbl(request):
    store_ids = get_managed_store_ids(request.user)
    context = {
        'active_tab': 'stock_check_tbl',
        'warehouses': list(Warehouse.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'name')),
        'products': list(Product.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'code', 'name', 'unit')),
    }
    return render(request, "products/stock_check_list.html", context)


@login_required(login_url="/login/")
@brand_owner_required
def stock_transfer_tbl(request):
    store_ids = get_managed_store_ids(request.user)
    context = {
        'active_tab': 'stock_transfer_tbl',
        'warehouses': list(Warehouse.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'name')),
        'products': list(Product.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'code', 'name', 'unit')),
    }
    return render(request, "products/stock_transfer_list.html", context)


@login_required(login_url="/login/")
@brand_owner_required
def supplier_tbl(request):
    context = {'active_tab': 'supplier_tbl'}
    return render(request, "products/supplier_list.html", context)


@login_required(login_url="/login/")
def cost_adjustment_tbl(request):
    context = {'active_tab': 'cost_adjustment_tbl'}
    return render(request, "products/cost_adjustment_list.html", context)


# ============ API: PRODUCT ============

@login_required(login_url="/login/")
def api_get_products(request):
    products = Product.objects.select_related('category', 'supplier', 'location').prefetch_related(
        'variants', 'stocks__warehouse', 'combo_items__product__stocks__warehouse',
        'receipt_items__goods_receipt',
    ).all()
    products = filter_by_store(products, request)
    receipt_map = _build_receipt_history_map(products)

    data = []
    for p in products:
        receipt_items = receipt_map.get(p.id, [])
        variants = [{
            'id': v.id,
            'size_name': v.size_name,
            'sku': v.sku,
            'barcode': v.barcode or '',
            'import_price': float(v.import_price),
            'cost_price': float(v.cost_price),
            'selling_price': float(v.selling_price),
            'wholesale_price_no_warranty': float(v.wholesale_price_no_warranty),
            'wholesale_price_warranty': float(v.wholesale_price_warranty),
            'is_active': v.is_active,
        } for v in p.variants.all()]

        # Combo items
        combo_items = []
        if p.is_combo:
            combo_items = [{
                'product_id': ci.product_id,
                'product_code': ci.product.code if ci.product else '',
                'product_name': ci.product.name if ci.product else '',
                'is_service': ci.product.is_service if ci.product else False,
                'quantity': float(ci.quantity),
                'selling_price': float(ci.product.selling_price) if ci.product else 0,
            } for ci in p.combo_items.select_related('product').all()]

        stock_by_warehouse = [{
            'warehouse': s.warehouse.name if s.warehouse else '',
            'warehouse_id': s.warehouse_id,
            'quantity': float(s.quantity),
        } for s in p.stocks.select_related('warehouse').all() if float(s.quantity) != 0]

        if p.is_combo:
            stock_by_warehouse, total_stock = _combo_stock_by_warehouse(p)
        else:
            total_stock = float(sum(s.quantity for s in p.stocks.all()))

        current_cost = _calc_on_hand_cost_price(p.id, total_stock, receipt_map)
        effective_cost = current_cost if current_cost > 0 else float(p.cost_price)

        latest_purchase = None
        recent_import_prices = []
        purchase_receipt_count = 0
        purchase_total_quantity = 0
        if receipt_items:
            latest_item = receipt_items[0]
            latest_purchase = {
                'receipt_code': latest_item.goods_receipt.code if latest_item.goods_receipt else '',
                'receipt_date': latest_item.goods_receipt.receipt_date.strftime('%d/%m/%Y') if latest_item.goods_receipt and latest_item.goods_receipt.receipt_date else '',
                'receipt_date_raw': latest_item.goods_receipt.receipt_date.strftime('%Y-%m-%d') if latest_item.goods_receipt and latest_item.goods_receipt.receipt_date else '',
                'supplier': latest_item.goods_receipt.supplier.name if latest_item.goods_receipt and latest_item.goods_receipt.supplier else '',
                'warehouse': latest_item.goods_receipt.warehouse.name if latest_item.goods_receipt and latest_item.goods_receipt.warehouse else '',
                'variant': latest_item.variant.size_name if latest_item.variant else '',
                'quantity': float(latest_item.quantity),
                'unit_price': float(latest_item.unit_price),
            }
            seen_receipts = set()
            for item in receipt_items:
                purchase_total_quantity += float(item.quantity or 0)
                if item.goods_receipt_id:
                    seen_receipts.add(item.goods_receipt_id)
            purchase_receipt_count = len(seen_receipts)
            recent_import_prices = [{
                'date': item.goods_receipt.receipt_date.strftime('%d/%m/%Y') if item.goods_receipt and item.goods_receipt.receipt_date else '',
                'price': float(item.unit_price),
                'quantity': float(item.quantity),
            } for item in receipt_items[:3]]

        data.append({
            'id': p.id, 'code': p.code, 'name': p.name, 'barcode': p.barcode or '',
            'category': p.category.name if p.category else '',
            'category_id': p.category_id,
            'unit': p.unit,
            'import_price': float(p.import_price),
            'cost_price': effective_cost,
            'cost_price_stored': float(p.cost_price),
            'selling_price': float(p.selling_price),
            'wholesale_price_no_warranty': float(p.wholesale_price_no_warranty),
            'wholesale_price_warranty': float(p.wholesale_price_warranty),
            'min_stock': p.min_stock, 'max_stock': p.max_stock,
            'supplier': p.supplier.name if p.supplier else '',
            'supplier_id': p.supplier_id,
            'total_stock': total_stock,
            'stock_by_warehouse': stock_by_warehouse,
            'image': p.image.url if p.image else '',
            'description': p.description or '',
            'is_active': p.is_active,
            'is_weight_based': p.is_weight_based,
            'is_service': p.is_service,
            'is_combo': p.is_combo,
            'combo_items': combo_items,
            'variants': variants,
            'location_id': p.location_id,
            'location': p.location.name if p.location else '',
            'specification': p.specification or '',
            'created_at': p.created_at.strftime('%Y-%m-%d') if p.created_at else '',
            'latest_purchase': latest_purchase,
            'recent_import_prices': recent_import_prices,
            'purchase_receipt_count': purchase_receipt_count,
            'purchase_total_quantity': purchase_total_quantity,
        })
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_product(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        with transaction.atomic():
            product_id = request.POST.get('id')
            if product_id:
                product = _product_queryset_for_request(request).get(id=product_id)
                was_combo = product.is_combo
                existing_combo_signature = _combo_signature(product) if was_combo else set()
            else:
                product = Product(created_by=request.user, store=_get_default_store_for_request(request))
                was_combo = False
                existing_combo_signature = set()

            product.code = (request.POST.get('code', '') or '').strip()
            product.name = (request.POST.get('name', '') or '').strip()
            if not product.code or not product.name:
                return JsonResponse({'status': 'error', 'message': 'Vui lòng nhập mã và tên SP'})

            product.barcode = request.POST.get('barcode', '')
            product.unit = request.POST.get('unit', 'Cái')
            product.import_price = request.POST.get('import_price', 0) or 0
            product.selling_price = request.POST.get('selling_price', 0) or 0
            product.wholesale_price_no_warranty = request.POST.get('wholesale_price_no_warranty', 0) or 0
            product.wholesale_price_warranty = request.POST.get('wholesale_price_warranty', 0) or 0
            product.min_stock = request.POST.get('min_stock', 0) or 0
            product.max_stock = request.POST.get('max_stock', 0) or 0
            product.description = request.POST.get('description', '')
            product.is_weight_based = request.POST.get('is_weight_based', '0') == '1'
            product.is_service = request.POST.get('is_service', '0') == '1'
            product.is_combo = request.POST.get('is_combo', '0') == '1'
            product.specification = request.POST.get('specification', '') or None
            if product.is_combo:
                product.is_service = False

            cat_id = request.POST.get('category_id')
            product.category_id = cat_id if cat_id else None
            sup_id = request.POST.get('supplier_id')
            product.supplier_id = sup_id if sup_id else None
            loc_id = request.POST.get('location_id')
            product.location_id = loc_id if loc_id else None

            skip_variants = request.POST.get('skip_variants', '0') == '1'
            variants_data = json.loads(request.POST.get('variants', '[]') or '[]')
            combo_data = json.loads(request.POST.get('combo_items', '[]') or '[]')
            normalized_combo_items = _validate_combo_items(product, combo_data, request) if product.is_combo else []
            if was_combo and existing_combo_signature and not product.is_combo:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Combo đã lưu không nên chuyển về sản phẩm thường. Hãy ẩn combo cũ và tạo sản phẩm mới nếu cần.',
                })
            if product.is_combo and was_combo and existing_combo_signature:
                new_signature = {
                    (component.id, quantity.normalize())
                    for component, quantity in normalized_combo_items
                }
                if new_signature != existing_combo_signature:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Combo đã lưu không nên đổi thành phần. Hãy tạo combo mới nếu cần cấu hình khác.',
                    })

            if 'image' in request.FILES:
                product.image = request.FILES['image']

            product.save()

            # Luồng form mới không còn chỉnh biến thể/kích thước.
            # Nếu client không yêu cầu sửa biến thể, giữ nguyên dữ liệu cũ.
            if not skip_variants:
                product.variants.all().delete()
                for v in variants_data:
                    ProductVariant.objects.create(
                        product=product,
                        size_name=v.get('size_name', ''),
                        sku=v.get('sku', ''),
                        barcode=v.get('barcode', ''),
                        import_price=v.get('import_price', 0) or 0,
                        cost_price=v.get('cost_price', 0) or 0,
                        selling_price=v.get('selling_price', 0) or 0,
                        wholesale_price_no_warranty=v.get('wholesale_price_no_warranty', 0) or 0,
                        wholesale_price_warranty=v.get('wholesale_price_warranty', 0) or 0,
                    )

            if product.is_combo:
                if not existing_combo_signature:
                    product.combo_items.all().delete()
                    for component, quantity in normalized_combo_items:
                        ComboItem.objects.create(
                            combo=product,
                            product=component,
                            quantity=quantity,
                        )

                total_cost = sum(
                    Decimal(str(component.cost_price or 0)) * quantity
                    for component, quantity in normalized_combo_items
                )
                product.cost_price = total_cost
                product.save(update_fields=['cost_price'])
            else:
                product.combo_items.all().delete()

        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Product.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy sản phẩm'})
    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': str(e)})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_product(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        product = _product_queryset_for_request(request).get(id=data.get('id'))

        # Kiểm tra SP đã được dùng trong đơn hàng chưa
        from orders.models import OrderItem
        order_count = OrderItem.objects.filter(product=product).count()
        if order_count > 0:
            return JsonResponse({
                'status': 'error',
                'message': f'🔒 Không thể xóa "{product.name}" vì đã có {order_count} '
                f'đơn hàng sử dụng sản phẩm này. '
                f'Bạn có thể ẩn sản phẩm bằng cách bỏ tích "Đang hoạt động".'
            })

        product.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Product.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy sản phẩm'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: WAREHOUSE ============

@login_required(login_url="/login/")
def api_get_warehouses(request):
    warehouses = Warehouse.objects.all()
    warehouses = filter_by_store(warehouses, request)
    data = [{
        'id': w.id, 'code': w.code, 'name': w.name,
        'address': w.address or '', 'manager': w.manager.username if w.manager else '',
        'is_active': w.is_active,
    } for w in warehouses]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_warehouse(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        wh_id = data.get('id')
        if wh_id:
            wh = _get_warehouse_for_user(request, wh_id)
            if not wh:
                return JsonResponse({'status': 'error', 'message': 'Không tìm thấy kho'})
        else:
            wh = Warehouse()
            wh.store = _get_default_store_for_request(request)
            if not wh.store:
                return JsonResponse({'status': 'error', 'message': 'Tài khoản chưa có phạm vi cửa hàng hợp lệ'})
        wh.code = data.get('code', '')
        wh.name = data.get('name', '')
        wh.address = data.get('address', '')
        wh.is_active = data.get('is_active', True)
        wh.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_warehouse(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        warehouse = _get_warehouse_for_user(request, data.get('id'))
        if not warehouse:
            return JsonResponse({'status': 'error', 'message': 'Không tìm thấy kho'})
        warehouse.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: SUPPLIER ============

@login_required(login_url="/login/")
def api_get_suppliers(request):
    suppliers = Supplier.objects.all()
    data = [{
        'id': s.id, 'code': s.code, 'name': s.name,
        'phone': s.phone or '', 'email': s.email or '',
        'address': s.address or '', 'tax_code': s.tax_code or '',
        'contact_person': s.contact_person or '', 'note': s.note or '',
        'is_active': s.is_active,
    } for s in suppliers]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_supplier(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    if not can_manage_users(request.user):
        return _forbid_json('Bạn không có quyền cấu hình nhà cung cấp')
    try:
        data = json.loads(request.body)
        sup_id = data.get('id')
        if sup_id:
            sup = Supplier.objects.get(id=sup_id)
        else:
            sup = Supplier()
            sup.created_by = request.user
        sup.code = data.get('code', '')
        sup.name = data.get('name', '')
        sup.phone = data.get('phone', '')
        sup.email = data.get('email', '')
        sup.address = data.get('address', '')
        sup.tax_code = data.get('tax_code', '')
        sup.contact_person = data.get('contact_person', '')
        sup.note = data.get('note', '')
        sup.is_active = data.get('is_active', True)
        sup.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_supplier(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    if not can_manage_users(request.user):
        return _forbid_json('Bạn không có quyền cấu hình nhà cung cấp')
    try:
        data = json.loads(request.body)
        Supplier.objects.filter(id=data.get('id')).delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: PRODUCT CATEGORY ============

@login_required(login_url="/login/")
def api_get_categories(request):
    cats = ProductCategory.objects.all()
    data = [{'id': c.id, 'name': c.name, 'description': c.description or '', 'is_active': c.is_active} for c in cats]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_category(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    if not can_manage_users(request.user):
        return _forbid_json('Bạn không có quyền cấu hình danh mục sản phẩm')
    try:
        data = json.loads(request.body)
        cat_id = data.get('id')
        if cat_id:
            cat = ProductCategory.objects.get(id=cat_id)
        else:
            cat = ProductCategory()
        cat.name = data.get('name', '')
        cat.description = data.get('description', '')
        cat.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: GOODS RECEIPT ============

@login_required(login_url="/login/")
def api_get_goods_receipts(request):
    """Trả về danh sách phiếu nhập trong phạm vi store mà user được phép xem."""
    receipts = GoodsReceipt.objects.select_related('supplier', 'warehouse', 'purchase_order').prefetch_related('items__product').all()
    receipts = filter_by_store(receipts, request, field_name='warehouse__store')
    data = []
    for r in receipts:
        receipt_items = list(r.items.select_related('product', 'variant').all())
        total_quantity, total_amount = _calculate_goods_receipt_totals(receipt_items)
        items = []
        for item in receipt_items:
            quantity = _to_decimal(item.quantity)
            unit_price = _to_decimal(item.unit_price)
            line_total = quantity * unit_price
            items.append({
                'product_id': item.product_id,
                'variant_id': item.variant_id,
                'product_code': item.product.code if item.product else '',
                'product_name': item.product.name if item.product else '',
                'variant_name': item.variant.size_name if item.variant else '',
                'quantity': float(quantity),
                'unit_price': float(unit_price),
                'total_price': float(line_total),
            })
        data.append({
            'id': r.id, 'code': r.code,
            'purchase_order': r.purchase_order.code if r.purchase_order else '',
            'supplier': r.supplier.name if r.supplier else '',
            'supplier_id': r.supplier_id,
            'warehouse': r.warehouse.name if r.warehouse else '',
            'warehouse_id': r.warehouse_id,
            'receipt_date': r.receipt_date.strftime('%Y-%m-%d') if r.receipt_date else '',
            'created_at': r.created_at.strftime('%d/%m/%Y %H:%M:%S') if r.created_at else '',
            'items_count': len(items),
            'total_quantity': float(total_quantity),
            'total_amount': float(total_amount),
            'status': r.status,
            'status_display': r.get_status_display(),
            'note': r.note or '',
            'items': items,
        })
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_goods_receipt(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            # 1. Nạp phiếu cũ nếu là cập nhật để biết cần hoàn tồn ở kho nào.
            gr_id = data.get('id')
            old_status = None
            old_warehouse_id = None
            if gr_id:
                gr = _get_goods_receipt_for_user(
                    request,
                    gr_id,
                    queryset=GoodsReceipt.objects.select_for_update().prefetch_related('items'),
                )
                if not gr:
                    return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phiếu nhập'})
                old_status = gr.status
                old_warehouse_id = gr.warehouse_id
            else:
                gr = GoodsReceipt()
                gr.created_by = request.user

            # Mã phiếu được giữ nguyên khi sửa; chỉ tự tăng khi tạo mới hoặc chưa có mã.
            code = (data.get('code', '') or '').strip()
            if not code:
                code = gr.code or _generate_next_goods_receipt_code()
            gr.code = code

            gr.supplier_id = data.get('supplier_id') or None
            requested_warehouse_id = data.get('warehouse_id') or None
            warehouse = _get_warehouse_for_user(request, requested_warehouse_id) if requested_warehouse_id else None
            if requested_warehouse_id and not warehouse:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Kho nhập không tồn tại hoặc không thuộc phạm vi cửa hàng của bạn.'
                })
            gr.warehouse = warehouse

            # Nếu UI không gửi ngày, giữ nguyên ngày cũ khi sửa; tạo mới thì lấy ngày local hiện tại.
            receipt_date = (data.get('receipt_date', '') or '').strip()
            if not receipt_date:
                if gr.receipt_date:
                    receipt_date = gr.receipt_date.strftime('%Y-%m-%d')
                else:
                    receipt_date = timezone.now().date().strftime('%Y-%m-%d')
            gr.receipt_date = receipt_date

            new_status = int(data.get('status', 1))
            gr.status = new_status
            gr.note = data.get('note', '')

            # 2. Chuẩn hóa item để toàn bộ các bước sau dùng cùng một kiểu dữ liệu.
            normalized_items, total_amount = _normalize_goods_receipt_items(data.get('items', []))
            for item in normalized_items:
                product = _get_product_for_user(request, item['product_id'])
                if not product:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Có sản phẩm không tồn tại hoặc không thuộc cửa hàng hiện tại.'
                    })
                _ensure_product_matches_store(product, warehouse.store_id if warehouse else None, 'kho nhập')
                if item['variant_id'] and not _get_variant_for_product(product, item['variant_id']):
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Biến thể không thuộc sản phẩm "{product.name}".'
                    })
            gr.total_amount = total_amount
            gr.save()

            # 3. Nếu phiếu cũ đã hoàn thành thì hoàn tác tồn theo kho cũ trước khi ghi item mới.
            if old_status == 1 and old_warehouse_id:
                _apply_goods_receipt_stock_adjustment(gr, old_warehouse_id, multiplier=-1)

            # 4. Ghi lại toàn bộ item mới sau khi đã hoàn tác item cũ.
            _recreate_goods_receipt_items(gr, normalized_items)

            # 5. Với phiếu hoàn thành, cộng tồn và đồng bộ giá vốn tham chiếu của sản phẩm.
            if new_status == 1 and gr.warehouse_id:
                _apply_goods_receipt_stock_adjustment(gr, gr.warehouse_id, multiplier=1)
                for item in normalized_items:
                    _sync_product_cost_after_goods_receipt(
                        item['product_id'],
                        item['quantity'],
                        item['unit_price'],
                    )

        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công', 'code': gr.code})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_goods_receipt(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            receipt = _get_goods_receipt_for_user(
                request,
                data.get('id'),
                queryset=GoodsReceipt.objects.select_for_update().prefetch_related('items'),
            )
            if not receipt:
                return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phiếu nhập'})

            # Phiếu nhập đã hoàn thành thì xóa phải hoàn tác phần tồn đã cộng trước đó.
            if receipt.status == 1 and receipt.warehouse_id:
                _apply_goods_receipt_stock_adjustment(receipt, receipt.warehouse_id, multiplier=-1)

            receipt.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: STOCK TRANSFER ============

@login_required(login_url="/login/")
def api_get_stock_transfers(request):
    """Trả về danh sách phiếu chuyển kho trong phạm vi store mà user được phép xem."""
    transfers = StockTransfer.objects.select_related('from_warehouse', 'to_warehouse').prefetch_related('items__product').all()
    transfers = filter_by_store(transfers, request, field_name='from_warehouse__store')
    data = []
    for t in transfers:
        items = [{
            'product_id': item.product_id,
            'variant_id': item.variant_id,
            'product_code': item.product.code if item.product else '',
            'product_name': item.product.name if item.product else '',
            'variant_name': item.variant.size_name if item.variant else '',
            'quantity': float(item.quantity),
        } for item in t.items.select_related('product', 'variant').all()]
        data.append({
            'id': t.id, 'code': t.code,
            'from_warehouse': t.from_warehouse.name if t.from_warehouse else '',
            'from_warehouse_id': t.from_warehouse_id,
            'to_warehouse': t.to_warehouse.name if t.to_warehouse else '',
            'to_warehouse_id': t.to_warehouse_id,
            'transfer_date': t.transfer_date.strftime('%Y-%m-%d') if t.transfer_date else '',
            'created_at': t.created_at.strftime('%d/%m/%Y %H:%M:%S') if t.created_at else '',
            'status': t.status, 'status_display': t.get_status_display(),
            'note': t.note or '',
            'items': items,
        })
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_stock_transfer(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            # 1. Nạp phiếu cũ nếu là cập nhật để biết cần hoàn tác tồn theo cặp kho cũ.
            st_id = data.get('id')
            old_status = None
            old_from_warehouse_id = None
            old_to_warehouse_id = None
            if st_id:
                st = _get_stock_transfer_for_user(
                    request,
                    st_id,
                    queryset=StockTransfer.objects.select_for_update().prefetch_related('items'),
                )
                if not st:
                    return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phiếu chuyển'})
                old_status = st.status
                old_from_warehouse_id = st.from_warehouse_id
                old_to_warehouse_id = st.to_warehouse_id
            else:
                st = StockTransfer()
                st.created_by = request.user

            # 2. Gán dữ liệu cơ bản từ payload.
            st.code = data.get('code', '')
            from_warehouse_id = data.get('from_warehouse_id') or None
            to_warehouse_id = data.get('to_warehouse_id') or None
            from_warehouse = _get_warehouse_for_user(request, from_warehouse_id) if from_warehouse_id else None
            to_warehouse = _get_warehouse_for_user(request, to_warehouse_id) if to_warehouse_id else None
            if from_warehouse_id and not from_warehouse:
                return JsonResponse({'status': 'error', 'message': 'Kho xuất không thuộc phạm vi cửa hàng của bạn.'})
            if to_warehouse_id and not to_warehouse:
                return JsonResponse({'status': 'error', 'message': 'Kho nhập không thuộc phạm vi cửa hàng của bạn.'})
            _ensure_warehouses_same_store(from_warehouse, to_warehouse)
            st.from_warehouse = from_warehouse
            st.to_warehouse = to_warehouse
            st.transfer_date = data.get('transfer_date')
            new_status = int(data.get('status', 0))
            st.status = new_status
            st.note = data.get('note', '')

            # 3. Validate toàn bộ item trước mọi ghi/hoàn tồn để lỗi không commit nửa chừng.
            normalized_items = _normalize_stock_transfer_items(data.get('items', []))
            for item in normalized_items:
                product = _get_product_for_user(request, item['product_id'])
                if not product:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Có sản phẩm không tồn tại hoặc không thuộc cửa hàng hiện tại.'
                    })
                _ensure_product_matches_store(
                    product,
                    from_warehouse.store_id if from_warehouse else (to_warehouse.store_id if to_warehouse else None),
                    'phiếu chuyển kho',
                )
                if item['variant_id'] and not _get_variant_for_product(product, item['variant_id']):
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Biến thể không thuộc sản phẩm "{product.name}".'
                    })

            st.save()

            # 4. Nếu phiếu cũ đã hoàn thành thì hoàn tác tồn theo cặp kho cũ trước khi ghi item mới.
            if old_status == 2 and old_from_warehouse_id and old_to_warehouse_id:
                _apply_stock_transfer_adjustment(
                    st,
                    old_from_warehouse_id,
                    old_to_warehouse_id,
                    reverse=True,
                )

            # 5. Ghi lại item mới theo payload hiện tại.
            _recreate_stock_transfer_items(st, normalized_items)

            # 6. Chỉ khi phiếu ở trạng thái hoàn thành mới áp biến động kho thực tế.
            if new_status == 2 and st.from_warehouse_id and st.to_warehouse_id:
                _apply_stock_transfer_adjustment(
                    st,
                    st.from_warehouse_id,
                    st.to_warehouse_id,
                    reverse=False,
                )

        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_stock_transfer(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            transfer = _get_stock_transfer_for_user(
                request,
                data.get('id'),
                queryset=StockTransfer.objects.select_for_update().prefetch_related('items'),
            )
            if not transfer:
                return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phiếu chuyển'})

            # Phiếu chuyển hoàn thành thì xóa phải hoàn tác tồn ở cả kho xuất và kho nhập.
            if transfer.status == 2 and transfer.from_warehouse_id and transfer.to_warehouse_id:
                _apply_stock_transfer_adjustment(
                    transfer,
                    transfer.from_warehouse_id,
                    transfer.to_warehouse_id,
                    reverse=True,
                )

            transfer.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: STOCK CHECK ============

@login_required(login_url="/login/")
def api_get_stock_checks(request):
    checks = StockCheck.objects.select_related('warehouse').prefetch_related('items__product').all()
    checks = filter_by_store(checks, request, field_name='warehouse__store')
    data = []
    for c in checks:
        items = [{
            'product_id': item.product_id,
            'variant_id': item.variant_id,
            'product_code': item.product.code if item.product else '',
            'product_name': item.product.name if item.product else '',
            'variant_name': item.variant.size_name if item.variant else '',
            'system_quantity': float(item.system_quantity),
            'actual_quantity': float(item.actual_quantity),
            'difference': float(item.difference),
            'note': item.note or '',
        } for item in c.items.select_related('product', 'variant').all()]
        data.append({
            'id': c.id, 'code': c.code,
            'warehouse': c.warehouse.name if c.warehouse else '',
            'warehouse_id': c.warehouse_id,
            'check_date': c.check_date.strftime('%Y-%m-%d') if c.check_date else '',
            'created_at': c.created_at.strftime('%d/%m/%Y %H:%M:%S') if c.created_at else '',
            'status': c.status, 'status_display': c.get_status_display(),
            'note': c.note or '',
            'items': items,
        })
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_stock_check(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            sc_id = data.get('id')
            if sc_id:
                sc = _get_stock_check_for_user(request, sc_id)
                if not sc:
                    return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phiếu kiểm'})
            else:
                sc = StockCheck()
                sc.created_by = request.user
            sc.code = data.get('code', '')
            warehouse_id = data.get('warehouse_id') or None
            warehouse = _get_warehouse_for_user(request, warehouse_id) if warehouse_id else None
            if warehouse_id and not warehouse:
                return JsonResponse({'status': 'error', 'message': 'Kho kiểm không thuộc phạm vi cửa hàng của bạn.'})
            sc.warehouse = warehouse
            items_data = data.get('items', [])
            normalized_items = []
            for item in items_data:
                product_id = item.get('product_id')
                product = _get_product_for_user(request, product_id)
                if not product:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Có sản phẩm không tồn tại hoặc không thuộc cửa hàng hiện tại.'
                    })
                _ensure_product_matches_store(product, warehouse.store_id if warehouse else None, 'kho kiểm')
                variant_id = item.get('variant_id') or None
                if variant_id and not _get_variant_for_product(product, variant_id):
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Biến thể không thuộc sản phẩm "{product.name}".'
                    })
                actual_qty = _to_decimal(item.get('actual_quantity', 0))
                sys_qty = Decimal('0')
                if warehouse and product_id:
                    try:
                        ps = ProductStock.objects.get(product_id=product_id, warehouse=warehouse)
                        sys_qty = _to_decimal(ps.quantity)
                    except ProductStock.DoesNotExist:
                        sys_qty = Decimal('0')
                normalized_items.append((item, product, variant_id, actual_qty, sys_qty))

            sc.check_date = data.get('check_date')
            sc.status = data.get('status', 0)
            sc.note = data.get('note', '')
            sc.save()

            # Save items
            sc.items.all().delete()
            for item, product, variant_id, actual_qty, sys_qty in normalized_items:
                StockCheckItem.objects.create(
                    stock_check=sc,
                    product=product,
                    variant_id=variant_id,
                    system_quantity=sys_qty,
                    actual_quantity=actual_qty,
                    difference=actual_qty - sys_qty,
                    note=item.get('note', ''),
                )

        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_stock_check(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        stock_check = _get_stock_check_for_user(request, data.get('id'))
        if not stock_check:
            return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phiếu kiểm'})
        stock_check.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

# ============ API: PURCHASE ORDER ============


@login_required(login_url="/login/")
def api_get_purchase_orders(request):
    orders = PurchaseOrder.objects.select_related('supplier', 'warehouse').prefetch_related('items__product').all()
    orders = filter_by_store(orders, request, field_name='warehouse__store')
    data = []
    for o in orders:
        items = [{
            'product_id': item.product_id,
            'variant_id': item.variant_id,
            'product_code': item.product.code if item.product else '',
            'product_name': item.product.name if item.product else '',
            'variant_name': item.variant.size_name if item.variant else '',
            'quantity': float(item.quantity),
            'received_quantity': float(item.received_quantity),
            'unit_price': float(item.unit_price),
            'total_price': float(item.total_price),
        } for item in o.items.select_related('product', 'variant').all()]
        data.append({
            'id': o.id, 'code': o.code,
            'supplier': o.supplier.name if o.supplier else '',
            'supplier_id': o.supplier_id,
            'warehouse': o.warehouse.name if o.warehouse else '',
            'warehouse_id': o.warehouse_id,
            'order_date': o.order_date.strftime('%Y-%m-%d') if o.order_date else '',
            'expected_date': o.expected_date.strftime('%Y-%m-%d') if o.expected_date else '',
            'created_at': o.created_at.strftime('%d/%m/%Y %H:%M:%S') if o.created_at else '',
            'total_amount': float(o.total_amount),
            'status': o.status, 'status_display': o.get_status_display(),
            'note': o.note or '',
            'items': items,
        })
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_purchase_order(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        po_id = data.get('id')
        if po_id:
            po = _get_purchase_order_for_user(request, po_id)
            if not po:
                return JsonResponse({'status': 'error', 'message': 'Không tìm thấy đơn đặt hàng'})
        else:
            po = PurchaseOrder()
            po.created_by = request.user
        po.code = data.get('code', '')
        po.supplier_id = data.get('supplier_id') or None
        warehouse_id = data.get('warehouse_id') or None
        warehouse = _get_warehouse_for_user(request, warehouse_id) if warehouse_id else None
        if warehouse_id and not warehouse:
            return JsonResponse({'status': 'error', 'message': 'Kho nhập không thuộc phạm vi cửa hàng của bạn.'})
        po.warehouse = warehouse
        po.order_date = data.get('order_date')
        po.expected_date = data.get('expected_date') or None
        po.status = data.get('status', 0)
        po.note = data.get('note', '')

        items_data = data.get('items', [])
        normalized_items = []
        total = 0
        for item in items_data:
            product = _get_product_for_user(request, item.get('product_id'))
            if not product:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Có sản phẩm không tồn tại hoặc không thuộc cửa hàng hiện tại.'
                })
            _ensure_product_matches_store(product, warehouse.store_id if warehouse else None, 'kho nhập')
            variant_id = item.get('variant_id') or None
            if variant_id and not _get_variant_for_product(product, variant_id):
                return JsonResponse({
                    'status': 'error',
                    'message': f'Biến thể không thuộc sản phẩm "{product.name}".'
                })
            qty = float(item.get('quantity', 0))
            price = float(item.get('unit_price', 0))
            total += qty * price
            normalized_items.append((product, variant_id, qty, price))

        po.total_amount = total
        po.save()

        # Delete old items and create new ones
        po.items.all().delete()
        for product, variant_id, qty, price in normalized_items:
            PurchaseOrderItem.objects.create(
                purchase_order=po,
                product=product,
                variant_id=variant_id,
                quantity=qty,
                unit_price=price,
                total_price=qty * price,
            )

        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: DELETE PURCHASE ORDER ============

@login_required(login_url="/login/")
def api_delete_purchase_order(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        purchase_order = _get_purchase_order_for_user(request, data.get('id'))
        if not purchase_order:
            return JsonResponse({'status': 'error', 'message': 'Không tìm thấy đơn đặt hàng'})
        purchase_order.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: COST ADJUSTMENT ============

@login_required(login_url="/login/")
def api_get_cost_adjustments(request):
    items = CostAdjustment.objects.select_related('product', 'adjusted_by').all()
    items = filter_by_store(items, request, field_name='product__store')
    data = [{
        'id': c.id,
        'product': c.product.name if c.product else '',
        'product_code': c.product.code if c.product else '',
        'old_cost': float(c.old_cost), 'new_cost': float(c.new_cost),
        'reason': c.reason or '',
        'adjusted_by': c.adjusted_by.username if c.adjusted_by else '',
        'adjusted_at': c.adjusted_at.strftime('%d/%m/%Y %H:%M') if c.adjusted_at else '',
    } for c in items]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_product_purchase_history(request):
    """API: Lịch sử nhập hàng của 1 sản phẩm"""
    product_id = request.GET.get('product_id')
    if not product_id:
        return JsonResponse({'status': 'error', 'message': 'Missing product_id'})

    product = _product_queryset_for_request(request).filter(id=product_id).first()
    if not product:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy sản phẩm'})

    store_ids = get_managed_store_ids(request.user)
    items = GoodsReceiptItem.objects.filter(
        product=product,
        goods_receipt__status=1,
        goods_receipt__warehouse__store_id__in=store_ids,
    ).select_related('goods_receipt', 'goods_receipt__supplier', 'goods_receipt__warehouse', 'variant')

    date_from = request.GET.get('date_from') or ''
    date_to = request.GET.get('date_to') or ''
    supplier_id = request.GET.get('supplier_id') or ''
    warehouse_id = request.GET.get('warehouse_id') or ''
    receipt_code = (request.GET.get('receipt_code') or '').strip()
    if date_from:
        items = items.filter(goods_receipt__receipt_date__gte=date_from)
    if date_to:
        items = items.filter(goods_receipt__receipt_date__lte=date_to)
    if supplier_id:
        items = items.filter(goods_receipt__supplier_id=supplier_id)
    if warehouse_id:
        items = items.filter(goods_receipt__warehouse_id=warehouse_id)
    if receipt_code:
        items = items.filter(goods_receipt__code__icontains=receipt_code)

    data = [{
        'receipt_code': it.goods_receipt.code,
        'receipt_date': it.goods_receipt.receipt_date.strftime('%d/%m/%Y') if it.goods_receipt.receipt_date else '',
        'receipt_date_raw': it.goods_receipt.receipt_date.strftime('%Y-%m-%d') if it.goods_receipt.receipt_date else '',
        'supplier': it.goods_receipt.supplier.name if it.goods_receipt.supplier else '',
        'warehouse': it.goods_receipt.warehouse.name if it.goods_receipt.warehouse else '',
        'variant': it.variant.size_name if it.variant else '',
        'quantity': float(it.quantity),
        'unit_price': float(it.unit_price),
        'total_price': float(it.total_price),
    } for it in items.order_by('-goods_receipt__receipt_date', '-goods_receipt__id')]

    price_timeline = [{
        'date': it.goods_receipt.receipt_date.strftime('%d/%m/%Y') if it.goods_receipt.receipt_date else '',
        'price': float(it.unit_price),
        'quantity': float(it.quantity),
    } for it in items.order_by('goods_receipt__receipt_date', 'goods_receipt__id')]

    # Tổng
    total_qty = sum(d['quantity'] for d in data)
    total_amount = sum(d['total_price'] for d in data)
    avg_price = total_amount / total_qty if total_qty > 0 else 0

    return JsonResponse({
        'status': 'ok',
        'data': data,
        'summary': {
            'total_entries': len(data),
            'total_quantity': total_qty,
            'total_amount': total_amount,
            'avg_unit_price': round(avg_price),
        },
        'price_timeline': price_timeline,
    })


@login_required(login_url="/login/")
def api_product_sales_history(request):
    """API: Lịch sử bán hàng (đơn hàng) của 1 sản phẩm"""
    product_id = request.GET.get('product_id')
    if not product_id:
        return JsonResponse({'status': 'error', 'message': 'Missing product_id'})

    product = _product_queryset_for_request(request).filter(id=product_id).first()
    if not product:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy sản phẩm'})

    from orders.models import OrderItem
    store_ids = get_managed_store_ids(request.user)
    items = OrderItem.objects.filter(
        product=product,
        order__store_id__in=store_ids,
        order__status__in=[3, 4, 5],  # Đã duyệt / Đã giao / Hoàn thành
    ).select_related('order', 'order__customer', 'variant')

    date_from = request.GET.get('date_from') or ''
    date_to = request.GET.get('date_to') or ''
    if date_from:
        items = items.filter(order__order_date__gte=date_from)
    if date_to:
        items = items.filter(order__order_date__lte=date_to)

    items = items.order_by('-order__order_date', '-order__id')

    data = [{
        'order_code': it.order.code,
        'order_date': it.order.order_date.strftime('%d/%m/%Y') if it.order.order_date else '',
        'order_date_raw': it.order.order_date.strftime('%Y-%m-%d') if it.order.order_date else '',
        'customer': it.order.customer.name if it.order.customer else '',
        'variant': it.variant.size_name if it.variant else '',
        'quantity': float(it.quantity),
        'unit_price': float(it.unit_price),
        'discount_percent': float(it.discount_percent),
        'total_price': float(it.total_price),
    } for it in items]

    # Tổng
    total_qty = sum(d['quantity'] for d in data)
    total_amount = sum(d['total_price'] for d in data)
    avg_price = total_amount / total_qty if total_qty > 0 else 0

    return JsonResponse({
        'status': 'ok',
        'data': data,
        'summary': {
            'total_orders': len(set(d['order_code'] for d in data)),
            'total_entries': len(data),
            'total_quantity': total_qty,
            'total_amount': total_amount,
            'avg_unit_price': round(avg_price),
        },
    })

# ============ API: PRODUCT LOCATION ============


@login_required(login_url="/login/")
def api_get_locations(request):
    locs = ProductLocation.objects.all()
    data = [
        {'id': location.id, 'name': location.name, 'is_active': location.is_active}
        for location in locs
    ]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_location(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    if not can_manage_users(request.user):
        return _forbid_json('Bạn không có quyền cấu hình vị trí sản phẩm')
    try:
        data = json.loads(request.body)
        loc_id = data.get('id')
        name = (data.get('name', '') or '').strip()
        if not name:
            return JsonResponse({'status': 'error', 'message': 'Vui lòng nhập tên vị trí'})
        if loc_id:
            loc = ProductLocation.objects.get(id=loc_id)
        else:
            loc = ProductLocation()
        # Check duplicate name
        dup = ProductLocation.objects.filter(name=name)
        if loc_id:
            dup = dup.exclude(id=loc_id)
        if dup.exists():
            return JsonResponse({'status': 'error', 'message': f'Vị trí "{name}" đã tồn tại'})
        loc.name = name
        loc.is_active = data.get('is_active', True)
        loc.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công', 'id': loc.id, 'name': loc.name})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_location(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    if not can_manage_users(request.user):
        return _forbid_json('Bạn không có quyền cấu hình vị trí sản phẩm')
    try:
        data = json.loads(request.body)
        loc = ProductLocation.objects.get(id=data.get('id'))
        # Check if any product is using this location
        product_count = Product.objects.filter(location=loc).count()
        if product_count > 0:
            return JsonResponse({
                'status': 'error',
                'message': f'Không thể xóa vị trí "{loc.name}" vì đang được {product_count} sản phẩm sử dụng.'
            })
        loc.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except ProductLocation.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy vị trí'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ EXCEL EXPORT ============

@login_required(login_url="/login/")
def export_products_excel(request):
    """Xuất danh sách sản phẩm ra Excel"""
    from core.excel_export import excel_response
    from datetime import datetime

    products = Product.objects.select_related('category', 'supplier', 'location').prefetch_related(
        'stocks__warehouse',
        'combo_items__product__stocks__warehouse',
    ).all()
    products = filter_by_store(products, request)
    receipt_map = _build_receipt_history_map(products)

    columns = [
        {'key': 'stt', 'label': 'STT', 'width': 6},
        {'key': 'code', 'label': 'Mã SP', 'width': 14},
        {'key': 'name', 'label': 'Tên sản phẩm', 'width': 30},
        {'key': 'barcode', 'label': 'Barcode', 'width': 16},
        {'key': 'category', 'label': 'Danh mục', 'width': 16},
        {'key': 'unit', 'label': 'ĐVT', 'width': 8},
        {'key': 'spec', 'label': 'Quy cách', 'width': 14},
        {'key': 'import_price', 'label': 'Giá nhập', 'width': 14},
        {'key': 'cost_price', 'label': 'Giá vốn', 'width': 14},
        {'key': 'wholesale_no_w', 'label': 'Giá sỉ KBH', 'width': 14},
        {'key': 'wholesale_w', 'label': 'Giá sỉ BH', 'width': 14},
        {'key': 'stock', 'label': 'Tồn kho', 'width': 10},
        {'key': 'supplier', 'label': 'NCC', 'width': 18},
        {'key': 'location', 'label': 'Vị trí', 'width': 14},
    ]

    rows = []
    for i, p in enumerate(products, 1):
        if p.is_combo:
            _, total_stock = _combo_stock_by_warehouse(p)
        else:
            total_stock = float(sum(s.quantity for s in p.stocks.all()))
        current_cost = _calc_on_hand_cost_price(p.id, total_stock, receipt_map)
        effective_cost = current_cost if current_cost > 0 else float(p.cost_price)
        rows.append({
            'stt': i,
            'code': p.code,
            'name': p.name,
            'barcode': p.barcode or '',
            'category': p.category.name if p.category else '',
            'unit': p.unit or '',
            'spec': p.specification or '',
            'import_price': float(p.import_price),
            'cost_price': effective_cost,
            'wholesale_no_w': float(p.wholesale_price_no_warranty),
            'wholesale_w': float(p.wholesale_price_warranty),
            'stock': total_stock,
            'supplier': p.supplier.name if p.supplier else '',
            'location': p.location.name if p.location else '',
        })

    return excel_response(
        title='DANH SÁCH SẢN PHẨM',
        subtitle=f'Xuất ngày {datetime.now().strftime("%d/%m/%Y %H:%M")} — {len(rows)} sản phẩm',
        columns=columns,
        rows=rows,
        filename=f'San_pham_{datetime.now().strftime("%Y%m%d")}',
        money_cols=['import_price', 'cost_price', 'wholesale_no_w', 'wholesale_w'],
    )


@login_required(login_url="/login/")
def export_goods_receipts_excel(request):
    """Xuất danh sách phiếu nhập kho ra Excel"""
    from core.excel_export import excel_response
    from datetime import datetime

    receipts = GoodsReceipt.objects.select_related('supplier', 'warehouse', 'created_by').prefetch_related('items__product').all()
    receipts = filter_by_store(receipts, request, field_name='warehouse__store')

    columns = [
        {'key': 'stt', 'label': 'STT', 'width': 6},
        {'key': 'code', 'label': 'Mã phiếu', 'width': 14},
        {'key': 'receipt_date', 'label': 'Ngày nhập', 'width': 12},
        {'key': 'supplier', 'label': 'Nhà cung cấp', 'width': 22},
        {'key': 'warehouse', 'label': 'Kho nhập', 'width': 16},
        {'key': 'total_quantity', 'label': 'Số lượng', 'width': 10},
        {'key': 'total_amount', 'label': 'Tổng tiền', 'width': 16},
        {'key': 'status', 'label': 'Trạng thái', 'width': 12},
        {'key': 'created_by', 'label': 'Người tạo', 'width': 14},
        {'key': 'note', 'label': 'Ghi chú', 'width': 24},
    ]

    rows = []
    total = 0
    total_quantity_all = 0
    for i, r in enumerate(receipts, 1):
        total_quantity, receipt_total = _calculate_goods_receipt_totals(r.items.all())
        total += float(receipt_total)
        total_quantity_all += float(total_quantity)
        rows.append({
            'stt': i,
            'code': r.code,
            'receipt_date': r.receipt_date,
            'supplier': r.supplier.name if r.supplier else '',
            'warehouse': r.warehouse.name if r.warehouse else '',
            'total_quantity': float(total_quantity),
            'total_amount': float(receipt_total),
            'status': r.get_status_display(),
            'created_by': r.created_by.get_full_name() or r.created_by.username if r.created_by else '',
            'note': r.note or '',
        })

    return excel_response(
        title='DANH SÁCH PHIẾU NHẬP KHO',
        subtitle=f'Xuất ngày {datetime.now().strftime("%d/%m/%Y %H:%M")} — {len(rows)} phiếu',
        columns=columns, rows=rows,
        filename=f'Nhap_kho_{datetime.now().strftime("%Y%m%d")}',
        money_cols=['total_amount'],
        total_row={'stt': '', 'code': 'TỔNG CỘNG', 'total_quantity': total_quantity_all, 'total_amount': total},
    )


@login_required(login_url="/login/")
def export_stock_transfers_excel(request):
    """Xuất danh sách chuyển kho ra Excel"""
    from core.excel_export import excel_response
    from datetime import datetime

    transfers = StockTransfer.objects.select_related('from_warehouse', 'to_warehouse', 'created_by').prefetch_related('items__product').all()
    transfers = filter_by_store(transfers, request, field_name='from_warehouse__store')

    columns = [
        {'key': 'stt', 'label': 'STT', 'width': 6},
        {'key': 'code', 'label': 'Mã phiếu', 'width': 14},
        {'key': 'transfer_date', 'label': 'Ngày chuyển', 'width': 12},
        {'key': 'from_warehouse', 'label': 'Kho xuất', 'width': 18},
        {'key': 'to_warehouse', 'label': 'Kho nhập', 'width': 18},
        {'key': 'items_count', 'label': 'Số SP', 'width': 8},
        {'key': 'total_qty', 'label': 'Tổng SL', 'width': 10},
        {'key': 'status', 'label': 'Trạng thái', 'width': 12},
        {'key': 'created_by', 'label': 'Người tạo', 'width': 14},
        {'key': 'note', 'label': 'Ghi chú', 'width': 24},
    ]

    rows = []
    for i, t in enumerate(transfers, 1):
        total_qty = sum(float(item.quantity) for item in t.items.all())
        rows.append({
            'stt': i,
            'code': t.code,
            'transfer_date': t.transfer_date,
            'from_warehouse': t.from_warehouse.name if t.from_warehouse else '',
            'to_warehouse': t.to_warehouse.name if t.to_warehouse else '',
            'items_count': t.items.count(),
            'total_qty': total_qty,
            'status': t.get_status_display(),
            'created_by': t.created_by.get_full_name() or t.created_by.username if t.created_by else '',
            'note': t.note or '',
        })

    return excel_response(
        title='DANH SÁCH PHIẾU CHUYỂN KHO',
        subtitle=f'Xuất ngày {datetime.now().strftime("%d/%m/%Y %H:%M")} — {len(rows)} phiếu',
        columns=columns, rows=rows,
        filename=f'Chuyen_kho_{datetime.now().strftime("%Y%m%d")}',
    )


@login_required(login_url="/login/")
def export_stock_checks_excel(request):
    """Xuất danh sách kiểm kho ra Excel"""
    from core.excel_export import excel_response
    from datetime import datetime

    checks = StockCheck.objects.select_related('warehouse', 'created_by').prefetch_related('items__product').all()
    checks = filter_by_store(checks, request, field_name='warehouse__store')

    columns = [
        {'key': 'stt', 'label': 'STT', 'width': 6},
        {'key': 'code', 'label': 'Mã phiếu', 'width': 14},
        {'key': 'check_date', 'label': 'Ngày kiểm', 'width': 12},
        {'key': 'warehouse', 'label': 'Kho', 'width': 18},
        {'key': 'items_count', 'label': 'Số SP', 'width': 8},
        {'key': 'total_diff', 'label': 'Chênh lệch SL', 'width': 14},
        {'key': 'status', 'label': 'Trạng thái', 'width': 12},
        {'key': 'created_by', 'label': 'Người tạo', 'width': 14},
        {'key': 'note', 'label': 'Ghi chú', 'width': 24},
    ]

    rows = []
    for i, c in enumerate(checks, 1):
        total_diff = sum(float(item.difference) for item in c.items.all())
        rows.append({
            'stt': i,
            'code': c.code,
            'check_date': c.check_date,
            'warehouse': c.warehouse.name if c.warehouse else '',
            'items_count': c.items.count(),
            'total_diff': total_diff,
            'status': c.get_status_display(),
            'created_by': c.created_by.get_full_name() or c.created_by.username if c.created_by else '',
            'note': c.note or '',
        })

    return excel_response(
        title='DANH SÁCH PHIẾU KIỂM KHO',
        subtitle=f'Xuất ngày {datetime.now().strftime("%d/%m/%Y %H:%M")} — {len(rows)} phiếu',
        columns=columns, rows=rows,
        filename=f'Kiem_kho_{datetime.now().strftime("%Y%m%d")}',
    )


@login_required(login_url="/login/")
def export_purchase_orders_excel(request):
    """Xuất danh sách đơn đặt hàng nhập ra Excel"""
    from core.excel_export import excel_response
    from datetime import datetime

    orders = PurchaseOrder.objects.select_related('supplier', 'warehouse', 'created_by').prefetch_related('items__product').all()
    orders = filter_by_store(orders, request, field_name='warehouse__store')

    columns = [
        {'key': 'stt', 'label': 'STT', 'width': 6},
        {'key': 'code', 'label': 'Mã đơn', 'width': 14},
        {'key': 'order_date', 'label': 'Ngày đặt', 'width': 12},
        {'key': 'expected_date', 'label': 'Ngày dự kiến', 'width': 12},
        {'key': 'supplier', 'label': 'Nhà cung cấp', 'width': 22},
        {'key': 'warehouse', 'label': 'Kho nhập', 'width': 16},
        {'key': 'items_count', 'label': 'Số SP', 'width': 8},
        {'key': 'total_amount', 'label': 'Tổng tiền', 'width': 16},
        {'key': 'status', 'label': 'Trạng thái', 'width': 12},
        {'key': 'created_by', 'label': 'Người tạo', 'width': 14},
        {'key': 'note', 'label': 'Ghi chú', 'width': 24},
    ]

    rows = []
    total = 0
    for i, o in enumerate(orders, 1):
        total += float(o.total_amount)
        rows.append({
            'stt': i,
            'code': o.code,
            'order_date': o.order_date,
            'expected_date': o.expected_date,
            'supplier': o.supplier.name if o.supplier else '',
            'warehouse': o.warehouse.name if o.warehouse else '',
            'items_count': o.items.count(),
            'total_amount': float(o.total_amount),
            'status': o.get_status_display(),
            'created_by': o.created_by.get_full_name() or o.created_by.username if o.created_by else '',
            'note': o.note or '',
        })

    return excel_response(
        title='DANH SÁCH ĐƠN ĐẶT HÀNG NHẬP',
        subtitle=f'Xuất ngày {datetime.now().strftime("%d/%m/%Y %H:%M")} — {len(rows)} đơn',
        columns=columns, rows=rows,
        filename=f'Dat_hang_nhap_{datetime.now().strftime("%Y%m%d")}',
        money_cols=['total_amount'],
        total_row={'stt': '', 'code': 'TỔNG CỘNG', 'total_amount': total},
    )


@login_required(login_url="/login/")
def export_suppliers_excel(request):
    """Xuất danh sách nhà cung cấp ra Excel"""
    from core.excel_export import excel_response
    from datetime import datetime

    suppliers = Supplier.objects.all()

    columns = [
        {'key': 'stt', 'label': 'STT', 'width': 6},
        {'key': 'code', 'label': 'Mã NCC', 'width': 12},
        {'key': 'name', 'label': 'Tên nhà cung cấp', 'width': 28},
        {'key': 'phone', 'label': 'SĐT', 'width': 14},
        {'key': 'email', 'label': 'Email', 'width': 22},
        {'key': 'tax_code', 'label': 'MST', 'width': 14},
        {'key': 'contact_person', 'label': 'Người liên hệ', 'width': 18},
        {'key': 'address', 'label': 'Địa chỉ', 'width': 30},
        {'key': 'note', 'label': 'Ghi chú', 'width': 24},
    ]

    rows = []
    for i, s in enumerate(suppliers, 1):
        rows.append({
            'stt': i,
            'code': s.code,
            'name': s.name,
            'phone': s.phone or '',
            'email': s.email or '',
            'tax_code': s.tax_code or '',
            'contact_person': s.contact_person or '',
            'address': s.address or '',
            'note': s.note or '',
        })

    return excel_response(
        title='DANH SÁCH NHÀ CUNG CẤP',
        subtitle=f'Xuất ngày {datetime.now().strftime("%d/%m/%Y %H:%M")} — {len(rows)} NCC',
        columns=columns, rows=rows,
        filename=f'NCC_{datetime.now().strftime("%Y%m%d")}',
    )
