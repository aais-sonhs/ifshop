import json
import logging
from decimal import Decimal
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import (
    Product, ProductCategory, ProductVariant, ProductStock, Supplier, Warehouse,
    GoodsReceipt, GoodsReceiptItem, PurchaseOrder, PurchaseOrderItem,
    StockCheck, StockCheckItem, StockTransfer, StockTransferItem, CostAdjustment,
    ComboItem
)

from core.store_utils import filter_by_store, get_user_store, brand_owner_required

logger = logging.getLogger(__name__)


# ============ PAGE VIEWS ============

@login_required(login_url="/login/")
@brand_owner_required
def product_tbl(request):
    context = {
        'active_tab': 'product_tbl',
        'categories': list(ProductCategory.objects.filter(is_active=True).values('id', 'name')),
        'suppliers': list(Supplier.objects.filter(is_active=True).values('id', 'name')),
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
    products = Product.objects.select_related('category', 'supplier').prefetch_related('variants', 'stocks', 'combo_items__product').all()
    products = filter_by_store(products, request)
    data = []
    for p in products:
        total_stock = float(sum(s.quantity for s in p.stocks.all()))
        variants = [{
            'id': v.id,
            'size_name': v.size_name,
            'sku': v.sku,
            'barcode': v.barcode or '',
            'cost_price': float(v.cost_price),
            'listed_price': float(v.listed_price),
            'selling_price': float(v.selling_price),
            'is_active': v.is_active,
        } for v in p.variants.all()]

        # Combo items
        combo_items = []
        if p.is_combo:
            combo_items = [{
                'product_id': ci.product_id,
                'product_code': ci.product.code,
                'product_name': ci.product.name,
                'is_service': ci.product.is_service,
                'quantity': float(ci.quantity),
                'selling_price': float(ci.product.selling_price),
            } for ci in p.combo_items.select_related('product').all()]

        stock_by_warehouse = [{
            'warehouse': s.warehouse.name if s.warehouse else '',
            'warehouse_id': s.warehouse_id,
            'quantity': float(s.quantity),
        } for s in p.stocks.select_related('warehouse').all() if float(s.quantity) != 0]

        data.append({
            'id': p.id, 'code': p.code, 'name': p.name, 'barcode': p.barcode or '',
            'category': p.category.name if p.category else '',
            'category_id': p.category_id,
            'unit': p.unit,
            'cost_price': float(p.cost_price), 'listed_price': float(p.listed_price),
            'selling_price': float(p.selling_price),
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
            'location': p.location or '',
        })
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_product(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        product_id = request.POST.get('id')
        if product_id:
            product = Product.objects.get(id=product_id)
            # Combo đã tạo → cho phép sửa (trước đây chặn hoàn toàn)
            # Giờ chỉ log cảnh báo để audit trail
            pass
        else:
            product = Product()
            product.created_by = request.user

        product.code = request.POST.get('code', '')
        product.name = request.POST.get('name', '')
        product.barcode = request.POST.get('barcode', '')
        product.unit = request.POST.get('unit', 'Cái')
        product.cost_price = request.POST.get('cost_price', 0) or 0
        product.listed_price = request.POST.get('listed_price', 0) or 0
        product.selling_price = request.POST.get('selling_price', 0) or 0
        product.min_stock = request.POST.get('min_stock', 0) or 0
        product.max_stock = request.POST.get('max_stock', 0) or 0
        product.description = request.POST.get('description', '')
        product.is_weight_based = request.POST.get('is_weight_based', '0') == '1'
        product.is_service = request.POST.get('is_service', '0') == '1'
        product.is_combo = request.POST.get('is_combo', '0') == '1'
        product.location = request.POST.get('location', '') or None

        cat_id = request.POST.get('category_id')
        product.category_id = cat_id if cat_id else None
        sup_id = request.POST.get('supplier_id')
        product.supplier_id = sup_id if sup_id else None

        if 'image' in request.FILES:
            product.image = request.FILES['image']

        product.save()

        # Save variants
        variants_json = request.POST.get('variants', '[]')
        import json as json_lib
        variants_data = json_lib.loads(variants_json)
        product.variants.all().delete()
        for v in variants_data:
            ProductVariant.objects.create(
                product=product,
                size_name=v.get('size_name', ''),
                sku=v.get('sku', ''),
                barcode=v.get('barcode', ''),
                cost_price=v.get('cost_price', 0) or 0,
                listed_price=v.get('listed_price', 0) or 0,
                selling_price=v.get('selling_price', 0) or 0,
            )

        # Save combo items
        if product.is_combo:
            combo_json = request.POST.get('combo_items', '[]')
            combo_data = json_lib.loads(combo_json)
            product.combo_items.all().delete()
            for ci in combo_data:
                pid = ci.get('product_id')
                qty = float(ci.get('quantity', 1))
                if pid and qty > 0:
                    ComboItem.objects.create(
                        combo=product,
                        product_id=pid,
                        quantity=qty,
                    )
            # Tự tính giá vốn combo = tổng giá vốn thành phần
            total_cost = sum(
                float(Product.objects.get(id=ci.get('product_id')).cost_price) * float(ci.get('quantity', 1))
                for ci in combo_data if ci.get('product_id')
            )
            product.cost_price = total_cost
            product.save(update_fields=['cost_price'])
        else:
            product.combo_items.all().delete()

        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_product(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        product = Product.objects.get(id=data.get('id'))

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
        gr_id = data.get('id')
        old_status = None
        if gr_id:
            gr = GoodsReceipt.objects.get(id=gr_id)
            old_status = gr.status
        else:
            gr = GoodsReceipt()
            gr.created_by = request.user
        gr.code = data.get('code', '')
        gr.supplier_id = data.get('supplier_id') or None
        gr.warehouse_id = data.get('warehouse_id') or None
        gr.receipt_date = data.get('receipt_date')
        new_status = int(data.get('status', 0))
        gr.status = new_status
        gr.note = data.get('note', '')

        # Save items
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
        # + Tính giá vốn trung bình gia quyền
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

                # Tính giá vốn TB gia quyền
                # Formula: (old_total_stock * old_cost + new_qty * new_price) / total_new_stock
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
                        product.save(update_fields=['cost_price'])
                except Product.DoesNotExist:
                    pass

        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
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

    from products.models import GoodsReceiptItem
    items = GoodsReceiptItem.objects.filter(
        product_id=product_id,
        goods_receipt__status=1  # Chỉ phiếu hoàn thành
    ).select_related('goods_receipt', 'goods_receipt__supplier', 'goods_receipt__warehouse', 'variant'
    ).order_by('-goods_receipt__receipt_date')

    data = [{
        'receipt_code': it.goods_receipt.code,
        'receipt_date': it.goods_receipt.receipt_date.strftime('%d/%m/%Y') if it.goods_receipt.receipt_date else '',
        'supplier': it.goods_receipt.supplier.name if it.goods_receipt.supplier else '',
        'warehouse': it.goods_receipt.warehouse.name if it.goods_receipt.warehouse else '',
        'variant': it.variant.size_name if it.variant else '',
        'quantity': float(it.quantity),
        'unit_price': float(it.unit_price),
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
            'total_entries': len(data),
            'total_quantity': total_qty,
            'total_amount': total_amount,
            'avg_unit_price': round(avg_price),
        }
    })
