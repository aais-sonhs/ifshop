import logging
import json
from datetime import datetime, timedelta
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Sum, Count, Q, F
from orders.models import Order, OrderItem, OrderReturn
from products.models import PurchaseOrder
from core.store_utils import filter_by_store, brand_owner_required, report_permission_required

logger = logging.getLogger(__name__)


@login_required(login_url="/login/")
@brand_owner_required
@report_permission_required
def report_sales(request):
    """Báo cáo bán hàng"""
    context = {'active_tab': 'report_sales'}
    return render(request, "reports/report_sales.html", context)


@login_required(login_url="/login/")
def api_report_sales(request):
    """API báo cáo bán hàng — hỗ trợ filter theo store + breakdown nhiều CH"""
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    store_id = request.GET.get('store_id')  # Filter cụ thể 1 CH

    # Mặc định: tháng hiện tại
    today = datetime.now().date()
    if not from_date:
        from_date = today.replace(day=1).strftime('%Y-%m-%d')
    if not to_date:
        to_date = today.strftime('%Y-%m-%d')

    # Base queryset
    orders = Order.objects.filter(
        order_date__gte=from_date, order_date__lte=to_date
    ).exclude(status=6)
    orders = filter_by_store(orders, request)

    # Filter theo store cụ thể
    if store_id:
        orders = orders.filter(store_id=store_id)

    total_orders = orders.count()
    total_revenue = float(orders.aggregate(s=Sum('final_amount'))['s'] or 0)
    total_paid = float(orders.aggregate(s=Sum('paid_amount'))['s'] or 0)
    total_debt = total_revenue - total_paid

    # Giá vốn
    cost_items = OrderItem.objects.filter(
        order__in=orders
    ).aggregate(
        total_cost=Sum(F('cost_price') * F('quantity'))
    )
    total_cost = float(cost_items['total_cost'] or 0)
    total_profit = total_revenue - total_cost

    # Trả hàng
    returns = OrderReturn.objects.filter(
        return_date__gte=from_date, return_date__lte=to_date
    ).exclude(status=3)
    total_returns = float(returns.aggregate(s=Sum('total_refund'))['s'] or 0)
    returns_count = returns.count()

    # Nhập hàng
    purchases = PurchaseOrder.objects.filter(
        order_date__gte=from_date, order_date__lte=to_date
    ).exclude(status=4)
    total_purchases = float(purchases.aggregate(s=Sum('total_amount'))['s'] or 0)

    # Doanh thu theo ngày
    from django.db.models.functions import TruncDate
    daily = orders.annotate(
        day=TruncDate('order_date')
    ).values('day').annotate(
        count=Count('id'),
        revenue=Sum('final_amount'),
        paid=Sum('paid_amount'),
    ).order_by('day')

    daily_data = []
    for d in daily:
        day_cost_items = OrderItem.objects.filter(
            order__order_date=d['day'], order__status__in=[0,1,2,3,4,5]
        ).exclude(order__status=6)
        if store_id:
            day_cost_items = day_cost_items.filter(order__store_id=store_id)
        day_cost_items = day_cost_items.aggregate(c=Sum(F('cost_price') * F('quantity')))
        day_cost = float(day_cost_items['c'] or 0)
        day_revenue = float(d['revenue'] or 0)

        day_returns = OrderReturn.objects.filter(
            return_date=d['day']
        ).exclude(status=3).aggregate(s=Sum('total_refund'))
        day_ret = float(day_returns['s'] or 0)

        daily_data.append({
            'date': d['day'].strftime('%d/%m/%Y'),
            'count': d['count'],
            'revenue': day_revenue,
            'cost': day_cost,
            'profit': day_revenue - day_cost,
            'returns': day_ret,
        })

    # Top 5 sản phẩm bán chạy
    from products.models import Product
    top_products = OrderItem.objects.filter(
        order__in=orders
    ).values('product__name').annotate(
        total_qty=Sum('quantity'),
        total_amount=Sum('total_price'),
    ).order_by('-total_qty')[:5]

    # Top 5 khách hàng
    top_customers = orders.values(
        'customer__name'
    ).annotate(
        order_count=Count('id'),
        total_amount=Sum('final_amount'),
    ).order_by('-total_amount')[:5]

    # === STORE BREAKDOWN (nếu nhiều CH) ===
    from core.store_utils import get_managed_store_ids
    from system_management.models import Store
    managed_ids = get_managed_store_ids(request.user)
    managed_stores = Store.objects.filter(id__in=managed_ids).select_related('brand')
    has_multiple = managed_stores.count() > 1

    stores_list = [{'id': s.id, 'name': s.name, 'brand': s.brand.name if s.brand else ''} for s in managed_stores]

    store_breakdown = []
    if has_multiple and not store_id:
        # Tính cho từng CH
        all_orders_base = Order.objects.filter(
            order_date__gte=from_date, order_date__lte=to_date
        ).exclude(status=6)
        all_orders_base = filter_by_store(all_orders_base, request)

        for st in managed_stores:
            st_orders = all_orders_base.filter(store=st)
            st_count = st_orders.count()
            st_revenue = float(st_orders.aggregate(s=Sum('final_amount'))['s'] or 0)
            st_paid = float(st_orders.aggregate(s=Sum('paid_amount'))['s'] or 0)
            st_cost_data = OrderItem.objects.filter(order__in=st_orders).aggregate(
                c=Sum(F('cost_price') * F('quantity'))
            )
            st_cost = float(st_cost_data['c'] or 0)
            store_breakdown.append({
                'store_id': st.id,
                'store_name': st.name,
                'brand_name': st.brand.name if st.brand else '',
                'orders': st_count,
                'revenue': st_revenue,
                'cost': st_cost,
                'profit': st_revenue - st_cost,
                'debt': st_revenue - st_paid,
                'paid': st_paid,
            })

    return JsonResponse({
        'status': 'ok',
        'has_multiple_stores': has_multiple,
        'stores': stores_list,
        'summary': {
            'total_orders': total_orders,
            'total_revenue': total_revenue,
            'total_cost': total_cost,
            'total_profit': total_profit,
            'total_returns': total_returns,
            'returns_count': returns_count,
            'total_debt': total_debt,
            'total_purchases': total_purchases,
        },
        'daily': daily_data,
        'store_breakdown': store_breakdown,
        'top_products': [{'name': p['product__name'], 'qty': float(p['total_qty'] or 0), 'amount': float(p['total_amount'] or 0)} for p in top_products],
        'top_customers': [{'name': c['customer__name'] or 'N/A', 'orders': c['order_count'], 'amount': float(c['total_amount'] or 0)} for c in top_customers],
    })


@login_required(login_url="/login/")
@brand_owner_required
@report_permission_required
def report_purchases(request):
    context = {'active_tab': 'report_purchases'}
    return render(request, "reports/report_purchases.html", context)


@login_required(login_url="/login/")
def api_report_purchases(request):
    """API báo cáo nhập hàng"""
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    today = datetime.now().date()
    if not from_date:
        from_date = today.replace(day=1).strftime('%Y-%m-%d')
    if not to_date:
        to_date = today.strftime('%Y-%m-%d')

    from products.models import GoodsReceipt
    receipts = GoodsReceipt.objects.filter(
        receipt_date__gte=from_date, receipt_date__lte=to_date
    ).select_related('supplier', 'warehouse').order_by('-receipt_date')
    receipts = filter_by_store(receipts, request, field_name='warehouse__store')

    data = [{
        'id': r.id, 'code': r.code,
        'date': r.receipt_date.strftime('%d/%m/%Y') if r.receipt_date else '',
        'supplier': r.supplier.name if r.supplier else '',
        'warehouse': r.warehouse.name if r.warehouse else '',
        'total_amount': float(r.total_amount),
        'status': r.status, 'status_display': r.get_status_display(),
    } for r in receipts]

    total = sum(d['total_amount'] for d in data if d['status'] != 2)
    count = len([d for d in data if d['status'] != 2])

    return JsonResponse({
        'status': 'ok', 'data': data,
        'summary': {'total_amount': total, 'total_count': count}
    })


@login_required(login_url="/login/")
@brand_owner_required
@report_permission_required
def report_inventory(request):
    context = {'active_tab': 'report_inventory'}
    return render(request, "reports/report_inventory.html", context)


@login_required(login_url="/login/")
def api_report_inventory(request):
    """API báo cáo tồn kho"""
    from products.models import Product, ProductStock, Warehouse
    from core.store_utils import filter_by_store
    warehouse_id = request.GET.get('warehouse_id')

    stocks = ProductStock.objects.select_related('product', 'warehouse').all()
    stocks = filter_by_store(stocks, request, field_name='warehouse__store')
    if warehouse_id:
        stocks = stocks.filter(warehouse_id=warehouse_id)

    data = []
    for s in stocks:
        qty = float(s.quantity)
        alert = ''
        alert_type = ''
        if s.product.min_stock and qty < s.product.min_stock:
            alert = 'Dưới tối thiểu'
            alert_type = 'danger'
        elif s.product.max_stock and qty > s.product.max_stock:
            alert = 'Trên tối đa'
            alert_type = 'warning'

        data.append({
            'product_code': s.product.code,
            'product_name': s.product.name,
            'warehouse': s.warehouse.name,
            'warehouse_id': s.warehouse_id,
            'quantity': qty,
            'min_stock': s.product.min_stock or 0,
            'max_stock': s.product.max_stock or 0,
            'unit': s.product.unit or '',
            'cost_price': float(s.product.cost_price),
            'stock_value': float(s.product.cost_price) * qty,
            'alert': alert,
            'alert_type': alert_type,
        })

    warehouses_qs = Warehouse.objects.filter(is_active=True)
    warehouses_qs = filter_by_store(warehouses_qs, request)
    warehouses = [{'id': w.id, 'name': w.name} for w in warehouses_qs]
    total_value = sum(d['stock_value'] for d in data)
    total_items = sum(d['quantity'] for d in data)
    alert_count = len([d for d in data if d['alert']])

    return JsonResponse({
        'status': 'ok', 'data': data, 'warehouses': warehouses,
        'summary': {'total_value': total_value, 'total_items': total_items, 'alert_count': alert_count}
    })


@login_required(login_url="/login/")
@brand_owner_required
@report_permission_required
def report_finance(request):
    context = {'active_tab': 'report_finance'}
    return render(request, "reports/report_finance.html", context)


@login_required(login_url="/login/")
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

    from finance.models import Receipt, Payment

    # Phiếu thu (hoàn thành)
    receipts = Receipt.objects.filter(
        receipt_date__gte=from_date, receipt_date__lte=to_date, status=1
    )
    receipts = filter_by_store(receipts, request)
    if store_id:
        receipts = receipts.filter(store_id=store_id)
    total_income = float(receipts.aggregate(s=Sum('amount'))['s'] or 0)

    # Thu theo danh mục
    income_by_cat = receipts.values('category__name').annotate(
        amount=Sum('amount')
    ).order_by('-amount')

    # Phiếu chi (hoàn thành)
    payments = Payment.objects.filter(
        payment_date__gte=from_date, payment_date__lte=to_date, status=1
    )
    payments = filter_by_store(payments, request)
    if store_id:
        payments = payments.filter(store_id=store_id)
    total_expense = float(payments.aggregate(s=Sum('amount'))['s'] or 0)

    # Chi theo danh mục
    expense_by_cat = payments.values('category__name').annotate(
        amount=Sum('amount')
    ).order_by('-amount')

    # Doanh thu từ đơn hàng
    orders_revenue = Order.objects.filter(
        order_date__gte=from_date, order_date__lte=to_date
    ).exclude(status=6)
    orders_revenue = filter_by_store(orders_revenue, request)
    if store_id:
        orders_revenue = orders_revenue.filter(store_id=store_id)
    order_revenue = float(orders_revenue.aggregate(s=Sum('paid_amount'))['s'] or 0)
    order_debt = float(orders_revenue.aggregate(s=Sum('final_amount'))['s'] or 0) - order_revenue

    rows = []
    for c in income_by_cat:
        rows.append({'name': c['category__name'] or 'Khác', 'income': float(c['amount'] or 0), 'expense': 0})
    for c in expense_by_cat:
        existing = next((r for r in rows if r['name'] == (c['category__name'] or 'Khác')), None)
        if existing:
            existing['expense'] = float(c['amount'] or 0)
        else:
            rows.append({'name': c['category__name'] or 'Khác', 'income': 0, 'expense': float(c['amount'] or 0)})

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
            st_income = float(st_receipts.aggregate(s=Sum('amount'))['s'] or 0)
            st_expense = float(st_payments.aggregate(s=Sum('amount'))['s'] or 0)
            store_breakdown.append({
                'store_id': st.id,
                'store_name': st.name,
                'brand_name': st.brand.name if st.brand else '',
                'income': st_income,
                'expense': st_expense,
                'net': st_income - st_expense,
            })

    return JsonResponse({
        'status': 'ok',
        'has_multiple_stores': has_multiple,
        'stores': stores_list,
        'summary': {
            'total_income': total_income,
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

    # Danh sách NV cho dropdown filter
    all_salespersons = sorted(salesperson_names)

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
    percent_format = '0.0"%"'
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    total_fill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
    total_font = Font(bold=True, size=10)

    # Title
    ws.merge_cells('A1:L1')
    ws['A1'] = f'BÁO CÁO DOANH THU NHÂN VIÊN BÁN HÀNG'
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
def export_sales_excel(request):
    """Xuất báo cáo bán hàng ra Excel"""
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

    orders = Order.objects.filter(
        order_date__gte=from_date, order_date__lte=to_date
    ).exclude(status=6)
    orders = filter_by_store(orders, request)
    if store_id:
        orders = orders.filter(store_id=store_id)

    # Styles
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Doanh thu theo ngày'
    header_font = Font(bold=True, size=14, color='FFFFFF')
    header_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
    sub_font = Font(bold=True, size=10, color='FFFFFF')
    sub_fill = PatternFill(start_color='2E75B6', end_color='2E75B6', fill_type='solid')
    thin = Border(left=Side(style='thin'), right=Side(style='thin'),
                  top=Side(style='thin'), bottom=Side(style='thin'))
    total_fill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
    money_fmt = '#,##0'

    ws.merge_cells('A1:G1')
    ws['A1'] = 'BÁO CÁO BÁN HÀNG'
    ws['A1'].font = header_font
    ws['A1'].fill = header_fill
    ws['A1'].alignment = Alignment(horizontal='center')
    ws.merge_cells('A2:G2')
    ws['A2'] = f'Từ {from_date} đến {to_date}'
    ws['A2'].font = Font(italic=True, size=10)
    ws['A2'].alignment = Alignment(horizontal='center')

    headers = ['STT', 'Ngày', 'Số ĐH', 'Doanh thu', 'Giá vốn', 'Lợi nhuận', 'Trả hàng']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.font = sub_font
        cell.fill = sub_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin

    from django.db.models.functions import TruncDate
    daily = orders.annotate(day=TruncDate('order_date')).values('day').annotate(
        count=Count('id'), revenue=Sum('final_amount')
    ).order_by('day')

    row = 5
    grand = {'count': 0, 'revenue': 0, 'cost': 0, 'profit': 0, 'returns': 0}
    for idx, d in enumerate(daily, 1):
        day_cost = float(OrderItem.objects.filter(
            order__order_date=d['day'], order__status__in=[0,1,2,3,4,5]
        ).exclude(order__status=6).aggregate(c=Sum(F('cost_price') * F('quantity')))['c'] or 0)
        day_revenue = float(d['revenue'] or 0)
        day_returns = float(OrderReturn.objects.filter(
            return_date=d['day']).exclude(status=3).aggregate(
            s=Sum('total_refund'))['s'] or 0)

        vals = [idx, d['day'].strftime('%d/%m/%Y'), d['count'], day_revenue,
                day_cost, day_revenue - day_cost, day_returns]
        for col, val in enumerate(vals, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = thin
            if col >= 4:
                cell.number_format = money_fmt
        grand['count'] += d['count']
        grand['revenue'] += day_revenue
        grand['cost'] += day_cost
        grand['profit'] += day_revenue - day_cost
        grand['returns'] += day_returns
        row += 1

    # Total row
    totals = ['', 'TỔNG', grand['count'], grand['revenue'], grand['cost'], grand['profit'], grand['returns']]
    for col, val in enumerate(totals, 1):
        cell = ws.cell(row=row, column=col, value=val)
        cell.font = Font(bold=True)
        cell.fill = total_fill
        cell.border = thin
        if col >= 4:
            cell.number_format = money_fmt

    # Sheet 2: Top sản phẩm
    ws2 = wb.create_sheet('Top sản phẩm')
    sp_headers = ['STT', 'Sản phẩm', 'Số lượng bán', 'Doanh thu']
    for col, h in enumerate(sp_headers, 1):
        cell = ws2.cell(row=1, column=col, value=h)
        cell.font = sub_font
        cell.fill = sub_fill
        cell.border = thin

    top_products = OrderItem.objects.filter(order__in=orders).values(
        'product__code', 'product__name'
    ).annotate(
        total_qty=Sum('quantity'), total_amount=Sum('total_price')
    ).order_by('-total_qty')[:20]

    for idx, p in enumerate(top_products, 1):
        ws2.cell(row=idx+1, column=1, value=idx).border = thin
        ws2.cell(row=idx+1, column=2, value=f"{p['product__code']} - {p['product__name']}").border = thin
        ws2.cell(row=idx+1, column=3, value=float(p['total_qty'] or 0)).border = thin
        c = ws2.cell(row=idx+1, column=4, value=float(p['total_amount'] or 0))
        c.number_format = money_fmt
        c.border = thin

    for i, w in enumerate([6, 35, 15, 18], 1):
        ws2.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    for i, w in enumerate([6, 20, 12, 18, 18, 18, 15], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f'BC_Ban_hang_{from_date}_{to_date}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required(login_url="/login/")
def export_inventory_excel(request):
    """Xuất báo cáo tồn kho ra Excel"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse
    from products.models import ProductStock, Warehouse

    warehouse_id = request.GET.get('warehouse_id')

    stocks = ProductStock.objects.select_related('product', 'warehouse').all()
    stocks = filter_by_store(stocks, request, field_name='warehouse__store')
    if warehouse_id:
        stocks = stocks.filter(warehouse_id=warehouse_id)

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

    ws.merge_cells('A1:K1')
    ws['A1'] = 'BÁO CÁO TỒN KHO'
    ws['A1'].font = header_font
    ws['A1'].fill = header_fill
    ws['A1'].alignment = Alignment(horizontal='center')
    ws.merge_cells('A2:K2')
    ws['A2'] = f'Ngày xuất: {datetime.now().strftime("%d/%m/%Y %H:%M")}'
    ws['A2'].font = Font(italic=True, size=10)
    ws['A2'].alignment = Alignment(horizontal='center')

    headers = ['STT', 'Mã SP', 'Tên sản phẩm', 'ĐVT', 'Kho', 'Tồn kho',
               'Tối thiểu', 'Tối đa', 'Giá vốn', 'Giá trị tồn', 'Cảnh báo']
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
        cost = float(s.product.cost_price)
        value = cost * qty
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

        vals = [idx, s.product.code, s.product.name, s.product.unit or '',
                s.warehouse.name, qty, s.product.min_stock or 0,
                s.product.max_stock or 0, cost, value, alert]
        for col, val in enumerate(vals, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = thin
            if col in (9, 10):
                cell.number_format = money_fmt
            if fill:
                cell.fill = fill
        row += 1

    # Total
    ws.cell(row=row, column=1, value='').border = thin
    c = ws.cell(row=row, column=2, value='TỔNG CỘNG')
    c.font = Font(bold=True)
    c.border = thin
    for col in range(3, 6):
        ws.cell(row=row, column=col, value='').border = thin
    c = ws.cell(row=row, column=6, value=total_qty)
    c.font = Font(bold=True)
    c.border = thin
    for col in range(7, 10):
        ws.cell(row=row, column=col, value='').border = thin
    c = ws.cell(row=row, column=10, value=total_value)
    c.font = Font(bold=True)
    c.number_format = money_fmt
    c.border = thin
    ws.cell(row=row, column=11, value='').border = thin

    col_widths = [6, 12, 30, 8, 15, 12, 12, 12, 15, 18, 15]
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
def export_purchases_excel(request):
    """Xuất báo cáo nhập hàng ra Excel"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse
    from products.models import GoodsReceipt

    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    today = datetime.now().date()
    if not from_date:
        from_date = today.replace(day=1).strftime('%Y-%m-%d')
    if not to_date:
        to_date = today.strftime('%Y-%m-%d')

    receipts = GoodsReceipt.objects.filter(
        receipt_date__gte=from_date, receipt_date__lte=to_date
    ).select_related('supplier', 'warehouse').order_by('-receipt_date')
    receipts = filter_by_store(receipts, request, field_name='warehouse__store')

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
    ws['A1'].font = hf; ws['A1'].fill = hfill; ws['A1'].alignment = Alignment(horizontal='center')
    ws.merge_cells('A2:G2')
    ws['A2'] = f'Từ {from_date} đến {to_date}'
    ws['A2'].font = Font(italic=True, size=10); ws['A2'].alignment = Alignment(horizontal='center')

    headers = ['STT', 'Mã phiếu', 'Ngày', 'Nhà cung cấp', 'Kho', 'Tổng tiền', 'Trạng thái']
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=4, column=col, value=h)
        c.font = sf; c.fill = sfill; c.alignment = Alignment(horizontal='center'); c.border = thin

    row = 5
    total = 0
    for idx, r in enumerate(receipts, 1):
        amt = float(r.total_amount)
        is_cancel = (r.status == 2)
        if not is_cancel:
            total += amt
        vals = [idx, r.code,
                r.receipt_date.strftime('%d/%m/%Y') if r.receipt_date else '',
                r.supplier.name if r.supplier else '',
                r.warehouse.name if r.warehouse else '',
                amt, r.get_status_display()]
        for col, val in enumerate(vals, 1):
            c = ws.cell(row=row, column=col, value=val)
            c.border = thin
            if col == 6: c.number_format = mfmt
            if is_cancel: c.fill = cancel_fill
        row += 1

    totals = ['', 'TỔNG', '', '', '', total, '']
    for col, val in enumerate(totals, 1):
        c = ws.cell(row=row, column=col, value=val)
        c.font = Font(bold=True); c.fill = tfill; c.border = thin
        if col == 6: c.number_format = mfmt

    for i, w in enumerate([6, 15, 12, 25, 15, 18, 12], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="BC_Nhap_hang_{from_date}_{to_date}.xlsx"'
    wb.save(response)
    return response


@login_required(login_url="/login/")
def export_finance_excel(request):
    """Xuất báo cáo tài chính ra Excel"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse
    from finance.models import Receipt, Payment

    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    store_id = request.GET.get('store_id')
    today = datetime.now().date()
    if not from_date:
        from_date = today.replace(day=1).strftime('%Y-%m-%d')
    if not to_date:
        to_date = today.strftime('%Y-%m-%d')

    receipts = Receipt.objects.filter(
        receipt_date__gte=from_date, receipt_date__lte=to_date, status=1)
    receipts = filter_by_store(receipts, request)
    if store_id: receipts = receipts.filter(store_id=store_id)

    payments = Payment.objects.filter(
        payment_date__gte=from_date, payment_date__lte=to_date, status=1)
    payments = filter_by_store(payments, request)
    if store_id: payments = payments.filter(store_id=store_id)

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
    tfill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
    mfmt = '#,##0'

    ws.merge_cells('A1:G1')
    ws['A1'] = 'BÁO CÁO THU CHI'
    ws['A1'].font = hf; ws['A1'].fill = hfill; ws['A1'].alignment = Alignment(horizontal='center')
    ws.merge_cells('A2:G2')
    ws['A2'] = f'Từ {from_date} đến {to_date}'
    ws['A2'].font = Font(italic=True, size=10); ws['A2'].alignment = Alignment(horizontal='center')

    # Summary row
    total_income = float(receipts.aggregate(s=Sum('amount'))['s'] or 0)
    total_expense = float(payments.aggregate(s=Sum('amount'))['s'] or 0)
    ws['A3'] = f'Tổng thu: {total_income:,.0f}đ  |  Tổng chi: {total_expense:,.0f}đ  |  Lãi/Lỗ: {total_income - total_expense:,.0f}đ'
    ws['A3'].font = Font(bold=True, size=10)
    ws.merge_cells('A3:G3')

    headers = ['STT', 'Loại', 'Mã phiếu', 'Ngày', 'Danh mục', 'Diễn giải', 'Số tiền']
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=5, column=col, value=h)
        c.font = sf; c.fill = sfill; c.alignment = Alignment(horizontal='center'); c.border = thin

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
            c.border = thin; c.fill = green_fill
            if col == 7: c.number_format = mfmt
        idx += 1; row += 1

    # Ghi phiếu chi
    for p in payments.select_related('category').order_by('-payment_date'):
        vals = [idx, 'CHI', p.code,
                p.payment_date.strftime('%d/%m/%Y') if p.payment_date else '',
                p.category.name if p.category else '',
                p.description or '', float(p.amount)]
        for col, val in enumerate(vals, 1):
            c = ws.cell(row=row, column=col, value=val)
            c.border = thin; c.fill = red_fill
            if col == 7: c.number_format = mfmt
        idx += 1; row += 1

    # Total rows
    for label, amt, fill in [('TỔNG THU', total_income, green_fill),
                               ('TỔNG CHI', total_expense, red_fill)]:
        for col, val in enumerate(['', label, '', '', '', '', amt], 1):
            c = ws.cell(row=row, column=col, value=val)
            c.font = Font(bold=True); c.fill = fill; c.border = thin
            if col == 7: c.number_format = mfmt
        row += 1
    net = total_income - total_expense
    for col, val in enumerate(['', 'LÃI/LỖ', '', '', '', '', net], 1):
        c = ws.cell(row=row, column=col, value=val)
        c.font = Font(bold=True, color='006600' if net >= 0 else 'CC0000')
        c.fill = tfill; c.border = thin
        if col == 7: c.number_format = mfmt

    for i, w in enumerate([6, 8, 15, 12, 20, 30, 18], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="BC_Thu_chi_{from_date}_{to_date}.xlsx"'
    wb.save(response)
    return response
