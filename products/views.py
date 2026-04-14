import json
import logging
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.utils import timezone
from .models import (
    Product, ProductCategory, ProductVariant, ProductStock, Supplier, Warehouse,
    GoodsReceipt, GoodsReceiptItem, PurchaseOrder, PurchaseOrderItem,
    StockCheck, StockCheckItem, StockTransfer, StockTransferItem, CostAdjustment,
    ComboItem, ProductLocation
)

from core.store_utils import filter_by_store, get_user_store, get_managed_store_ids, brand_owner_required

logger = logging.getLogger(__name__)


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
    context = {
        'active_tab': 'purchase_order_tbl',
        'suppliers': list(Supplier.objects.filter(is_active=True).values('id', 'name')),
        'warehouses': list(Warehouse.objects.filter(is_active=True).values('id', 'name')),
        'products': list(Product.objects.filter(is_active=True).values('id', 'code', 'name', 'cost_price', 'unit')),
    }
    return render(request, "products/purchase_order_list.html", context)


@login_required(login_url="/login/")
@brand_owner_required
def goods_receipt_tbl(request):
    context = {
        'active_tab': 'goods_receipt_tbl',
        'suppliers': list(Supplier.objects.filter(is_active=True).values('id', 'name')),
        'warehouses': list(Warehouse.objects.filter(is_active=True).values('id', 'name')),
        'products': list(Product.objects.filter(is_active=True).values('id', 'code', 'name', 'cost_price', 'unit')),
    }
    return render(request, "products/goods_receipt_list.html", context)


@login_required(login_url="/login/")
@brand_owner_required
def stock_check_tbl(request):
    context = {
        'active_tab': 'stock_check_tbl',
        'warehouses': list(Warehouse.objects.filter(is_active=True).values('id', 'name')),
        'products': list(Product.objects.filter(is_active=True).values('id', 'code', 'name', 'unit')),
    }
    return render(request, "products/stock_check_list.html", context)


@login_required(login_url="/login/")
@brand_owner_required
def stock_transfer_tbl(request):
    context = {
        'active_tab': 'stock_transfer_tbl',
        'warehouses': list(Warehouse.objects.filter(is_active=True).values('id', 'name')),
        'products': list(Product.objects.filter(is_active=True).values('id', 'code', 'name', 'unit')),
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
            wh = Warehouse.objects.get(id=wh_id)
        else:
            wh = Warehouse()
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
        Warehouse.objects.filter(id=data.get('id')).delete()
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
    receipts = GoodsReceipt.objects.select_related('supplier', 'warehouse', 'purchase_order').prefetch_related('items__product').all()
    receipts = filter_by_store(receipts, request, field_name='warehouse__store')
    data = []
    for r in receipts:
        items = [{
            'product_id': item.product_id,
            'variant_id': item.variant_id,
            'product_code': item.product.code if item.product else '',
            'product_name': item.product.name if item.product else '',
            'variant_name': item.variant.size_name if item.variant else '',
            'quantity': float(item.quantity),
            'unit_price': float(item.unit_price),
            'total_price': float(item.total_price),
        } for item in r.items.select_related('product', 'variant').all()]
        data.append({
            'id': r.id, 'code': r.code,
            'purchase_order': r.purchase_order.code if r.purchase_order else '',
            'supplier': r.supplier.name if r.supplier else '',
            'supplier_id': r.supplier_id,
            'warehouse': r.warehouse.name if r.warehouse else '',
            'warehouse_id': r.warehouse_id,
            'receipt_date': r.receipt_date.strftime('%Y-%m-%d') if r.receipt_date else '',
            'total_amount': float(r.total_amount),
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
            gr_id = data.get('id')
            old_status = None
            if gr_id:
                gr = GoodsReceipt.objects.select_for_update().get(id=gr_id)
                old_status = gr.status
            else:
                gr = GoodsReceipt()
                gr.created_by = request.user

            # Mã phiếu được giữ nguyên khi sửa; chỉ tự tăng khi tạo mới hoặc chưa có mã.
            code = (data.get('code', '') or '').strip()
            if not code:
                code = gr.code or _generate_next_goods_receipt_code()
            gr.code = code

            gr.supplier_id = data.get('supplier_id') or None
            gr.warehouse_id = data.get('warehouse_id') or None

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

            items_data = data.get('items', [])
            total = 0
            for item in items_data:
                tp = float(item.get('quantity', 0)) * float(item.get('unit_price', 0))
                total += tp
            gr.total_amount = total
            gr.save()

            # Hoàn tác tồn kho nếu trước đó đã hoàn thành
            if old_status == 1 and gr.warehouse_id:
                for old_item in gr.items.all():
                    stock, _ = ProductStock.objects.get_or_create(
                        product_id=old_item.product_id, warehouse_id=gr.warehouse_id)
                    stock.quantity -= old_item.quantity
                    stock.save()

            # Delete old items and create new ones
            gr.items.all().delete()
            for item in items_data:
                qty = float(item.get('quantity', 0))
                price = float(item.get('unit_price', 0))
                GoodsReceiptItem.objects.create(
                    goods_receipt=gr,
                    product_id=item.get('product_id'),
                    variant_id=item.get('variant_id') or None,
                    quantity=qty,
                    unit_price=price,
                    total_price=qty * price,
                )

            # Cộng tồn kho nếu status mới = Hoàn thành (1)
            # + Cập nhật giá vốn tham chiếu/fallback trong DB
            # + Cập nhật giá nhập (import_price) = giá mới nhất
            if new_status == 1 and gr.warehouse_id:
                for item in items_data:
                    product_id = item.get('product_id')
                    new_qty = Decimal(str(item.get('quantity', 0)))
                    new_price = Decimal(str(item.get('unit_price', 0)))

                    stock, _ = ProductStock.objects.get_or_create(
                        product_id=product_id,
                        warehouse_id=gr.warehouse_id,
                    )
                    old_stock_qty = stock.quantity  # Tồn trước khi nhập

                    # Cộng tồn
                    stock.quantity += new_qty
                    stock.save()

                    # Lưu giá vốn tham chiếu/fallback trong DB và cập nhật giá nhập mới nhất.
                    # Màn hình danh sách sản phẩm/export sẽ ưu tiên tính giá vốn của tồn hiện tại
                    # từ lịch sử các phiếu nhập còn lại.
                    try:
                        product = Product.objects.get(id=product_id)
                        total_old_stock = Decimal(str(sum(
                            float(s.quantity) for s in ProductStock.objects.filter(product_id=product_id)
                        ))) - new_qty  # Trừ lại vì đã cộng ở trên
                        if total_old_stock < 0:
                            total_old_stock = Decimal('0')
                        total_new_stock = total_old_stock + new_qty
                        if total_new_stock > 0:
                            old_cost = product.cost_price or Decimal('0')
                            weighted_avg = (total_old_stock * old_cost + new_qty * new_price) / total_new_stock
                            product.cost_price = round(weighted_avg)

                        # Cập nhật giá nhập = giá từ phiếu nhập mới nhất
                        product.import_price = new_price
                        product.save(update_fields=['cost_price', 'import_price'])
                    except Product.DoesNotExist:
                        pass

        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công', 'code': gr.code})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_goods_receipt(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        GoodsReceipt.objects.filter(id=data.get('id')).delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: STOCK TRANSFER ============

@login_required(login_url="/login/")
def api_get_stock_transfers(request):
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
        st_id = data.get('id')
        old_status = None
        if st_id:
            st = StockTransfer.objects.get(id=st_id)
            old_status = st.status
        else:
            st = StockTransfer()
            st.created_by = request.user
        st.code = data.get('code', '')
        st.from_warehouse_id = data.get('from_warehouse_id') or None
        st.to_warehouse_id = data.get('to_warehouse_id') or None
        st.transfer_date = data.get('transfer_date')
        new_status = int(data.get('status', 0))
        st.status = new_status
        st.note = data.get('note', '')
        st.save()

        # Hoàn tác tồn kho nếu trước đó đã hoàn thành
        if old_status == 2 and st.from_warehouse_id and st.to_warehouse_id:
            for old_item in st.items.all():
                qty = old_item.quantity
                pid = old_item.product_id
                from_stock, _ = ProductStock.objects.get_or_create(
                    product_id=pid, warehouse_id=st.from_warehouse_id)
                from_stock.quantity += qty  # Hoàn lại kho xuất
                from_stock.save()
                to_stock, _ = ProductStock.objects.get_or_create(
                    product_id=pid, warehouse_id=st.to_warehouse_id)
                to_stock.quantity -= qty  # Hoàn lại kho nhập
                to_stock.save()

        # Save items
        items_data = data.get('items', [])
        st.items.all().delete()
        for item in items_data:
            StockTransferItem.objects.create(
                transfer=st,
                product_id=item.get('product_id'),
                variant_id=item.get('variant_id') or None,
                quantity=float(item.get('quantity', 0)),
            )

        # Cập nhật tồn kho nếu status mới = Hoàn thành (2)
        if new_status == 2 and st.from_warehouse_id and st.to_warehouse_id:
            for item in items_data:
                qty = float(item.get('quantity', 0))
                pid = item.get('product_id')
                from_stock, _ = ProductStock.objects.get_or_create(
                    product_id=pid, warehouse_id=st.from_warehouse_id)
                from_stock.quantity -= qty
                from_stock.save()
                to_stock, _ = ProductStock.objects.get_or_create(
                    product_id=pid, warehouse_id=st.to_warehouse_id)
                to_stock.quantity += qty
                to_stock.save()

        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_stock_transfer(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        StockTransfer.objects.filter(id=data.get('id')).delete()
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
        sc_id = data.get('id')
        if sc_id:
            sc = StockCheck.objects.get(id=sc_id)
        else:
            sc = StockCheck()
            sc.created_by = request.user
        sc.code = data.get('code', '')
        sc.warehouse_id = data.get('warehouse_id') or None
        sc.check_date = data.get('check_date')
        sc.status = data.get('status', 0)
        sc.note = data.get('note', '')
        sc.save()

        # Save items
        items_data = data.get('items', [])
        sc.items.all().delete()
        for item in items_data:
            product_id = item.get('product_id')
            actual_qty = float(item.get('actual_quantity', 0))
            # Get system quantity from ProductStock
            sys_qty = 0
            if sc.warehouse_id and product_id:
                try:
                    ps = ProductStock.objects.get(product_id=product_id, warehouse_id=sc.warehouse_id)
                    sys_qty = ps.quantity
                except ProductStock.DoesNotExist:
                    sys_qty = 0
            StockCheckItem.objects.create(
                stock_check=sc,
                product_id=product_id,
                variant_id=item.get('variant_id') or None,
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
        StockCheck.objects.filter(id=data.get('id')).delete()
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
            po = PurchaseOrder.objects.get(id=po_id)
        else:
            po = PurchaseOrder()
            po.created_by = request.user
        po.code = data.get('code', '')
        po.supplier_id = data.get('supplier_id') or None
        po.warehouse_id = data.get('warehouse_id') or None
        po.order_date = data.get('order_date')
        po.expected_date = data.get('expected_date') or None
        po.status = data.get('status', 0)
        po.note = data.get('note', '')

        # Calculate total from items
        items_data = data.get('items', [])
        total = 0
        for item in items_data:
            tp = float(item.get('quantity', 0)) * float(item.get('unit_price', 0))
            total += tp
        po.total_amount = total
        po.save()

        # Delete old items and create new ones
        po.items.all().delete()
        for item in items_data:
            qty = float(item.get('quantity', 0))
            price = float(item.get('unit_price', 0))
            PurchaseOrderItem.objects.create(
                purchase_order=po,
                product_id=item.get('product_id'),
                variant_id=item.get('variant_id') or None,
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
        PurchaseOrder.objects.filter(id=data.get('id')).delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: COST ADJUSTMENT ============

@login_required(login_url="/login/")
def api_get_cost_adjustments(request):
    items = CostAdjustment.objects.select_related('product', 'adjusted_by').all()
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
    data = [{'id': l.id, 'name': l.name, 'is_active': l.is_active} for l in locs]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_location(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
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
        {'key': 'items_count', 'label': 'Số SP', 'width': 8},
        {'key': 'total_amount', 'label': 'Tổng tiền', 'width': 16},
        {'key': 'status', 'label': 'Trạng thái', 'width': 12},
        {'key': 'created_by', 'label': 'Người tạo', 'width': 14},
        {'key': 'note', 'label': 'Ghi chú', 'width': 24},
    ]

    rows = []
    total = 0
    for i, r in enumerate(receipts, 1):
        total += float(r.total_amount)
        rows.append({
            'stt': i,
            'code': r.code,
            'receipt_date': r.receipt_date,
            'supplier': r.supplier.name if r.supplier else '',
            'warehouse': r.warehouse.name if r.warehouse else '',
            'items_count': r.items.count(),
            'total_amount': float(r.total_amount),
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
        total_row={'stt': '', 'code': 'TỔNG CỘNG', 'total_amount': total},
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
