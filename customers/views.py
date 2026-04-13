import json
import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Customer, CustomerGroup
from orders.models import Order
from core.store_utils import filter_by_store, get_user_store, brand_owner_required

logger = logging.getLogger(__name__)


@login_required(login_url="/login/")
@brand_owner_required
def customer_tbl(request):
    groups = list(CustomerGroup.objects.filter(is_active=True).values('id', 'name'))
    context = {'active_tab': 'customer_tbl', 'groups': groups}
    return render(request, "customers/customer_list.html", context)


@login_required(login_url="/login/")
def customer_group_tbl(request):
    context = {'active_tab': 'customer_group_tbl'}
    return render(request, "customers/customer_group_list.html", context)


# ============ API ============

@login_required(login_url="/login/")
def api_get_customers(request):
    customers = Customer.objects.select_related('group').all()
    customers = filter_by_store(customers, request)
    data = [{
        'id': c.id, 'code': c.code, 'name': c.name,
        'avatar_url': c.avatar.url if c.avatar else '',
        'customer_type': c.customer_type,
        'customer_type_display': c.get_customer_type_display(),
        'phone': c.phone or '', 'email': c.email or '',
        'address': c.address or '',
        'id_number': c.id_number or '',
        'company': c.company or '',
        'tax_code': c.tax_code or '',
        'company_address': c.company_address or '',
        'owner_tax_code': c.owner_tax_code or '',
        'group': c.group.name if c.group else '', 'group_id': c.group_id,
        'total_purchased': float(c.total_purchased),
        'total_debt': float(c.total_debt),
        'points': c.points, 'membership_level': c.membership_level,
        'membership_display': c.get_membership_level_display(),
        'gender': c.gender, 'gender_display': c.get_gender_display(),
        'date_of_birth': c.date_of_birth.strftime('%d/%m/%Y') if c.date_of_birth else '',
        'note': c.note or '', 'is_active': c.is_active,
    } for c in customers]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_customer(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        cid = data.get('id')
        if cid:
            c = Customer.objects.get(id=cid)
        else:
            c = Customer()
            c.created_by = request.user
            # Auto-assign store (with brand owner fallback)
            store = get_user_store(request)
            if store:
                c.store = store
            else:
                from core.store_utils import get_managed_store_ids
                from system_management.models import Store
                sids = get_managed_store_ids(request.user)
                if sids:
                    c.store = Store.objects.filter(id__in=sids).first()
        c.code = data.get('code', '')
        c.name = data.get('name', '')
        c.customer_type = data.get('customer_type', 1)
        c.phone = data.get('phone', '')
        c.email = data.get('email', '')
        c.address = data.get('address', '')
        c.id_number = data.get('id_number', '')
        c.company = data.get('company', '')
        c.tax_code = data.get('tax_code', '')
        c.company_address = data.get('company_address', '')
        c.owner_tax_code = data.get('owner_tax_code', '')
        c.note = data.get('note', '')
        c.group_id = data.get('group_id') or None
        c.is_active = data.get('is_active', True)
        c.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_customer(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        cid = data.get('id')
        from core.store_utils import get_managed_store_ids
        store_ids = get_managed_store_ids(request.user)
        c = Customer.objects.filter(id=cid, store_id__in=store_ids).first()
        if not c:
            return JsonResponse({'status': 'error', 'message': 'Không tìm thấy hoặc không có quyền xóa khách hàng này'})
        c.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_upload_customer_avatar(request):
    """Upload ảnh đại diện khách hàng — auto convert sang JPG cho OpenCV"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        cid = request.POST.get('id')
        if not cid:
            return JsonResponse({'status': 'error', 'message': 'Missing customer id'})
        c = Customer.objects.get(id=cid)
        if 'avatar' in request.FILES:
            import os
            from PIL import Image
            from io import BytesIO
            from django.core.files.base import ContentFile

            # Xóa ảnh cũ nếu có
            if c.avatar:
                try:
                    if os.path.isfile(c.avatar.path):
                        os.remove(c.avatar.path)
                except Exception:
                    pass

            # Convert sang JPG
            uploaded = request.FILES['avatar']
            img = Image.open(uploaded)
            if img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=90)
            buffer.seek(0)

            filename = f"customer_{c.code}.jpg"
            c.avatar.save(filename, ContentFile(buffer.read()), save=True)

            return JsonResponse({'status': 'ok', 'message': 'Upload thành công', 'avatar_url': c.avatar.url})
        return JsonResponse({'status': 'error', 'message': 'Không có file ảnh'})
    except Customer.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy khách hàng'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_get_customer_groups(request):
    groups = CustomerGroup.objects.all()
    data = [{
        'id': g.id, 'name': g.name, 'description': g.description or '',
        'discount_percent': float(g.discount_percent),
        'customer_count': g.customers.count(),
        'is_active': g.is_active,
    } for g in groups]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_customer_group(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        gid = data.get('id')
        if gid:
            g = CustomerGroup.objects.get(id=gid)
        else:
            g = CustomerGroup()
        g.name = data.get('name', '')
        g.description = data.get('description', '')
        g.discount_percent = data.get('discount_percent', 0) or 0
        g.is_active = data.get('is_active', True)
        g.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_customer_group(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        CustomerGroup.objects.filter(id=data.get('id')).delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_customer_orders(request):
    """Lịch sử mua hàng của khách hàng"""
    cid = request.GET.get('customer_id')
    if not cid:
        return JsonResponse({'status': 'error', 'message': 'Missing customer_id'})
    try:
        from core.store_utils import get_managed_store_ids
        store_ids = get_managed_store_ids(request.user)
        customer = Customer.objects.filter(id=cid, store_id__in=store_ids).first()
        if not customer:
            return JsonResponse({'status': 'error', 'message': 'Không tìm thấy khách hàng'})
        orders = Order.objects.filter(customer=customer).select_related('warehouse').order_by('-order_date')
        data = []
        total_amount = 0
        total_debt = 0
        for o in orders:
            debt = float(o.final_amount) - float(o.paid_amount)
            items = [{
                'product_name': it.product.name,
                'quantity': float(it.quantity),
                'unit_price': float(it.unit_price),
                'discount_percent': float(it.discount_percent),
                'total_price': float(it.total_price),
            } for it in o.items.select_related('product').all()]

            data.append({
                'id': o.id, 'code': o.code,
                'order_date': o.order_date.strftime('%d/%m/%Y') if o.order_date else '',
                'warehouse': o.warehouse.name if o.warehouse else '',
                'total_amount': float(o.total_amount),
                'discount_amount': float(o.discount_amount),
                'final_amount': float(o.final_amount),
                'paid_amount': float(o.paid_amount),
                'debt': debt if debt > 0 else 0,
                'status': o.status,
                'status_display': o.get_status_display(),
                'payment_status': o.payment_status,
                'payment_status_display': o.get_payment_status_display(),
                'note': o.note or '',
                'items': items,
            })
            if o.status != 6:  # Không tính đơn hủy
                total_amount += float(o.final_amount)
                if debt > 0:
                    total_debt += debt

        return JsonResponse({
            'status': 'ok',
            'customer': {'id': customer.id, 'code': customer.code, 'name': customer.name,
                         'phone': customer.phone or '', 'company': customer.company or ''},
            'orders': data,
            'summary': {
                'total_orders': len([d for d in data if d['status'] != 6]),
                'total_cancelled': len([d for d in data if d['status'] == 6]),
                'total_amount': total_amount,
                'total_debt': total_debt,
            }
        })
    except Customer.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy khách hàng'})


# ============ CAFE TABLE ============

@login_required(login_url="/login/")
def cafe_table_tbl(request):
    context = {'active_tab': 'cafe_table_tbl'}
    return render(request, "customers/cafe_table_map.html", context)


@login_required(login_url="/login/")
def api_get_cafe_tables(request):
    from .models import CafeTable
    from core.store_utils import filter_by_store
    tables = CafeTable.objects.select_related('current_order').filter(is_active=True)
    tables = filter_by_store(tables, request)
    data = [{
        'id': t.id, 'number': t.number, 'name': t.name or f'Bàn {t.number}',
        'area': t.area, 'area_display': t.get_area_display(),
        'capacity': t.capacity, 'status': t.status,
        'status_display': t.get_status_display(),
        'current_order_id': t.current_order_id,
        'current_order_code': t.current_order.code if t.current_order else '',
        'note': t.note or '', 'sort_order': t.sort_order,
    } for t in tables]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_cafe_table(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        from .models import CafeTable
        data = json.loads(request.body)
        tid = data.get('id')
        if tid:
            t = CafeTable.objects.get(id=tid)
        else:
            t = CafeTable()
            store = get_user_store(request)
            if store:
                t.store = store
        t.number = data.get('number', '')
        t.name = data.get('name', '')
        t.area = data.get('area', 'indoor')
        t.capacity = data.get('capacity', 4)
        t.note = data.get('note', '')
        t.sort_order = data.get('sort_order', 0)
        t.is_active = data.get('is_active', True)
        t.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_cafe_table(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        from .models import CafeTable
        data = json.loads(request.body)
        CafeTable.objects.filter(id=data.get('id')).delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_update_table_status(request):
    """Cập nhật trạng thái bàn"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        from .models import CafeTable
        data = json.loads(request.body)
        tid = data.get('id')
        t = CafeTable.objects.get(id=tid)
        new_status = int(data.get('status', 0))
        t.status = new_status
        if new_status == 0:  # Trống
            t.current_order = None
        elif 'order_id' in data:
            t.current_order_id = data['order_id']
        t.save()
        return JsonResponse({'status': 'ok', 'message': 'Cập nhật thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ LOYALTY POINTS ============

@login_required(login_url="/login/")
def api_get_point_history(request):
    """Lịch sử tích/đổi điểm của KH"""
    from .models import PointTransaction
    cid = request.GET.get('customer_id')
    if not cid:
        return JsonResponse({'status': 'error', 'message': 'Missing customer_id'})
    txns = PointTransaction.objects.filter(customer_id=cid).select_related('order').order_by('-created_at')[:100]
    data = [{
        'id': t.id,
        'type': t.transaction_type,
        'type_display': t.get_transaction_type_display(),
        'points': t.points,
        'balance_after': t.balance_after,
        'description': t.description or '',
        'order_code': t.order.code if t.order else '',
        'created_at': t.created_at.strftime('%d/%m/%Y %H:%M'),
    } for t in txns]
    customer = Customer.objects.get(id=cid)
    return JsonResponse({
        'status': 'ok', 'data': data,
        'customer_points': customer.points,
        'membership_level': customer.membership_level,
        'membership_display': customer.get_membership_level_display(),
    })


@login_required(login_url="/login/")
def api_adjust_points(request):
    """Cộng/trừ điểm thủ công"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        from .models import PointTransaction
        data = json.loads(request.body)
        cid = data.get('customer_id')
        points = int(data.get('points', 0))
        txn_type = int(data.get('type', 3))  # 3 = điều chỉnh
        desc = data.get('description', 'Điều chỉnh thủ công')
        customer = Customer.objects.get(id=cid)
        if txn_type == 2 and points > customer.points:
            return JsonResponse({'status': 'error', 'message': f'Khách chỉ có {customer.points} điểm'})
        if txn_type == 1 or txn_type == 3:
            customer.points += points
        else:
            customer.points -= points
        customer.save(update_fields=['points'])

        # Auto upgrade membership
        _auto_upgrade_membership(customer)

        PointTransaction.objects.create(
            customer=customer,
            transaction_type=txn_type,
            points=points,
            balance_after=customer.points,
            description=desc,
            created_by=request.user,
        )
        return JsonResponse({'status': 'ok', 'message': f'Cập nhật điểm thành công. Hiện có {customer.points} điểm'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


def _auto_upgrade_membership(customer):
    """Tự động nâng hạng thành viên dựa trên tổng mua hàng"""
    total = float(customer.total_purchased)
    if total >= 100_000_000:
        customer.membership_level = 4  # Kim cương
    elif total >= 50_000_000:
        customer.membership_level = 3  # Bạch kim
    elif total >= 20_000_000:
        customer.membership_level = 2  # Vàng
    elif total >= 5_000_000:
        customer.membership_level = 1  # Bạc
    else:
        customer.membership_level = 0
    customer.save(update_fields=['membership_level'])


def add_loyalty_points_for_order(order):
    """Tích điểm cho KH khi đơn hoàn thành — gọi từ order views"""
    from .models import PointTransaction
    from system_management.models import BusinessConfig
    try:
        config = BusinessConfig.get_config()
        if not config.opt_loyalty_points:
            return
        if not order.customer:
            return
        rate = config.opt_loyalty_rate or 10000
        points = int(float(order.final_amount) / rate)
        if points <= 0:
            return
        customer = order.customer
        customer.points += points
        customer.total_purchased = float(customer.total_purchased) + float(order.final_amount)
        customer.save(update_fields=['points', 'total_purchased'])
        _auto_upgrade_membership(customer)

        PointTransaction.objects.create(
            customer=customer, order=order,
            transaction_type=1, points=points,
            balance_after=customer.points,
            description=f'Tích điểm đơn {order.code} ({order.final_amount:,.0f}đ)',
            created_by=order.created_by,
        )
    except Exception as e:
        logger.error(f'Lỗi tích điểm: {e}')


# ============ POS ============

@login_required(login_url="/login/")
def pos_page(request):
    context = {'active_tab': 'pos_page'}
    return render(request, "customers/pos.html", context)


# ============ DASHBOARD ============

@login_required(login_url="/login/")
def dashboard_page(request):
    context = {'active_tab': 'dashboard'}
    return render(request, "customers/dashboard.html", context)


@login_required(login_url="/login/")
def api_dashboard_data(request):
    """API lấy dữ liệu dashboard"""
    from datetime import datetime, timedelta
    from django.db.models import Sum, Count, Q
    from core.store_utils import get_managed_store_ids
    from products.models import ProductStock

    store_ids = get_managed_store_ids(request.user)
    today = datetime.now().date()
    first_day = today.replace(day=1)

    # Doanh thu + đơn tháng này
    month_orders = Order.objects.filter(
        store_id__in=store_ids, order_date__gte=first_day, order_date__lte=today
    ).exclude(status=6)
    stats = month_orders.aggregate(
        total_revenue=Sum('final_amount'),
        total_orders=Count('id'),
        total_paid=Sum('paid_amount'),
    )
    revenue = float(stats['total_revenue'] or 0)
    paid = float(stats['total_paid'] or 0)
    orders_count = stats['total_orders'] or 0

    # Tính lợi nhuận (doanh thu - giá vốn)
    from orders.models import OrderItem
    cost = OrderItem.objects.filter(
        order__store_id__in=store_ids,
        order__order_date__gte=first_day,
        order__order_date__lte=today,
    ).exclude(order__status=6).aggregate(
        total=Sum('cost_price')
    )['total'] or 0
    profit = revenue - float(cost)

    # KH mới tháng này
    new_customers = Customer.objects.filter(
        store_id__in=store_ids,
        created_at__date__gte=first_day,
    ).count()

    # Doanh thu 7 ngày
    chart_data = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_rev = Order.objects.filter(
            store_id__in=store_ids, order_date=day
        ).exclude(status=6).aggregate(r=Sum('final_amount'))['r'] or 0
        chart_data.append({
            'date': day.strftime('%d/%m'),
            'revenue': float(day_rev)
        })

    # Top SP bán chạy
    top_products = OrderItem.objects.filter(
        order__store_id__in=store_ids,
        order__order_date__gte=first_day,
    ).exclude(order__status=6).values('product__name').annotate(
        total_qty=Sum('quantity'),
        total_amount=Sum('total_price')
    ).order_by('-total_amount')[:10]

    # Top KH
    top_customers = Order.objects.filter(
        store_id__in=store_ids, order_date__gte=first_day,
        customer__isnull=False,
    ).exclude(status=6).values('customer__name', 'customer__phone').annotate(
        total=Sum('final_amount'), count=Count('id')
    ).order_by('-total')[:10]

    # Cảnh báo tồn kho thấp
    low_stock = ProductStock.objects.filter(
        warehouse__store_id__in=store_ids,
        quantity__lte=10,
        product__is_active=True,
    ).select_related('product', 'warehouse').values(
        'product__name', 'product__code', 'warehouse__name', 'quantity'
    )[:20]

    return JsonResponse({
        'status': 'ok',
        'kpi': {
            'revenue': revenue,
            'orders': orders_count,
            'profit': profit,
            'paid': paid,
            'debt': revenue - paid,
            'new_customers': new_customers,
        },
        'chart': chart_data,
        'top_products': [{'name': p['product__name'], 'qty': float(p['total_qty']), 'amount': float(p['total_amount'])} for p in top_products],
        'top_customers': [{'name': c['customer__name'], 'phone': c['customer__phone'] or '', 'total': float(c['total']), 'count': c['count']} for c in top_customers],
        'low_stock': [{'product': s['product__name'], 'code': s['product__code'], 'warehouse': s['warehouse__name'], 'qty': float(s['quantity'])} for s in low_stock],
    })

