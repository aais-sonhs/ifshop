import json
import logging
from datetime import date
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import transaction
from .models import Order, OrderItem, Quotation, QuotationItem, OrderReturn, OrderReturnItem, Packaging
from customers.models import Customer
from products.models import Product, Warehouse, ProductStock
from finance.models import Receipt, FinanceCategory, CashBook
from core.store_utils import filter_by_store, get_user_store, brand_owner_required

logger = logging.getLogger(__name__)


@login_required(login_url="/login/")
@brand_owner_required
def order_tbl(request):
    from core.store_utils import get_managed_store_ids
    store_ids = get_managed_store_ids(request.user)
    customers = list(Customer.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'code', 'name'))
    warehouses = list(Warehouse.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'name'))
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
    context = {
        'active_tab': 'order_tbl',
        'customers': customers,
        'warehouses': warehouses,
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
    customers = list(Customer.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'code', 'name'))
    brand_users = AuthUser.objects.filter(
        is_active=True,
        profile__store_id__in=store_ids
    ).distinct().order_by('last_name', 'first_name')
    system_users = [
        {'id': u.id, 'full_name': u.get_full_name() or u.username}
        for u in brand_users
    ]
    context = {'active_tab': 'quotation_tbl', 'customers': customers, 'system_users': system_users}
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
    data = []
    for p in products:
        # Tồn kho theo từng kho: {warehouse_id: quantity}
        stocks = {}
        total_stock = 0
        for s in p.stocks.all():
            stocks[str(s.warehouse_id)] = float(s.quantity)
            total_stock += float(s.quantity)

        # Variants
        variants = [{
            'id': v.id,
            'size_name': v.size_name,
            'sku': v.sku,
            'cost_price': float(v.cost_price),
            'listed_price': float(v.listed_price),
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
            'listed_price': float(p.listed_price),
            'cost_price': float(p.cost_price),
            'price': float(p.selling_price),
            'is_weight_based': p.is_weight_based,
            'is_service': p.is_service,
            'is_combo': p.is_combo,
            'combo_items': combo_items,
            'stocks': stocks,
            'total_stock': float(total_stock),
            'variants': variants,
        })
    return JsonResponse({'data': data})


# ============ API: CODE GENERATION ============

@login_required(login_url="/login/")
def api_next_order_code(request):
    """Sinh mã đơn hàng tiếp theo: DH-001, DH-002, ..."""
    import re
    prefix = 'DH-'
    # FIX: Dùng all_objects để tính cả record đã soft-delete, tránh trùng mã
    last_order = Order.all_objects.filter(code__startswith=prefix).order_by('-id').first()
    next_num = 1
    if last_order:
        match = re.search(r'DH-(\d+)', last_order.code)
        if match:
            next_num = int(match.group(1)) + 1
    # Đảm bảo không trùng (kể cả đã xóa mềm)
    while True:
        code = f'{prefix}{next_num:03d}'
        if not Order.all_objects.filter(code=code).exists():
            break
        next_num += 1
    return JsonResponse({'code': code})


@login_required(login_url="/login/")
def api_next_quotation_code(request):
    """Sinh mã báo giá tiếp theo: BG-001, BG-002, ..."""
    import re
    prefix = 'BG-'
    # FIX: Dùng all_objects để tính cả record đã soft-delete, tránh trùng mã
    last_q = Quotation.all_objects.filter(code__startswith=prefix).order_by('-id').first()
    next_num = 1
    if last_q:
        match = re.search(r'BG-(\d+)', last_q.code)
        if match:
            next_num = int(match.group(1)) + 1
    while True:
        code = f'{prefix}{next_num:03d}'
        if not Quotation.all_objects.filter(code=code).exists():
            break
        next_num += 1
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

        # Tự sinh mã khách hàng
        import re
        prefix = 'KH'
        last_cust = Customer.objects.filter(code__startswith=prefix).order_by('-id').first()
        next_num = 1
        if last_cust:
            match = re.search(r'KH(\d+)', last_cust.code)
            if match:
                next_num = int(match.group(1)) + 1
        while True:
            cust_code = f'{prefix}{next_num:03d}'
            if not Customer.objects.filter(code=cust_code).exists():
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
        # Auto-assign store
        from core.store_utils import get_user_store, get_managed_store_ids as _get_sids
        from system_management.models import Store as _Store
        user_store = get_user_store(request)
        if user_store:
            c.store = user_store
        else:
            _sids = _get_sids(request.user)
            if _sids:
                c.store = _Store.objects.filter(id__in=_sids).first()
        c.save()

        return JsonResponse({
            'status': 'ok',
            'message': f'Tạo khách hàng {c.name} thành công!',
            'customer': {
                'id': c.id,
                'code': c.code,
                'name': c.name,
            }
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: ORDER ============

@login_required(login_url="/login/")
def api_get_orders(request):
    orders = Order.objects.select_related('customer', 'warehouse').prefetch_related('receipts').all()
    orders = filter_by_store(orders, request)
    data = [{
        'id': o.id, 'code': o.code,
        'customer': o.customer.name if o.customer else '',
        'customer_id': o.customer_id,
        'warehouse': o.warehouse.name if o.warehouse else '',
        'warehouse_id': o.warehouse_id,
        'order_date': o.order_date.strftime('%Y-%m-%d') if o.order_date else '',
        'total_amount': float(o.total_amount),
        'discount_amount': float(o.discount_amount),
        'final_amount': float(o.final_amount),
        'paid_amount': float(o.paid_amount),
        'status': o.status, 'status_display': o.get_status_display(),
        'payment_status': o.payment_status,
        'payment_status_display': o.get_payment_status_display(),
        'has_receipt': o.receipts.filter(status=1).exists(),
        'receipt_count': o.receipts.filter(status=1).count(),
        'note': o.note or '',
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
                'id': o.id, 'code': o.code, 'customer_id': o.customer_id,
                'warehouse_id': o.warehouse_id,
                'order_date': o.order_date.strftime('%Y-%m-%d') if o.order_date else '',
                'discount_amount': float(o.discount_amount),
                'status': o.status, 'note': o.note or '',
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
                # Gán store từ profile user
                if not o.store_id:
                    from core.store_utils import get_user_store, get_managed_store_ids as _get_store_ids
                    from system_management.models import Store as _Store
                    user_store = get_user_store(request)
                    if user_store:
                        o.store = user_store
                    else:
                        _sids = _get_store_ids(request.user)
                        if _sids:
                            o.store = _Store.objects.filter(id__in=_sids).first()
            o.code = data.get('code', '')
            # Kiểm tra trùng mã (kể cả record đã soft-delete)
            dup = Order.all_objects.filter(code=o.code)
            if oid:
                dup = dup.exclude(id=oid)
            if dup.exists():
                return JsonResponse({'status': 'error', 'message': f'Mã đơn hàng "{o.code}" đã tồn tại. Vui lòng chọn mã khác.'})
            o.customer_id = data.get('customer_id') or None
            o.warehouse_id = data.get('warehouse_id') or None
            o.quotation_id = data.get('quotation_id') or None
            o.order_date = data.get('order_date')
            o.discount_amount = data.get('discount_amount', 0) or 0
            new_status = int(data.get('status', 0))
            new_approver_id_raw = data.get('approver_id') or None
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
            total = 0
            for it in items_data:
                qty = float(it.get('quantity', 0))
                price = float(it.get('unit_price', 0))
                disc = float(it.get('discount_percent', 0))
                line_total = qty * price * (1 - disc / 100)
                total += line_total

            o.total_amount = total
            o.final_amount = total - float(o.discount_amount)

            o.save()

            # Xử lý thanh toán — bắt buộc tạo phiếu thu nếu đã thanh toán
            is_paid = data.get('is_paid', True)
            if is_paid:
                # Tính tổng đã thu từ các phiếu thu Hoàn thành hiện có
                existing_paid = sum(
                    float(rec.amount)
                    for rec in Receipt.objects.filter(order=o, status=1)
                )
                remaining = float(o.final_amount) - existing_paid
                if remaining > 0:
                    # Tạo phiếu thu tự động
                    sale_cat = FinanceCategory.objects.filter(
                        type=1, name__icontains='bán hàng', is_active=True
                    ).first()
                    receipt_code = f'PT-{o.code}'
                    # Nếu đã có phiếu thu cùng code → thêm suffix
                    suffix = 1
                    base_code = receipt_code
                    while Receipt.objects.filter(code=receipt_code).exists():
                        suffix += 1
                        receipt_code = f'{base_code}-{suffix}'
                    pm = int(data.get('payment_method', 2))
                    # Tự động gán quỹ theo hình thức thanh toán
                    if pm == 2:
                        auto_cashbook = CashBook.objects.filter(
                            is_active=True, name__icontains='ngân hàng'
                        ).first()
                    else:
                        auto_cashbook = CashBook.objects.filter(
                            is_active=True, name__icontains='tiền mặt'
                        ).first()
                    Receipt.objects.create(
                        code=receipt_code,
                        category=sale_cat,
                        customer_id=o.customer_id,
                        order=o,
                        amount=remaining,
                        description=f'Thu tiền đơn hàng {o.code} (tự động)',
                        receipt_date=o.order_date or date.today(),
                        status=1,  # Hoàn thành
                        payment_method=pm,
                        cash_book=auto_cashbook,
                        created_by=request.user,
                    )
                # Cập nhật paid trên order
                total_paid = sum(
                    float(rec.amount)
                    for rec in Receipt.objects.filter(order=o, status=1)
                )
                o.paid_amount = total_paid
                if total_paid >= float(o.final_amount):
                    o.payment_status = 2
                elif total_paid > 0:
                    o.payment_status = 1
                else:
                    o.payment_status = 0
            else:
                # Chưa thanh toán — tính lại từ phiếu thu thực tế
                total_paid = sum(
                    float(rec.amount)
                    for rec in Receipt.objects.filter(order=o, status=1)
                )
                o.paid_amount = total_paid
                if total_paid >= float(o.final_amount):
                    o.payment_status = 2
                elif total_paid > 0:
                    o.payment_status = 1
                else:
                    o.payment_status = 0
            o.save(update_fields=['paid_amount', 'payment_status'])

            # Hoàn tác tồn kho nếu trước đó đã hoàn thành
            # FIX: Dùng Decimal thay vì float để tránh lỗi 'unsupported operand type'
            from decimal import Decimal
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
                                stock.quantity += Decimal(str(old_item.quantity)) * Decimal(str(ci.quantity))
                                stock.save()
                    elif not product.is_service:
                        stock, _ = ProductStock.objects.get_or_create(
                            product_id=old_item.product_id, warehouse_id=o.warehouse_id)
                        stock.quantity += Decimal(str(old_item.quantity))
                        stock.save()

            # Xóa items cũ và tạo mới
            o.items.all().delete()
            for it in items_data:
                qty = float(it.get('quantity', 0))
                price = float(it.get('unit_price', 0))
                disc = float(it.get('discount_percent', 0))
                line_total = qty * price * (1 - disc / 100)
                product = Product.objects.get(id=it['product_id'])
                variant_id = it.get('variant_id') or None
                cost = float(product.cost_price)
                listed = float(product.listed_price)
                if variant_id:
                    from products.models import ProductVariant
                    try:
                        variant = ProductVariant.objects.get(id=variant_id)
                        cost = float(variant.cost_price)
                        listed = float(variant.listed_price)
                    except ProductVariant.DoesNotExist:
                        variant_id = None
                OrderItem.objects.create(
                    order=o,
                    product=product,
                    variant_id=variant_id,
                    quantity=qty,
                    unit_price=price,
                    cost_price=cost,
                    discount_percent=disc,
                    total_price=line_total,
                    is_below_listed=(price < listed),
                )

            # Trừ tồn kho khi đơn hàng Hoàn thành (status=5)
            # FIX: Dùng Decimal thay vì float
            if new_status == 5 and o.warehouse_id:
                from products.models import ComboItem as _ComboItem2
                for it in items_data:
                    qty = Decimal(str(it.get('quantity', 0)))
                    pid = it.get('product_id')
                    product = Product.objects.get(id=pid)
                    if product.is_combo:
                        # Combo: trừ kho từng SP thành phần (bỏ qua dịch vụ)
                        for ci in _ComboItem2.objects.filter(combo_id=pid):
                            if not ci.product.is_service:
                                stock, _ = ProductStock.objects.get_or_create(
                                    product_id=ci.product_id, warehouse_id=o.warehouse_id)
                                stock.quantity -= qty * Decimal(str(ci.quantity))
                                stock.save()
                    elif not product.is_service:
                        stock, _ = ProductStock.objects.get_or_create(
                            product_id=pid, warehouse_id=o.warehouse_id)
                        stock.quantity -= qty
                        stock.save()
            # Cập nhật trạng thái báo giá → "Đã tạo đơn hàng"
            if o.quotation_id:
                Quotation.objects.filter(id=o.quotation_id).update(status=3)

        # Xây dựng message phản hồi
        msg = 'Lưu thành công'
        if o.approver_id and o.approval_status == 1:
            approver_name = o.approver.get_full_name() if o.approver else ''
            msg += f'. ⏳ Đơn hàng cần được {approver_name} duyệt trước khi hoàn thành.'
        return JsonResponse({'status': 'ok', 'message': msg})
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
        order.note = data.get('note', '')
        order.save(update_fields=['note'])
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
                                stock.quantity += _Dec(str(item.quantity)) * _Dec(str(ci.quantity))
                                stock.save()
                    elif not product.is_service:
                        stock, _ = ProductStock.objects.get_or_create(
                            product_id=item.product_id, warehouse_id=order.warehouse_id)
                        stock.quantity += _Dec(str(item.quantity))
                        stock.save()

            # Xử lý phiếu thu liên quan
            linked_receipts = Receipt.objects.filter(order=order)
            receipt_warning = ''
            if linked_receipts.exists():
                # Hủy phiếu thu tự động
                auto_receipts = linked_receipts.filter(description__icontains='tự động')
                manual_receipts = linked_receipts.exclude(description__icontains='tự động')

                for r in auto_receipts:
                    r.status = 2  # Hủy
                    r.note = f'[HỦY TỰ ĐỘNG] Đơn hàng {order.code} đã bị hủy. {r.note or ""}'.strip()
                    r.save()

                if manual_receipts.exists():
                    codes = ', '.join([r.code for r in manual_receipts])
                    receipt_warning = f' ⚠️ Có phiếu thu thủ công liên quan: {codes}. Vui lòng kiểm tra và xử lý.'

            # Cập nhật trạng thái → Hủy
            old_note = order.note or ''
            cancel_note = f"[HỦY] Lý do: {reason}" if reason else "[HỦY]"
            order.status = 6
            order.payment_status = 0
            order.paid_amount = 0
            order.note = f"{cancel_note}\n{old_note}".strip() if old_note else cancel_note
            order.save()

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
                # Tự động chuyển sang Hoàn thành
                old_status = order.status
                order.status = 5  # Hoàn thành

                # Trừ tồn kho (nếu chưa trừ trước đó)
                if old_status != 5 and order.warehouse_id:
                    from products.models import ComboItem as _ApprComboItem
                    from decimal import Decimal as _Dec
                    for item in order.items.all():
                        product = item.product
                        if product.is_combo:
                            for ci in _ApprComboItem.objects.filter(combo=product):
                                if not ci.product.is_service:
                                    stock, _ = ProductStock.objects.get_or_create(
                                        product_id=ci.product_id, warehouse_id=order.warehouse_id)
                                    stock.quantity -= _Dec(str(item.quantity)) * _Dec(str(ci.quantity))
                                    stock.save()
                        elif not product.is_service:
                            stock, _ = ProductStock.objects.get_or_create(
                                product_id=item.product_id, warehouse_id=order.warehouse_id)
                            stock.quantity -= _Dec(str(item.quantity))
                            stock.save()

                if note:
                    order.note = f"{order.note or ''}\n[DUYỆT] {note}".strip()
                order.save()

                approver_name = request.user.get_full_name() or request.user.username
                return JsonResponse({
                    'status': 'ok',
                    'message': f'✅ Đã duyệt đơn hàng {order.code}. Đơn hàng đã chuyển sang Hoàn thành.'
                })

            elif action == 'reject':
                order.approval_status = 3  # Từ chối
                order.approved_at = timezone.now()
                if note:
                    order.note = f"{order.note or ''}\n[TỪ CHỐI] {note}".strip()
                order.save()
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


# ============ API: QUOTATION ============

@login_required(login_url="/login/")
def api_get_quotations(request):
    quotes = Quotation.objects.select_related('customer').all()
    quotes = filter_by_store(quotes, request)
    data = [{
        'id': q.id, 'code': q.code,
        'customer': q.customer.name if q.customer else '',
        'customer_id': q.customer_id,
        'quotation_date': q.quotation_date.strftime('%Y-%m-%d') if q.quotation_date else '',
        'valid_until': q.valid_until.strftime('%Y-%m-%d') if q.valid_until else '',
        'total_amount': float(q.total_amount),
        'discount_amount': float(q.discount_amount),
        'final_amount': float(q.final_amount),
        'status': q.status, 'status_display': q.get_status_display(),
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
                'id': q.id, 'code': q.code, 'customer_id': q.customer_id,
                'quotation_date': q.quotation_date.strftime('%Y-%m-%d') if q.quotation_date else '',
                'valid_until': q.valid_until.strftime('%Y-%m-%d') if q.valid_until else '',
                'discount_amount': float(q.discount_amount),
                'status': q.status, 'note': q.note or '',
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
            if qid:
                q = Quotation.objects.get(id=qid)
                q.items.all().delete()
            else:
                q = Quotation()
                q.created_by = request.user
                # Gán store từ profile user
                from core.store_utils import get_user_store, get_managed_store_ids as _get_store_ids
                from system_management.models import Store as _Store
                user_store = get_user_store(request)
                if user_store:
                    q.store = user_store
                else:
                    # Brand owner có thể không có profile.store → lấy store đầu tiên của brand
                    _sids = _get_store_ids(request.user)
                    if _sids:
                        q.store = _Store.objects.filter(id__in=_sids).first()
            q.code = data.get('code', '')
            # Kiểm tra trùng mã (kể cả record đã soft-delete)
            dup = Quotation.all_objects.filter(code=q.code)
            if qid:
                dup = dup.exclude(id=qid)
            if dup.exists():
                return JsonResponse({'status': 'error', 'message': f'Mã báo giá "{q.code}" đã tồn tại. Vui lòng chọn mã khác.'})
            q.customer_id = data.get('customer_id') or None
            q.quotation_date = data.get('quotation_date')
            q.valid_until = data.get('valid_until') or None
            q.discount_amount = data.get('discount_amount', 0) or 0
            q.status = data.get('status', 0)
            q.note = data.get('note', '')
            q.salesperson = data.get('salesperson', '') or (request.user.get_full_name() or request.user.username)

            # Tính tổng từ items
            items_data = data.get('items', [])
            total = 0
            for it in items_data:
                qty = float(it.get('quantity', 0))
                price = float(it.get('unit_price', 0))
                disc = float(it.get('discount_percent', 0))
                line_total = qty * price * (1 - disc / 100)
                total += line_total

            q.total_amount = total
            q.final_amount = total - float(q.discount_amount)
            q.save()

            # Lưu items
            for it in items_data:
                qty = float(it.get('quantity', 0))
                price = float(it.get('unit_price', 0))
                disc = float(it.get('discount_percent', 0))
                line_total = qty * price * (1 - disc / 100)
                QuotationItem.objects.create(
                    quotation=q,
                    product_id=it['product_id'],
                    variant_id=it.get('variant_id') or None,
                    quantity=qty,
                    unit_price=price,
                    discount_percent=disc,
                    total_price=line_total,
                    note=it.get('note', ''),
                )

        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
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
                payment_status=2,  # Đã thanh toán
                total_amount=data.get('total_amount', 0),
                discount_amount=data.get('discount_amount', 0),
                final_amount=data.get('final_amount', 0),
                paid_amount=data.get('paid_amount', 0),
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
                    cost_price=float(product.cost_price or 0) * float(item_data.get('quantity', 1)),
                )
                oi.save()

                # Deduct stock
                if warehouse and not getattr(product, 'is_service', False):
                    if product.is_combo:
                        # Combo: trừ kho từng thành phần
                        from products.models import ComboItem
                        combo_items = ComboItem.objects.filter(combo=product).select_related('product')
                        for ci in combo_items:
                            qty_deduct = float(ci.quantity) * float(item_data.get('quantity', 1))
                            stock, _ = ProductStock.objects.get_or_create(
                                product=ci.product, warehouse=warehouse,
                                defaults={'quantity': 0}
                            )
                            stock.quantity = float(stock.quantity) - qty_deduct
                            stock.save()
                    else:
                        stock, _ = ProductStock.objects.get_or_create(
                            product=product, warehouse=warehouse,
                            defaults={'quantity': 0}
                        )
                        stock.quantity = float(stock.quantity) - float(item_data.get('quantity', 1))
                        stock.save()

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


