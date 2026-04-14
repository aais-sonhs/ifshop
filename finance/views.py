import json
import logging
from decimal import Decimal
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Q
from .models import FinanceCategory, CashBook, Receipt, ReceiptItem, Payment, PaymentMethodOption
from .services import (
    capture_receipt_effect,
    delete_receipt_with_effect,
    save_receipt_with_effect,
)
from customers.models import Customer
from orders.models import Order
from products.models import GoodsReceipt, Supplier
from core.store_utils import filter_by_store, get_user_store, get_managed_store_ids, brand_owner_required

logger = logging.getLogger(__name__)


def _get_default_store_for_request(request):
    store = get_user_store(request)
    if store:
        return store

    from system_management.models import Store

    store_ids = get_managed_store_ids(request.user)
    if not store_ids:
        return None
    return Store.objects.filter(id__in=store_ids).order_by('id').first()


def _filter_receipts_for_user(queryset, request):
    if request.user.is_superuser:
        return queryset.none()
    store_ids = get_managed_store_ids(request.user)
    if not store_ids:
        return queryset.none()
    return queryset.filter(
        Q(store_id__in=store_ids) |
        Q(store_id__isnull=True, order__store_id__in=store_ids)
    )


def _serialize_payment_methods():
    return [{
        'id': m.id,
        'code': m.code,
        'name': m.name,
        'description': m.description or '',
        'legacy_type': m.legacy_type,
        'legacy_type_display': m.get_legacy_type_display(),
        'default_cash_book_id': m.default_cash_book_id,
        'default_cash_book': m.default_cash_book.name if m.default_cash_book else '',
        'sort_order': m.sort_order,
        'is_active': m.is_active,
    } for m in PaymentMethodOption.objects.select_related('default_cash_book').filter(is_active=True)]


@login_required(login_url="/login/")
@brand_owner_required
def receipt_tbl(request):
    categories = list(FinanceCategory.objects.filter(type=1, is_active=True).values('id', 'name'))
    cashbooks = list(CashBook.objects.filter(is_active=True).values('id', 'name'))
    payment_methods = _serialize_payment_methods()
    from core.store_utils import get_managed_store_ids
    store_ids = get_managed_store_ids(request.user)
    customers = list(Customer.objects.filter(is_active=True, store_id__in=store_ids).values('id', 'code', 'name'))
    context = {
        'active_tab': 'receipt_tbl',
        'categories': categories,
        'cashbooks': cashbooks,
        'payment_methods': payment_methods,
        'customers': customers,
    }
    return render(request, "finance/receipt_list.html", context)


@login_required(login_url="/login/")
@brand_owner_required
def payment_tbl(request):
    categories = list(FinanceCategory.objects.filter(type=2, is_active=True).values('id', 'name'))
    cashbooks = list(CashBook.objects.filter(is_active=True).values('id', 'name'))
    payment_methods = _serialize_payment_methods()
    suppliers = list(Supplier.objects.filter(is_active=True).values('id', 'code', 'name'))
    goods_receipts = list(GoodsReceipt.objects.select_related('supplier').values(
        'id', 'code', 'supplier__name', 'total_amount', 'status'
    ).order_by('-receipt_date'))
    context = {
        'active_tab': 'payment_tbl',
        'categories': categories,
        'cashbooks': cashbooks,
        'payment_methods': payment_methods,
        'suppliers': suppliers,
        'goods_receipts': goods_receipts,
    }
    return render(request, "finance/payment_list.html", context)


@login_required(login_url="/login/")
def finance_list_tbl(request):
    context = {'active_tab': 'finance_list_tbl'}
    return render(request, "finance/finance_list.html", context)


@login_required(login_url="/login/")
def cashbook_tbl(request):
    cashbooks = list(CashBook.objects.filter(is_active=True).values('id', 'name'))
    context = {'active_tab': 'cashbook_tbl', 'cashbooks': cashbooks}
    return render(request, "finance/cashbook.html", context)


# ============ API: ORDERS FOR RECEIPT ============

@login_required(login_url="/login/")
def api_get_orders_for_receipt(request):
    """Lấy DS đơn hàng còn nợ để tạo phiếu thu"""
    customer_id = request.GET.get('customer_id')
    orders = Order.objects.select_related('customer').exclude(status=6)
    orders = filter_by_store(orders, request)
    if customer_id:
        orders = orders.filter(customer_id=customer_id)

    data = []
    for o in orders:
        remaining = float(o.final_amount) - float(o.paid_amount)
        data.append({
            'id': o.id,
            'code': o.code,
            'customer': o.customer.name if o.customer else '',
            'customer_id': o.customer_id,
            'order_date': o.order_date.strftime('%Y-%m-%d') if o.order_date else '',
            'final_amount': float(o.final_amount),
            'paid_amount': float(o.paid_amount),
            'remaining': remaining,
            'status_display': o.get_status_display(),
            'payment_status_display': o.get_payment_status_display(),
        })
    return JsonResponse({'data': data})


# ============ API: RECEIPT ============

@login_required(login_url="/login/")
def api_get_receipts(request):
    receipts = Receipt.objects.select_related('category', 'cash_book', 'customer', 'order', 'created_by', 'payment_method_option').all()
    receipts = _filter_receipts_for_user(receipts, request)
    data = [{
        'id': r.id, 'code': r.code,
        'category': r.category.name if r.category else '',
        'category_id': r.category_id,
        'cash_book': r.cash_book.name if r.cash_book else '',
        'cash_book_id': r.cash_book_id,
        'customer': r.customer.name if r.customer else '',
        'customer_id': r.customer_id,
        'order': r.order.code if r.order else '',
        'order_id': r.order_id,
        'order_remaining': float(r.order.final_amount - r.order.paid_amount) if r.order else 0,
        'amount': float(r.amount),
        'description': r.description or '',
        'receipt_date': r.receipt_date.strftime('%Y-%m-%d') if r.receipt_date else '',
        'status': r.status, 'status_display': r.get_status_display(),
        'payment_method': r.payment_method,
        'payment_method_option_id': r.payment_method_option_id,
        'payment_method_display': r.get_payment_method_label(),
        'note': r.note or '',
        'created_by': r.created_by.get_full_name() or r.created_by.username if r.created_by else '',
    } for r in receipts]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_receipt_summary(request):
    receipts = Receipt.objects.select_related('cash_book').filter(status=1)
    receipts = _filter_receipts_for_user(receipts, request)
    # Date filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        receipts = receipts.filter(receipt_date__gte=date_from)
    if date_to:
        receipts = receipts.filter(receipt_date__lte=date_to)

    by_cashbook = {}
    by_method = {}
    total_amount = 0

    for receipt in receipts:
        amount = float(receipt.amount or 0)
        total_amount += amount

        cashbook_name = receipt.cash_book.name if receipt.cash_book else 'Chưa gán tài khoản'
        by_cashbook[cashbook_name] = by_cashbook.get(cashbook_name, 0) + amount

        method_name = receipt.get_payment_method_label()
        by_method[method_name] = by_method.get(method_name, 0) + amount

    cashbook_rows = [
        {'name': name, 'amount': amount}
        for name, amount in sorted(by_cashbook.items(), key=lambda item: item[1], reverse=True)
    ]
    method_rows = [
        {'name': name, 'amount': amount}
        for name, amount in sorted(by_method.items(), key=lambda item: item[1], reverse=True)
    ]
    return JsonResponse({
        'status': 'ok',
        'summary': {
            'total_amount': total_amount,
            'receipt_count': receipts.count(),
            'by_cashbook': cashbook_rows,
            'by_method': method_rows,
        }
    })


@login_required(login_url="/login/")
def api_save_receipt(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        rid = data.get('id')
        old_effect = None
        if rid:
            r = _filter_receipts_for_user(Receipt.objects.all(), request).get(id=rid)
            old_effect = capture_receipt_effect(r)
        else:
            r = Receipt()
            r.created_by = request.user

        r.code = data.get('code', '')
        r.category_id = data.get('category_id') or None
        r.cash_book_id = data.get('cash_book_id') or None
        r.customer_id = data.get('customer_id') or None
        r.order_id = data.get('order_id') or None
        r.amount = data.get('amount', 0) or 0
        r.description = data.get('description', '')
        r.receipt_date = data.get('receipt_date')
        r.status = data.get('status', 0)
        r.payment_method = data.get('payment_method', 2)
        r.payment_method_option_id = data.get('payment_method_option_id') or None
        r.note = data.get('note', '')

        linked_order = None
        if r.order_id:
            linked_order = filter_by_store(Order.objects.filter(id=r.order_id), request).first()
            if not linked_order:
                return JsonResponse({'status': 'error', 'message': 'Không tìm thấy đơn hàng trong phạm vi cửa hàng'})
            r.store_id = linked_order.store_id
            if not r.customer_id:
                r.customer_id = linked_order.customer_id
        elif not r.store_id:
            store = _get_default_store_for_request(request)
            if store:
                r.store = store

        if r.payment_method_option_id:
            method = PaymentMethodOption.objects.select_related('default_cash_book').filter(id=r.payment_method_option_id).first()
            if method:
                r.payment_method = method.legacy_type if method.legacy_type in (1, 2) else 2
                if not r.cash_book_id and method.default_cash_book_id:
                    r.cash_book_id = method.default_cash_book_id

        save_receipt_with_effect(r, old_effect=old_effect)

        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_receipt(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        receipt = _filter_receipts_for_user(Receipt.objects.all(), request).filter(id=data.get('id')).first()
        if not receipt:
            return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phiếu thu'})
        delete_receipt_with_effect(receipt)

        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: PAYMENT ============

@login_required(login_url="/login/")
def api_get_payments(request):
    payments = Payment.objects.select_related('category', 'cash_book', 'supplier', 'customer', 'goods_receipt', 'payment_method_option').all()
    payments = filter_by_store(payments, request)
    data = [{
        'id': p.id, 'code': p.code,
        'category': p.category.name if p.category else '',
        'category_id': p.category_id,
        'cash_book': p.cash_book.name if p.cash_book else '',
        'cash_book_id': p.cash_book_id,
        'supplier': p.supplier.name if p.supplier else '',
        'supplier_id': p.supplier_id,
        'customer': p.customer.name if p.customer else '',
        'target': p.supplier.name if p.supplier else (p.customer.name if p.customer else ''),
        'goods_receipt': p.goods_receipt.code if p.goods_receipt else '',
        'goods_receipt_id': p.goods_receipt_id,
        'amount': float(p.amount),
        'description': p.description or '',
        'payment_date': p.payment_date.strftime('%Y-%m-%d') if p.payment_date else '',
        'status': p.status, 'status_display': p.get_status_display(),
        'payment_method': p.payment_method,
        'payment_method_option_id': p.payment_method_option_id,
        'payment_method_display': p.get_payment_method_label(),
        'note': p.note or '',
    } for p in payments]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_payment(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            pid = data.get('id')
            old_amount = 0
            old_cash_book_id = None
            old_status = None
            if pid:
                p = Payment.objects.get(id=pid)
                old_amount = float(p.amount)
                old_cash_book_id = p.cash_book_id
                old_status = p.status
            else:
                p = Payment()
                p.created_by = request.user
            p.code = data.get('code', '')
            p.category_id = data.get('category_id') or None
            p.cash_book_id = data.get('cash_book_id') or None
            p.supplier_id = data.get('supplier_id') or None
            p.goods_receipt_id = data.get('goods_receipt_id') or None
            p.amount = data.get('amount', 0) or 0
            p.description = data.get('description', '')
            p.payment_date = data.get('payment_date')
            p.status = data.get('status', 0)
            p.payment_method = data.get('payment_method', 2)
            p.payment_method_option_id = data.get('payment_method_option_id') or None
            p.note = data.get('note', '')
            if p.payment_method_option_id:
                method = PaymentMethodOption.objects.select_related('default_cash_book').filter(id=p.payment_method_option_id).first()
                if method:
                    p.payment_method = method.legacy_type if method.legacy_type in (1, 2) else 2
                    if not p.cash_book_id and method.default_cash_book_id:
                        p.cash_book_id = method.default_cash_book_id

            new_amount = float(p.amount)
            new_status = int(p.status)

            # Hoàn lại số dư quỹ cũ (nếu phiếu cũ đã hoàn thành)
            if pid and old_status == 1 and old_cash_book_id:
                old_book = CashBook.objects.select_for_update().get(id=old_cash_book_id)
                old_book.balance += Decimal(str(old_amount))
                old_book.save(update_fields=['balance'])

            # Kiểm tra và trừ số dư quỹ mới (nếu phiếu mới hoàn thành)
            if new_status == 1 and p.cash_book_id:
                book = CashBook.objects.select_for_update().get(id=p.cash_book_id)
                if float(book.balance) < new_amount:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Số dư quỹ "{book.name}" không đủ! Số dư hiện tại: {int(book.balance):,}đ, cần chi: {int(new_amount):,}đ'
                    })
                book.balance -= Decimal(str(new_amount))
                book.save(update_fields=['balance'])

            p.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_payment(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        Payment.objects.filter(id=data.get('id')).delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: FINANCE CATEGORY ============

@login_required(login_url="/login/")
def api_get_finance_categories(request):
    cats = FinanceCategory.objects.all()
    data = [{
        'id': c.id, 'name': c.name, 'type': c.type,
        'type_display': c.get_type_display(),
        'description': c.description or '', 'is_active': c.is_active,
    } for c in cats]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_finance_category(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        cid = data.get('id')
        if cid:
            c = FinanceCategory.objects.get(id=cid)
        else:
            c = FinanceCategory()
        c.name = data.get('name', '')
        c.type = data.get('type', 1)
        c.description = data.get('description', '')
        c.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: CASHBOOK ============

@login_required(login_url="/login/")
def api_get_cashbooks(request):
    books = CashBook.objects.all()
    data = [{
        'id': b.id, 'name': b.name, 'description': b.description or '',
        'balance': float(b.balance), 'is_active': b.is_active,
    } for b in books]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_cashbook(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        bid = data.get('id')
        if bid:
            b = CashBook.objects.get(id=bid)
        else:
            b = CashBook()
        b.name = data.get('name', '')
        b.description = data.get('description', '')
        b.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_get_payment_methods(request):
    data = [{
        'id': m.id,
        'code': m.code,
        'name': m.name,
        'description': m.description or '',
        'legacy_type': m.legacy_type,
        'legacy_type_display': m.get_legacy_type_display(),
        'default_cash_book_id': m.default_cash_book_id,
        'default_cash_book': m.default_cash_book.name if m.default_cash_book else '',
        'sort_order': m.sort_order,
        'is_active': m.is_active,
    } for m in PaymentMethodOption.objects.select_related('default_cash_book').all()]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_payment_method(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        mid = data.get('id')
        if mid:
            method = PaymentMethodOption.objects.get(id=mid)
        else:
            method = PaymentMethodOption()
        method.code = (data.get('code') or '').strip().upper()
        method.name = (data.get('name') or '').strip()
        method.description = data.get('description', '')
        method.legacy_type = int(data.get('legacy_type', 3) or 3)
        method.default_cash_book_id = data.get('default_cash_book_id') or None
        method.sort_order = int(data.get('sort_order', 0) or 0)
        method.is_active = bool(data.get('is_active', True))
        if not method.code or not method.name:
            return JsonResponse({'status': 'error', 'message': 'Vui lòng nhập mã và tên phương thức'})
        method.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu phương thức thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_payment_method(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        method = PaymentMethodOption.objects.get(id=data.get('id'))
        # Check if any receipts/payments reference this method
        receipt_count = Receipt.objects.filter(payment_method_option=method).count()
        payment_count = Payment.objects.filter(payment_method_option=method).count()
        if receipt_count + payment_count > 0:
            return JsonResponse({
                'status': 'error',
                'message': f'Không thể xóa "{method.name}". Đang có {receipt_count} phiếu thu và {payment_count} phiếu chi sử dụng.'
            })
        method.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except PaymentMethodOption.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phương thức'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
@brand_owner_required
def setting_payment_methods(request):
    cashbooks = list(CashBook.objects.filter(is_active=True).values('id', 'name'))
    context = {
        'active_tab': 'setting_payment_methods',
        'cashbooks': cashbooks,
    }
    return render(request, "finance/setting_payment_methods.html", context)


# ============ EXCEL EXPORT ============

@login_required(login_url="/login/")
def export_receipts_excel(request):
    """Xuất danh sách phiếu thu ra Excel"""
    from core.excel_export import excel_response
    from datetime import datetime

    receipts = Receipt.objects.select_related(
        'category', 'cash_book', 'customer', 'order', 'created_by', 'payment_method_option'
    ).filter(status=1)
    receipts = _filter_receipts_for_user(receipts, request)

    # Date filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        receipts = receipts.filter(receipt_date__gte=date_from)
    if date_to:
        receipts = receipts.filter(receipt_date__lte=date_to)

    columns = [
        {'key': 'stt', 'label': 'STT', 'width': 6},
        {'key': 'code', 'label': 'Mã phiếu', 'width': 14},
        {'key': 'category', 'label': 'Danh mục', 'width': 16},
        {'key': 'customer', 'label': 'Khách hàng', 'width': 22},
        {'key': 'order', 'label': 'Đơn hàng', 'width': 14},
        {'key': 'amount', 'label': 'Số tiền', 'width': 16},
        {'key': 'method', 'label': 'Hình thức TT', 'width': 16},
        {'key': 'date', 'label': 'Ngày thu', 'width': 13},
        {'key': 'cashbook', 'label': 'Quỹ/Tài khoản', 'width': 20},
        {'key': 'creator', 'label': 'Người tạo', 'width': 16},
        {'key': 'description', 'label': 'Diễn giải', 'width': 30},
    ]

    rows = []
    total = 0
    for i, r in enumerate(receipts, 1):
        total += float(r.amount or 0)
        rows.append({
            'stt': i,
            'code': r.code,
            'category': r.category.name if r.category else '',
            'customer': r.customer.name if r.customer else '',
            'order': r.order.code if r.order else '',
            'amount': float(r.amount or 0),
            'method': r.get_payment_method_label(),
            'date': r.receipt_date,
            'cashbook': r.cash_book.name if r.cash_book else '',
            'creator': (r.created_by.get_full_name() or r.created_by.username) if r.created_by else '',
            'description': r.description or '',
        })

    period = ''
    if date_from and date_to:
        period = f' ({date_from} → {date_to})'
    elif date_from:
        period = f' (từ {date_from})'
    elif date_to:
        period = f' (đến {date_to})'

    return excel_response(
        title='DANH SÁCH PHIẾU THU',
        subtitle=f'Xuất ngày {datetime.now().strftime("%d/%m/%Y %H:%M")}{period}',
        columns=columns,
        rows=rows,
        filename=f'Phieu_thu_{datetime.now().strftime("%Y%m%d")}',
        money_cols=['amount'],
        total_row={'stt': '', 'code': 'TỔNG CỘNG', 'amount': total},
    )


@login_required(login_url="/login/")
def export_payments_excel(request):
    """Xuất danh sách phiếu chi ra Excel"""
    from core.excel_export import excel_response
    from datetime import datetime

    payments = Payment.objects.select_related(
        'category', 'cash_book', 'supplier', 'customer', 'payment_method_option'
    ).filter(status=1)
    payments = filter_by_store(payments, request)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        payments = payments.filter(payment_date__gte=date_from)
    if date_to:
        payments = payments.filter(payment_date__lte=date_to)

    columns = [
        {'key': 'stt', 'label': 'STT', 'width': 6},
        {'key': 'code', 'label': 'Mã phiếu', 'width': 14},
        {'key': 'category', 'label': 'Danh mục', 'width': 16},
        {'key': 'target', 'label': 'Người nhận', 'width': 22},
        {'key': 'amount', 'label': 'Số tiền', 'width': 16},
        {'key': 'method', 'label': 'Hình thức TT', 'width': 16},
        {'key': 'date', 'label': 'Ngày chi', 'width': 13},
        {'key': 'cashbook', 'label': 'Quỹ/Tài khoản', 'width': 20},
        {'key': 'description', 'label': 'Diễn giải', 'width': 30},
    ]

    rows = []
    total = 0
    for i, p in enumerate(payments, 1):
        total += float(p.amount or 0)
        target = p.supplier.name if p.supplier else (p.customer.name if p.customer else '')
        rows.append({
            'stt': i,
            'code': p.code,
            'category': p.category.name if p.category else '',
            'target': target,
            'amount': float(p.amount or 0),
            'method': p.get_payment_method_label(),
            'date': p.payment_date,
            'cashbook': p.cash_book.name if p.cash_book else '',
            'description': p.description or '',
        })

    period = ''
    if date_from and date_to:
        period = f' ({date_from} → {date_to})'
    elif date_from:
        period = f' (từ {date_from})'
    elif date_to:
        period = f' (đến {date_to})'

    return excel_response(
        title='DANH SÁCH PHIẾU CHI',
        subtitle=f'Xuất ngày {datetime.now().strftime("%d/%m/%Y %H:%M")}{period}',
        columns=columns,
        rows=rows,
        filename=f'Phieu_chi_{datetime.now().strftime("%Y%m%d")}',
        money_cols=['amount'],
        total_row={'stt': '', 'code': 'TỔNG CỘNG', 'amount': total},
    )
