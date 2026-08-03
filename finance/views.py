import json
import logging
import re
from functools import wraps
from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.db import transaction, IntegrityError
from django.db.models import (
    Case,
    CharField,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Prefetch,
    Q,
    Max,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_date
from .models import (
    FinanceCategory,
    CashBook,
    Receipt,
    Payment,
    PaymentMethodOption,
    FinancialPlan,
    FinancialPlanItem,
    FinancialPlanAllocation,
    FinancialPlanRevision,
    SupplierPaymentSchedule,
)
from .services import (
    capture_receipt_effect,
    save_receipt_with_effect,
)
from customers.models import Customer
from orders.models import Order
from products.models import GoodsReceipt, PurchaseReturn, Supplier
from core.store_utils import filter_by_store, get_user_store, get_managed_store_ids, brand_owner_required, can_manage_users
from core.unique_codes import save_with_generated_code
from system_management.menu_config import is_menu_visible_for_user

logger = logging.getLogger(__name__)


def _forbid_json(message='Bạn không có quyền thực hiện thao tác này'):
    return JsonResponse({'status': 'error', 'message': message}, status=403)


def financial_plan_menu_required(view_func):
    """Ẩn chức năng phải đi cùng chặn URL/API trực tiếp theo thương hiệu."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_menu_visible_for_user(request.user, 'financial_plans'):
            message = 'Chức năng Kế hoạch tài chính đang tắt cho thương hiệu này.'
            if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return _forbid_json(message)
            return redirect('/dashboard/')
        return view_func(request, *args, **kwargs)
    return wrapper


def _get_default_store_for_request(request):
    """Lấy store mặc định của user hiện tại để gán cho chứng từ không đi kèm đơn/phiếu nhập."""
    store = get_user_store(request)
    if store:
        return store

    from system_management.models import Store

    store_ids = get_managed_store_ids(request.user)
    if not store_ids:
        return None
    return Store.objects.filter(id__in=store_ids).order_by('id').first()


def _filter_receipts_for_user(queryset, request):
    """Lọc phiếu thu trong phạm vi store mà user được phép xem.

    Phiếu thu có thể mang `store_id` trực tiếp, hoặc đi theo `order.store_id`
    với dữ liệu cũ chưa gán store đầy đủ.
    """
    if request.user.is_superuser:
        return queryset.none()
    store_ids = get_managed_store_ids(request.user)
    if not store_ids:
        return queryset.none()
    return queryset.filter(
        Q(store_id__in=store_ids) |
        Q(store_id__isnull=True, order__store_id__in=store_ids)
    )


def _filter_payments_for_user(queryset, request):
    """Lọc phiếu chi trong phạm vi store mà user được phép xem.

    Phiếu chi có thể mang `store_id` trực tiếp, hoặc suy ra qua
    `goods_receipt.warehouse.store_id` với dữ liệu cũ.
    """
    if request.user.is_superuser:
        return queryset.none()
    store_ids = get_managed_store_ids(request.user)
    if not store_ids:
        return queryset.none()
    return queryset.filter(
        Q(store_id__in=store_ids) |
        Q(store_id__isnull=True, goods_receipt__warehouse__store_id__in=store_ids)
    )


def _get_user_display_name(user):
    """Ưu tiên họ tên đầy đủ; fallback về username nếu hồ sơ chưa đủ dữ liệu."""
    if not user:
        return ''
    return user.get_full_name() or user.username or ''


def _parse_decimal_filter(value):
    """Chuyển tham số filter số tiền về Decimal; dữ liệu lỗi thì bỏ qua filter."""
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _parse_payment_decimal(value, label):
    """Đọc số tiền từ payload và chặn NaN/Infinity trước khi ghi sổ quỹ."""
    if value in (None, ''):
        return Decimal('0')
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError, AttributeError):
        raise ValueError(f'{label} không hợp lệ.')
    if not number.is_finite():
        raise ValueError(f'{label} không hợp lệ.')
    return number


def _apply_payment_promotion(payment, data):
    """Tính tiền thực chi từ tiền trước KM và KM lưu riêng trên phiếu chi.

    Payload cũ chỉ gửi `amount` vẫn được giữ tương thích: `amount` khi đó là
    tiền thực chi. Giao diện mới gửi `gross_amount` cùng các trường KM để phía
    server là nơi tính kết quả cuối cùng và không tin vào phép tính JavaScript.
    """
    promotion_keys = {
        'gross_amount', 'promotion_mode', 'promotion_amount', 'promotion_percent',
    }
    if not any(key in data for key in promotion_keys):
        actual_amount = _parse_payment_decimal(data.get('amount', 0), 'Số tiền thực chi')
        if actual_amount < 0:
            raise ValueError('Số tiền thực chi không được âm.')
        payment.amount = actual_amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        return

    existing_gross = (
        Decimal(str(payment.amount or 0))
        + Decimal(str(payment.promotion_amount or 0))
    )
    gross_source = data.get('gross_amount')
    if gross_source in (None, ''):
        gross_source = data.get('amount', existing_gross)
    gross_amount = _parse_payment_decimal(gross_source, 'Số tiền trước khuyến mãi')
    gross_amount = gross_amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    if gross_amount < 0:
        raise ValueError('Số tiền trước khuyến mãi không được âm.')

    promotion_mode = str(data.get('promotion_mode') or 'amount').strip().lower()
    if promotion_mode not in dict(Payment.PROMOTION_MODE_CHOICES):
        raise ValueError('Cách tính khuyến mãi không hợp lệ.')

    if promotion_mode == 'percent':
        promotion_percent = _parse_payment_decimal(
            data.get('promotion_percent', 0),
            'Khuyến mãi (%)',
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if promotion_percent < 0 or promotion_percent > 100:
            raise ValueError('Khuyến mãi (%) phải từ 0 đến 100.')
        promotion_amount = (
            gross_amount * promotion_percent / Decimal('100')
        ).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    else:
        promotion_amount = _parse_payment_decimal(
            data.get('promotion_amount', 0),
            'Tiền khuyến mãi',
        ).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        if promotion_amount < 0:
            raise ValueError('Tiền khuyến mãi không được âm.')
        promotion_percent = (
            promotion_amount * Decimal('100') / gross_amount
            if gross_amount else Decimal('0')
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    if promotion_amount > gross_amount:
        raise ValueError('Tiền khuyến mãi không được lớn hơn số tiền trước khuyến mãi.')

    payment.promotion_mode = promotion_mode
    payment.promotion_amount = promotion_amount
    payment.promotion_percent = promotion_percent
    payment.amount = gross_amount - promotion_amount


def _to_positive_int(value, default, minimum=1, maximum=None):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        parsed = default
    if parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return parsed


def _generate_next_payment_code():
    prefix = 'PC-'
    max_number = 0
    for code in Payment.all_objects.filter(code__startswith='PC').values_list('code', flat=True):
        match = re.match(r'^PC-?(\d+)$', code or '', re.IGNORECASE)
        if match:
            max_number = max(max_number, int(match.group(1)))

    next_number = max_number + 1
    while True:
        candidate = f'{prefix}{next_number:03d}'
        if not Payment.all_objects.filter(code=candidate).exists():
            return candidate
        next_number += 1


def _apply_receipt_filters(queryset, request):
    """Áp toàn bộ bộ lọc truy vấn cho danh sách phiếu thu."""
    search = (request.GET.get('search') or '').strip()
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    cash_book_id = request.GET.get('cash_book_id')
    payment_method_option_id = request.GET.get('payment_method_option_id') or request.GET.get('method_id')
    payment_type = request.GET.get('payment_type')
    category_id = request.GET.get('category_id')
    status = request.GET.get('status')
    has_order = request.GET.get('has_order')
    amount_from = _parse_decimal_filter(request.GET.get('amount_from'))
    amount_to = _parse_decimal_filter(request.GET.get('amount_to'))
    receipt_creator = (request.GET.get('receipt_creator') or '').strip()
    order_creator = (request.GET.get('order_creator') or '').strip()

    if date_from:
        queryset = queryset.filter(receipt_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(receipt_date__lte=date_to)

    if cash_book_id == '0':
        queryset = queryset.filter(cash_book_id__isnull=True)
    elif cash_book_id:
        queryset = queryset.filter(cash_book_id=cash_book_id)

    if payment_method_option_id:
        queryset = queryset.filter(payment_method_option_id=payment_method_option_id)

    if payment_type:
        queryset = queryset.filter(
            Q(payment_method_option__legacy_type=payment_type) |
            Q(payment_method_option__isnull=True, payment_method=payment_type)
        )

    if category_id:
        queryset = queryset.filter(category_id=category_id)

    if status not in (None, ''):
        queryset = queryset.filter(status=status)

    if has_order == 'yes':
        queryset = queryset.filter(order_id__isnull=False)
    elif has_order == 'no':
        queryset = queryset.filter(order_id__isnull=True)

    if amount_from is not None:
        queryset = queryset.filter(amount__gte=amount_from)
    if amount_to is not None:
        queryset = queryset.filter(amount__lte=amount_to)

    if receipt_creator:
        queryset = queryset.filter(
            Q(created_by__username__icontains=receipt_creator) |
            Q(created_by__first_name__icontains=receipt_creator) |
            Q(created_by__last_name__icontains=receipt_creator)
        )

    if order_creator:
        queryset = queryset.filter(
            Q(order__creator_name__icontains=order_creator) |
            Q(order__salesperson__icontains=order_creator) |
            Q(order__created_by__username__icontains=order_creator) |
            Q(order__created_by__first_name__icontains=order_creator) |
            Q(order__created_by__last_name__icontains=order_creator)
        )

    if search:
        queryset = queryset.filter(
            Q(code__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(customer__code__icontains=search) |
            Q(order__code__icontains=search) |
            Q(category__name__icontains=search) |
            Q(cash_book__name__icontains=search) |
            Q(description__icontains=search) |
            Q(note__icontains=search) |
            Q(created_by__username__icontains=search) |
            Q(created_by__first_name__icontains=search) |
            Q(created_by__last_name__icontains=search) |
            Q(order__creator_name__icontains=search) |
            Q(order__salesperson__icontains=search)
        )

    return queryset


def _apply_payment_filters(queryset, request):
    """Áp bộ lọc của danh sách phiếu chi trên toàn bộ queryset."""
    search = (request.GET.get('search') or '').strip()
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    cash_book_id = request.GET.get('cash_book_id')
    payment_method_option_id = request.GET.get('payment_method_option_id') or request.GET.get('method_id')
    payment_type = request.GET.get('payment_type')
    category_id = request.GET.get('category_id')
    supplier_id = request.GET.get('supplier_id')
    store_id = request.GET.get('store_id')
    status = request.GET.get('status')
    goods_receipt_state = request.GET.get('goods_receipt_state')
    amount_from = _parse_decimal_filter(request.GET.get('amount_from'))
    amount_to = _parse_decimal_filter(request.GET.get('amount_to'))

    if date_from:
        queryset = queryset.filter(payment_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(payment_date__lte=date_to)

    if cash_book_id == '0':
        queryset = queryset.filter(cash_book_id__isnull=True)
    elif cash_book_id:
        queryset = queryset.filter(cash_book_id=cash_book_id)

    if payment_method_option_id:
        queryset = queryset.filter(payment_method_option_id=payment_method_option_id)

    if payment_type:
        queryset = queryset.filter(
            Q(payment_method_option__legacy_type=payment_type) |
            Q(payment_method_option__isnull=True, payment_method=payment_type)
        )

    if category_id:
        queryset = queryset.filter(category_id=category_id)
    if supplier_id:
        queryset = queryset.filter(supplier_id=supplier_id)

    if store_id:
        queryset = queryset.filter(
            Q(store_id=store_id) |
            Q(store_id__isnull=True, goods_receipt__warehouse__store_id=store_id)
        )

    if status not in (None, ''):
        queryset = queryset.filter(status=status)

    if goods_receipt_state == 'yes':
        queryset = queryset.filter(goods_receipt_id__isnull=False)
    elif goods_receipt_state == 'no':
        queryset = queryset.filter(goods_receipt_id__isnull=True)

    if amount_from is not None:
        queryset = queryset.filter(amount__gte=amount_from)
    if amount_to is not None:
        queryset = queryset.filter(amount__lte=amount_to)

    if search:
        queryset = queryset.filter(
            Q(code__icontains=search) |
            Q(supplier__name__icontains=search) |
            Q(supplier__code__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(customer__code__icontains=search) |
            Q(goods_receipt__code__icontains=search) |
            Q(category__name__icontains=search) |
            Q(cash_book__name__icontains=search) |
            Q(payment_method_option__name__icontains=search) |
            Q(description__icontains=search) |
            Q(note__icontains=search) |
            Q(created_by__username__icontains=search) |
            Q(created_by__first_name__icontains=search) |
            Q(created_by__last_name__icontains=search) |
            Q(approved_by__username__icontains=search) |
            Q(approved_by__first_name__icontains=search) |
            Q(approved_by__last_name__icontains=search)
        )

    return queryset


def _serialize_payment_methods():
    """Chuẩn hóa danh sách phương thức thanh toán để render cho UI."""
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


def _get_receipt_for_user(request, receipt_id, queryset=None):
    """Lấy phiếu thu trong phạm vi user được phép truy cập."""
    if not receipt_id:
        return None
    base_queryset = queryset if queryset is not None else Receipt.objects.all()
    return _filter_receipts_for_user(base_queryset, request).filter(id=receipt_id).first()


def _get_payment_for_user(request, payment_id, queryset=None):
    """Lấy phiếu chi trong phạm vi user được phép truy cập."""
    if not payment_id:
        return None
    base_queryset = queryset if queryset is not None else Payment.objects.all()
    return _filter_payments_for_user(base_queryset, request).filter(id=payment_id).first()


def _get_customer_for_user(request, customer_id):
    if not customer_id:
        return None
    return filter_by_store(Customer.objects.filter(id=customer_id), request).first()


def _normalize_optional_int(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate_receipt_immutable_fields(receipt, data):
    """Phiếu thu đã tạo không được đổi chứng từ gốc/khách/danh mục."""
    immutable_fields = [
        ('code', 'Mã phiếu'),
        ('category_id', 'Danh mục'),
        ('customer_id', 'Khách hàng'),
        ('order_id', 'Đơn hàng'),
    ]

    for field_name, label in immutable_fields:
        if field_name not in data:
            continue
        old_value = getattr(receipt, field_name)
        new_value = data.get(field_name)

        if field_name == 'code':
            if (new_value or '').strip() != (old_value or ''):
                raise ValueError(f'Không được đổi {label.lower()} của phiếu thu đã tạo.')
            continue

        if _normalize_optional_int(new_value) != old_value:
            raise ValueError(
                f'Không được đổi {label.lower()} của phiếu thu đã tạo. '
                'Nếu thu nhầm đơn, hãy chuyển phiếu này sang trạng thái Hủy và tạo phiếu thu mới.'
            )


def _apply_payment_method_defaults(finance_document):
    """Áp cấu hình mặc định từ phương thức thanh toán lên phiếu thu/phiếu chi.

    Hàm này chỉ bổ sung dữ liệu còn thiếu, không ép ghi đè quỹ nếu user đã chọn sẵn.
    """
    if not finance_document.payment_method_option_id:
        return None

    method = PaymentMethodOption.objects.select_related('default_cash_book').filter(
        id=finance_document.payment_method_option_id
    ).first()
    if not method:
        return None

    finance_document.payment_method = method.legacy_type if method.legacy_type in (1, 2) else 2
    if not finance_document.cash_book_id and method.default_cash_book_id:
        finance_document.cash_book_id = method.default_cash_book_id
    return method


def _resolve_receipt_scope(request, receipt):
    """Gắn store và customer cho phiếu thu dựa trên đơn hàng liên kết hoặc store mặc định."""
    linked_order = None
    if receipt.order_id:
        order_id = _normalize_optional_int(receipt.order_id)
        customer_id = _normalize_optional_int(receipt.customer_id)
        linked_order = filter_by_store(Order.objects.filter(id=order_id), request).first()
        if not linked_order:
            raise ValueError('Không tìm thấy đơn hàng trong phạm vi cửa hàng')
        receipt.store_id = linked_order.store_id
        if customer_id and customer_id != linked_order.customer_id:
            raise ValueError('Khách hàng không khớp với đơn hàng đã chọn')
        receipt.order_id = linked_order.id
        receipt.customer_id = linked_order.customer_id
        return linked_order

    if receipt.customer_id:
        customer_id = _normalize_optional_int(receipt.customer_id)
        customer = _get_customer_for_user(request, customer_id)
        if not customer:
            raise ValueError('Khách hàng không thuộc phạm vi cửa hàng của bạn')
        receipt.customer_id = customer.id
        receipt.store_id = customer.store_id
        return linked_order

    if not receipt.store_id:
        store = _get_default_store_for_request(request)
        if store:
            receipt.store = store
    return linked_order


def _resolve_payment_scope(request, payment):
    """Gắn store cho phiếu chi dựa trên phiếu nhập liên kết hoặc store mặc định."""
    linked_receipt = None
    if payment.goods_receipt_id:
        linked_receipt = filter_by_store(
            GoodsReceipt.objects.select_related('warehouse__store'),
            request,
            field_name='warehouse__store',
        ).filter(id=payment.goods_receipt_id).first()
        if not linked_receipt:
            raise ValueError('Không tìm thấy phiếu nhập trong phạm vi cửa hàng')
        payment.store_id = linked_receipt.warehouse.store_id if linked_receipt.warehouse else None
        return linked_receipt

    if not payment.store_id:
        store = _get_default_store_for_request(request)
        if store:
            payment.store = store
    return linked_receipt


def _adjust_cashbook_balance(cash_book_id, amount_delta, validate_non_negative=False):
    """Điều chỉnh số dư quỹ trong transaction hiện tại.

    - `amount_delta > 0`: cộng quỹ
    - `amount_delta < 0`: trừ quỹ
    - `validate_non_negative=True`: chặn quỹ âm trước khi lưu
    """
    if not cash_book_id:
        return None

    cash_book = CashBook.objects.select_for_update().get(id=cash_book_id)
    new_balance = Decimal(str(cash_book.balance or 0)) + Decimal(str(amount_delta or 0))
    if validate_non_negative and new_balance < 0:
        required = abs(Decimal(str(amount_delta or 0)))
        raise ValueError(
            f'Số dư quỹ "{cash_book.name}" không đủ! '
            f'Số dư hiện tại: {int(cash_book.balance):,}đ, cần chi: {int(required):,}đ'
        )
    cash_book.balance = new_balance
    cash_book.save(update_fields=['balance'])
    return cash_book


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
    cashbooks = list(CashBook.objects.filter(is_active=True).values('id', 'name', 'balance'))
    payment_methods = _serialize_payment_methods()
    suppliers = list(Supplier.objects.filter(is_active=True).values('id', 'code', 'name'))
    goods_receipts_qs = GoodsReceipt.objects.select_related('supplier')
    goods_receipts_qs = filter_by_store(goods_receipts_qs, request, field_name='warehouse__store')
    goods_receipts = list(goods_receipts_qs.values(
        'id', 'code', 'supplier__name', 'total_amount', 'status'
    ).order_by('-receipt_date'))
    from system_management.models import Store
    stores = list(
        Store.objects
        .filter(id__in=get_managed_store_ids(request.user))
        .values('id', 'name')
        .order_by('name')
    )
    context = {
        'active_tab': 'payment_tbl',
        'categories': categories,
        'cashbooks': cashbooks,
        'payment_methods': payment_methods,
        'suppliers': suppliers,
        'goods_receipts': goods_receipts,
        'stores': stores,
        'has_multiple_stores': len(stores) > 1,
    }
    return render(request, "finance/payment_list.html", context)


@login_required(login_url="/login/")
def finance_list_tbl(request):
    context = {'active_tab': 'finance_list_tbl'}
    return render(request, "finance/finance_list.html", context)


@login_required(login_url="/login/")
def cashbook_tbl(request):
    cashbooks = list(CashBook.objects.filter(is_active=True).values('id', 'name'))
    context = {
        'active_tab': 'cashbook_tbl',
        'cashbooks': cashbooks,
        # Chỉ người có quyền cấu hình mới được mở form tạo/sửa quỹ.
        # Nhân viên vẫn xem được sổ quỹ nhưng không thấy nút thao tác quản trị.
        'can_manage_cashbooks': can_manage_users(request.user),
    }
    return render(request, "finance/cashbook.html", context)


@login_required(login_url="/login/")
@brand_owner_required
def supplier_debt_tbl(request):
    """Màn hình theo dõi công nợ phải trả theo từng phiếu nhập."""
    from system_management.models import Store

    store_ids = get_managed_store_ids(request.user)
    suppliers = list(
        Supplier.objects
        .filter(goods_receipts__warehouse__store_id__in=store_ids)
        .distinct()
        .values('id', 'code', 'name')
        .order_by('name')
    )
    stores = list(
        Store.objects
        .filter(id__in=store_ids)
        .values('id', 'name')
        .order_by('name')
    )
    return render(request, 'finance/supplier_debt.html', {
        'active_tab': 'supplier_debt_tbl',
        'suppliers': suppliers,
        'stores': stores,
        'has_multiple_stores': len(stores) > 1,
    })


@login_required(login_url="/login/")
@brand_owner_required
@financial_plan_menu_required
def financial_plan_tbl(request):
    """Lập ngân sách, lịch chi nhà cung cấp và theo dõi dự báo dòng tiền."""
    from system_management.models import Store

    store_ids = get_managed_store_ids(request.user)
    stores = list(
        Store.objects.filter(id__in=store_ids)
        .values('id', 'name')
        .order_by('name')
    )
    goods_receipts = list(
        filter_by_store(
            GoodsReceipt.objects.select_related('supplier', 'warehouse').filter(status=1),
            request,
            field_name='warehouse__store',
        )
        .values(
            'id', 'code', 'supplier_id', 'supplier__name', 'total_amount',
            'warehouse__store_id', 'receipt_date',
        )
        .order_by('-receipt_date', '-id')
    )
    return render(request, 'finance/financial_plan.html', {
        'active_tab': 'financial_plan_tbl',
        'stores': stores,
        'has_multiple_stores': len(stores) > 1,
        'categories': list(
            FinanceCategory.objects.filter(is_active=True)
            .values('id', 'name', 'type')
            .order_by('type', 'name')
        ),
        'cashbooks': list(
            CashBook.objects.filter(is_active=True)
            .values('id', 'name', 'balance', 'minimum_balance')
            .order_by('name')
        ),
        'suppliers': list(
            Supplier.objects.filter(is_active=True)
            .values('id', 'code', 'name', 'payment_term_days', 'payment_priority')
            .order_by('name')
        ),
        'goods_receipts': goods_receipts,
    })


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
    """Trả về danh sách phiếu thu sau khi áp quyền theo store và bộ lọc tìm kiếm."""
    receipts = Receipt.objects.select_related(
        'category', 'cash_book', 'customer', 'order', 'order__created_by', 'created_by', 'payment_method_option'
    ).all()
    receipts = _filter_receipts_for_user(receipts, request)
    receipts = _apply_receipt_filters(receipts, request)
    receipts = receipts.order_by('-receipt_date', '-id')
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
        'order_final_amount': float(r.order.final_amount) if r.order else 0,
        'order_paid_amount': float(r.order.paid_amount) if r.order else 0,
        'order_remaining': float(r.order.final_amount - r.order.paid_amount) if r.order else 0,
        'amount': float(r.amount),
        'description': r.description or '',
        'receipt_date': r.receipt_date.strftime('%Y-%m-%d') if r.receipt_date else '',
        'created_at': r.created_at.strftime('%d/%m/%Y %H:%M:%S') if r.created_at else '',
        'status': r.status, 'status_display': r.get_status_display(),
        'payment_method': r.payment_method,
        'payment_method_legacy_type': r.payment_method_option.legacy_type if r.payment_method_option else r.payment_method,
        'payment_method_option_id': r.payment_method_option_id,
        'payment_method_display': r.get_payment_method_label(),
        'note': r.note or '',
        'created_by': _get_user_display_name(r.created_by),
        'receipt_creator': _get_user_display_name(r.created_by),
        'order_creator': (
            r.order.creator_name or
            _get_user_display_name(r.order.created_by)
        ) if r.order else '',
        'salesperson': r.order.salesperson if r.order else '',
    } for r in receipts]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_receipt_summary(request):
    """Tổng hợp nhanh phiếu thu hoàn thành theo quỹ và phương thức thanh toán."""
    receipts = Receipt.objects.select_related('cash_book', 'payment_method_option').filter(status=1)
    receipts = _filter_receipts_for_user(receipts, request)
    receipts = _apply_receipt_filters(receipts, request)

    by_cashbook = {}
    by_method = {}
    total_amount = 0
    receipt_count = 0

    for receipt in receipts:
        amount = float(receipt.amount or 0)
        total_amount += amount
        receipt_count += 1

        cashbook_name = receipt.cash_book.name if receipt.cash_book else 'Chưa gán tài khoản'
        if cashbook_name not in by_cashbook:
            by_cashbook[cashbook_name] = {'amount': 0, 'count': 0}
        by_cashbook[cashbook_name]['amount'] += amount
        by_cashbook[cashbook_name]['count'] += 1

        method_name = receipt.get_payment_method_label()
        if method_name not in by_method:
            by_method[method_name] = {'amount': 0, 'count': 0}
        by_method[method_name]['amount'] += amount
        by_method[method_name]['count'] += 1

    cashbook_rows = [
        {
            'name': name,
            'amount': values['amount'],
            'count': values['count'],
            'percent': round(values['amount'] / total_amount * 100, 2) if total_amount else 0,
        }
        for name, values in sorted(by_cashbook.items(), key=lambda item: item[1]['amount'], reverse=True)
    ]
    method_rows = [
        {
            'name': name,
            'amount': values['amount'],
            'count': values['count'],
            'percent': round(values['amount'] / total_amount * 100, 2) if total_amount else 0,
        }
        for name, values in sorted(by_method.items(), key=lambda item: item[1]['amount'], reverse=True)
    ]
    return JsonResponse({
        'status': 'ok',
        'summary': {
            'total_amount': total_amount,
            'receipt_count': receipt_count,
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
            # Khi sửa phiếu thu, luôn chụp hiệu ứng cũ để hoàn/tái áp sổ quỹ chính xác.
            r = _get_receipt_for_user(request, rid)
            if not r:
                return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phiếu thu'})
            _validate_receipt_immutable_fields(r, data)
            old_effect = capture_receipt_effect(r)
        else:
            r = Receipt()
            r.created_by = request.user

        # 1. Gán dữ liệu cơ bản từ payload.
        if not rid:
            r.code = data.get('code', '')
            r.category_id = data.get('category_id') or None
            r.customer_id = data.get('customer_id') or None
            r.order_id = data.get('order_id') or None
        if rid:
            if 'cash_book_id' in data:
                r.cash_book_id = data.get('cash_book_id') or None
            if 'amount' in data:
                r.amount = data.get('amount', 0) or 0
            if 'description' in data:
                r.description = data.get('description', '')
            if 'receipt_date' in data:
                r.receipt_date = data.get('receipt_date') or r.receipt_date
            if 'status' in data:
                r.status = data.get('status', 0)
            if 'payment_method' in data:
                r.payment_method = data.get('payment_method', 2)
            if 'payment_method_option_id' in data:
                r.payment_method_option_id = data.get('payment_method_option_id') or None
            if 'note' in data:
                r.note = data.get('note', '')
        else:
            r.cash_book_id = data.get('cash_book_id') or None
            r.amount = data.get('amount', 0) or 0
            r.description = data.get('description', '')
            r.receipt_date = data.get('receipt_date')
            r.status = data.get('status', 0)
            r.payment_method = data.get('payment_method', 2)
            r.payment_method_option_id = data.get('payment_method_option_id') or None
            r.note = data.get('note', '')

        # 2. Đồng bộ store/customer theo đơn hàng, hoặc fallback về store mặc định của user.
        _resolve_receipt_scope(request, r)

        # 3. Đồng bộ loại thanh toán chuẩn và quỹ mặc định theo method option đã chọn.
        _apply_payment_method_defaults(r)

        # 4. Ghi phiếu và áp/hoàn tác hiệu ứng quỹ + công nợ đơn hàng trong cùng transaction.
        save_receipt_with_effect(r, old_effect=old_effect)

        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': str(e)})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_receipt(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    return JsonResponse({
        'status': 'error',
        'message': 'Phiếu thu đã tạo không được xóa. Vui lòng sửa trạng thái phiếu thu sang Hủy nếu cần bỏ phiếu.'
    })


# ============ API: PAYMENT ============

def _get_payment_amount_breakdown(payment):
    """Giá trị hiển thị của phiếu chi, có đồng bộ lại các phiếu Nháp cũ."""
    stored_amount = Decimal(str(payment.amount or 0))
    stored_promotion = Decimal(str(payment.promotion_amount or 0))
    promotion_percent = Decimal(str(payment.promotion_percent or 0))
    schedule = getattr(payment, 'supplier_schedule', None)
    if schedule and schedule.status != 2:
        gross_amount = Decimal(str(schedule.gross_amount or 0))
    elif payment.goods_receipt_id:
        gross_amount = Decimal(str(payment.goods_receipt.total_amount or 0))
    else:
        gross_amount = stored_amount + stored_promotion

    promotion_amount = stored_promotion
    actual_amount = stored_amount
    if payment.status == 0 and (payment.goods_receipt_id or schedule):
        if payment.promotion_mode == 'percent':
            promotion_amount = (
                gross_amount * promotion_percent / Decimal('100')
            ).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        promotion_amount = min(max(promotion_amount, Decimal('0')), gross_amount)
        actual_amount = gross_amount - promotion_amount
        if payment.promotion_mode == 'amount':
            promotion_percent = (
                promotion_amount * Decimal('100') / gross_amount
                if gross_amount else Decimal('0')
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    return {
        'gross_amount': gross_amount,
        'promotion_amount': promotion_amount,
        'promotion_percent': promotion_percent,
        'actual_amount': actual_amount,
    }


def _serialize_payment_list(payments):
    data = []
    for p in payments:
        amounts = _get_payment_amount_breakdown(p)
        data.append({
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
        'gross_amount': float(amounts['gross_amount']),
        'promotion_mode': p.promotion_mode,
        'promotion_amount': float(amounts['promotion_amount']),
        'promotion_percent': float(amounts['promotion_percent']),
        'amount': float(amounts['actual_amount']),
        'description': p.description or '',
        'payment_date': p.payment_date.strftime('%Y-%m-%d') if p.payment_date else '',
        'created_at': p.created_at.strftime('%d/%m/%Y %H:%M:%S') if p.created_at else '',
        'status': p.status, 'status_display': p.get_status_display(),
        'payment_method': p.payment_method,
        'payment_method_option_id': p.payment_method_option_id,
        'payment_method_display': p.get_payment_method_label(),
        'note': p.note or '',
        'created_by': _get_user_display_name(p.created_by),
        'approved_by': _get_user_display_name(p.approved_by),
        'approved_at': p.approved_at.strftime('%d/%m/%Y %H:%M:%S') if p.approved_at else '',
        })
    return data


def _get_finance_entry_queryset(request):
    entry_type = (request.GET.get('type') or '').strip()
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    receipt_queryset = _filter_receipts_for_user(Receipt.objects.all(), request).order_by()
    payment_queryset = _filter_payments_for_user(Payment.objects.all(), request).order_by()

    if date_from:
        receipt_queryset = receipt_queryset.filter(receipt_date__gte=date_from)
        payment_queryset = payment_queryset.filter(payment_date__gte=date_from)
    if date_to:
        receipt_queryset = receipt_queryset.filter(receipt_date__lte=date_to)
        payment_queryset = payment_queryset.filter(payment_date__lte=date_to)

    receipt_entries = receipt_queryset.annotate(
        entry_type=Value('thu', output_field=CharField()),
        entry_date=F('receipt_date'),
        category_name=Coalesce(F('category__name'), Value('', output_field=CharField())),
        target_name=Coalesce(F('customer__name'), Value('', output_field=CharField())),
        cash_book_name=Coalesce(F('cash_book__name'), Value('', output_field=CharField())),
        created_at_sort=F('created_at'),
        sort_id=F('id'),
    ).values(
        'entry_type',
        'id',
        'code',
        'category_name',
        'target_name',
        'amount',
        'payment_method',
        'entry_date',
        'cash_book_name',
        'status',
        'created_at',
        'created_at_sort',
        'sort_id',
    )

    payment_entries = payment_queryset.annotate(
        entry_type=Value('chi', output_field=CharField()),
        entry_date=F('payment_date'),
        category_name=Coalesce(F('category__name'), Value('', output_field=CharField())),
        target_name=Coalesce(F('supplier__name'), F('customer__name'), Value('', output_field=CharField())),
        cash_book_name=Coalesce(F('cash_book__name'), Value('', output_field=CharField())),
        created_at_sort=F('created_at'),
        sort_id=F('id'),
    ).values(
        'entry_type',
        'id',
        'code',
        'category_name',
        'target_name',
        'amount',
        'payment_method',
        'entry_date',
        'cash_book_name',
        'status',
        'created_at',
        'created_at_sort',
        'sort_id',
    )

    if entry_type == 'thu':
        return receipt_entries.order_by('-entry_date', '-created_at_sort', '-sort_id')
    if entry_type == 'chi':
        return payment_entries.order_by('-entry_date', '-created_at_sort', '-sort_id')
    return receipt_entries.union(payment_entries, all=True).order_by('-entry_date', '-created_at_sort', '-sort_id')


def _serialize_finance_entries(rows):
    status_labels = dict(Receipt.STATUS_CHOICES)
    data = []
    for row in rows:
        entry_type = row.get('entry_type') or ''
        entry_date = row.get('entry_date')
        created_at = row.get('created_at')
        data.append({
            'id': row.get('id'),
            'entry_type': entry_type,
            'type': 'Thu' if entry_type == 'thu' else 'Chi',
            'type_class': 'success' if entry_type == 'thu' else 'danger',
            'code': row.get('code') or '',
            'category': row.get('category_name') or '',
            'target': row.get('target_name') or '',
            'amount': float(row.get('amount') or 0),
            'payment_method': row.get('payment_method'),
            'date': entry_date.strftime('%Y-%m-%d') if entry_date else '',
            'created_at': created_at.strftime('%d/%m/%Y %H:%M:%S') if created_at else '',
            'cash_book': row.get('cash_book_name') or '',
            'status': row.get('status'),
            'status_display': status_labels.get(row.get('status'), ''),
        })
    return data


def _get_supplier_debt_queryset(request):
    """Tính phải trả theo phiếu nhập trong phạm vi cửa hàng được phép xem.

    Phải trả = Phiếu nhập hoàn thành - Phiếu trả nhập hoàn thành.
    Còn nợ = max(Phải trả - Phiếu chi hoàn thành có liên kết, 0).
    """
    money_field = DecimalField(max_digits=18, decimal_places=0)
    zero_money = Value(Decimal('0'), output_field=money_field)

    completed_cash_payment_total = (
        Payment.objects
        .filter(goods_receipt_id=OuterRef('pk'), status=1)
        .order_by()
        .values('goods_receipt_id')
        .annotate(total=Sum('amount'))
        .values('total')[:1]
    )
    completed_promotion_total = (
        Payment.objects
        .filter(goods_receipt_id=OuterRef('pk'), status=1)
        .order_by()
        .values('goods_receipt_id')
        .annotate(total=Sum('promotion_amount'))
        .values('total')[:1]
    )
    completed_return_total = (
        PurchaseReturn.objects
        .filter(goods_receipt_id=OuterRef('pk'), status=1)
        .order_by()
        .values('goods_receipt_id')
        .annotate(total=Sum('total_amount'))
        .values('total')[:1]
    )

    receipts = filter_by_store(
        GoodsReceipt.objects.filter(status=1).select_related(
            'supplier', 'warehouse', 'warehouse__store', 'purchase_order'
        ),
        request,
        field_name='warehouse__store',
    )
    total_all_count = receipts.count()
    receipts = receipts.annotate(
        cash_paid_amount=Coalesce(
            Subquery(completed_cash_payment_total, output_field=money_field),
            zero_money,
            output_field=money_field,
        ),
        promotion_amount=Coalesce(
            Subquery(completed_promotion_total, output_field=money_field),
            zero_money,
            output_field=money_field,
        ),
        returned_amount=Coalesce(
            Subquery(completed_return_total, output_field=money_field),
            zero_money,
            output_field=money_field,
        ),
    ).annotate(
        paid_amount=ExpressionWrapper(
            F('cash_paid_amount') + F('promotion_amount'),
            output_field=money_field,
        ),
        payable_amount=ExpressionWrapper(
            F('total_amount') - F('returned_amount'),
            output_field=money_field,
        ),
    ).annotate(
        remaining_raw=ExpressionWrapper(
            F('payable_amount') - F('paid_amount'),
            output_field=money_field,
        ),
    ).annotate(
        debt_amount=Case(
            When(remaining_raw__gt=0, then=F('remaining_raw')),
            default=zero_money,
            output_field=money_field,
        ),
        overpaid_amount=Case(
            When(remaining_raw__lt=0, then=ExpressionWrapper(-F('remaining_raw'), output_field=money_field)),
            default=zero_money,
            output_field=money_field,
        ),
    )
    return receipts, total_all_count


def _apply_supplier_debt_filters(queryset, request):
    search = (request.GET.get('q') or '').strip()
    supplier_id = (request.GET.get('supplier_id') or '').strip()
    store_id = (request.GET.get('store_id') or '').strip()
    payment_state = (request.GET.get('payment_state') or 'outstanding').strip()
    date_from = parse_date((request.GET.get('date_from') or '').strip())
    date_to = parse_date((request.GET.get('date_to') or '').strip())

    if search:
        queryset = queryset.filter(
            Q(code__icontains=search)
            | Q(purchase_order__code__icontains=search)
            | Q(supplier__code__icontains=search)
            | Q(supplier__name__icontains=search)
            | Q(warehouse__name__icontains=search)
        )
    if supplier_id:
        queryset = queryset.filter(supplier_id=int(supplier_id)) if supplier_id.isdigit() else queryset.none()
    if store_id:
        allowed_store_ids = set(get_managed_store_ids(request.user))
        if store_id.isdigit() and int(store_id) in allowed_store_ids:
            queryset = queryset.filter(warehouse__store_id=int(store_id))
        else:
            queryset = queryset.none()
    if date_from:
        queryset = queryset.filter(receipt_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(receipt_date__lte=date_to)

    if payment_state == 'unpaid':
        queryset = queryset.filter(paid_amount__lte=0, debt_amount__gt=0)
    elif payment_state == 'partial':
        queryset = queryset.filter(paid_amount__gt=0, debt_amount__gt=0)
    elif payment_state == 'settled':
        queryset = queryset.filter(debt_amount__lte=0)
    elif payment_state != 'all':
        payment_state = 'outstanding'
        queryset = queryset.filter(debt_amount__gt=0)

    sort = (request.GET.get('sort') or 'date_desc').strip()
    ordering = {
        'date_asc': ('receipt_date', 'id'),
        'debt_desc': ('-debt_amount', '-receipt_date', '-id'),
        'debt_asc': ('debt_amount', '-receipt_date', '-id'),
        'date_desc': ('-receipt_date', '-id'),
    }.get(sort, ('-receipt_date', '-id'))
    return queryset.order_by(*ordering), payment_state


def _serialize_supplier_debts(receipts):
    data = []
    for receipt in receipts:
        payable_amount = Decimal(str(receipt.payable_amount or 0))
        paid_amount = Decimal(str(receipt.paid_amount or 0))
        debt_amount = Decimal(str(receipt.debt_amount or 0))
        if debt_amount > 0 and paid_amount <= 0:
            payment_state = 'unpaid'
            payment_state_display = 'Chưa thanh toán'
        elif debt_amount > 0:
            payment_state = 'partial'
            payment_state_display = 'Thanh toán một phần'
        else:
            payment_state = 'settled'
            payment_state_display = 'Đã tất toán'

        payments = getattr(receipt, 'completed_debt_payments', [])
        data.append({
            'id': receipt.id,
            'code': receipt.code,
            'purchase_order': receipt.purchase_order.code if receipt.purchase_order else '',
            'receipt_date': receipt.receipt_date.strftime('%Y-%m-%d') if receipt.receipt_date else '',
            'supplier_id': receipt.supplier_id,
            'supplier_code': receipt.supplier.code if receipt.supplier else '',
            'supplier': receipt.supplier.name if receipt.supplier else '',
            'warehouse': receipt.warehouse.name if receipt.warehouse else '',
            'store_id': receipt.warehouse.store_id if receipt.warehouse else None,
            'store': receipt.warehouse.store.name if receipt.warehouse and receipt.warehouse.store else '',
            'original_amount': float(receipt.total_amount or 0),
            'returned_amount': float(receipt.returned_amount or 0),
            'payable_amount': float(payable_amount),
            'cash_paid_amount': float(receipt.cash_paid_amount or 0),
            'promotion_amount': float(receipt.promotion_amount or 0),
            'paid_amount': float(paid_amount),
            'debt_amount': float(debt_amount),
            'overpaid_amount': float(receipt.overpaid_amount or 0),
            'payment_state': payment_state,
            'payment_state_display': payment_state_display,
            'payment_codes': [payment.code for payment in payments],
            'payment_count': len(payments),
        })
    return data


@login_required(login_url="/login/")
@brand_owner_required
def api_get_supplier_debts(request):
    receipts, total_all_count = _get_supplier_debt_queryset(request)
    overall_debt_amount = sum(
        (
            Decimal(str(value or 0))
            for value in receipts.filter(debt_amount__gt=0).values_list('debt_amount', flat=True).iterator()
        ),
        Decimal('0'),
    )
    receipts, payment_state = _apply_supplier_debt_filters(receipts, request)

    totals = {
        'original_amount': Decimal('0'),
        'returned_amount': Decimal('0'),
        'payable_amount': Decimal('0'),
        'cash_paid_amount': Decimal('0'),
        'promotion_amount': Decimal('0'),
        'paid_amount': Decimal('0'),
        'debt_amount': Decimal('0'),
        'overpaid_amount': Decimal('0'),
    }
    debt_document_count = 0
    for row in receipts.values(
        'total_amount', 'returned_amount', 'payable_amount',
        'cash_paid_amount', 'promotion_amount', 'paid_amount',
        'debt_amount', 'overpaid_amount',
    ).iterator():
        totals['original_amount'] += Decimal(str(row['total_amount'] or 0))
        for key in (
            'returned_amount', 'payable_amount', 'cash_paid_amount',
            'promotion_amount', 'paid_amount', 'debt_amount', 'overpaid_amount',
        ):
            totals[key] += Decimal(str(row[key] or 0))
        if Decimal(str(row['debt_amount'] or 0)) > 0:
            debt_document_count += 1
    page = _to_positive_int(request.GET.get('page'), default=1, minimum=1)
    page_size = _to_positive_int(request.GET.get('page_size'), default=25, minimum=10, maximum=200)
    paginator = Paginator(receipts, page_size)
    page_obj = paginator.get_page(page)
    page_receipts = page_obj.object_list.prefetch_related(Prefetch(
        'payments',
        queryset=Payment.objects.filter(status=1).order_by('payment_date', 'id'),
        to_attr='completed_debt_payments',
    ))
    data = _serialize_supplier_debts(page_receipts)

    return JsonResponse({
        'data': data,
        'totals': {
            key: float(value or 0)
            for key, value in totals.items()
        } | {
            'debt_document_count': debt_document_count,
            'overall_debt_amount': float(overall_debt_amount),
        },
        'filters': {'payment_state': payment_state},
        'meta': {
            'page': page_obj.number,
            'page_size': page_size,
            'page_count': len(data),
            'total_pages': paginator.num_pages,
            'total_filtered_count': paginator.count,
            'total_all_count': total_all_count,
            'has_previous': page_obj.has_previous(),
            'has_next': page_obj.has_next(),
            'start_index': page_obj.start_index() if paginator.count else 0,
            'end_index': page_obj.end_index() if paginator.count else 0,
        },
    })


@login_required(login_url="/login/")
def api_get_finance_entries(request):
    page = _to_positive_int(request.GET.get('page'), default=1, minimum=1)
    page_size = _to_positive_int(request.GET.get('page_size'), default=25, minimum=10, maximum=200)
    entries = _get_finance_entry_queryset(request)
    paginator = Paginator(entries, page_size)
    page_obj = paginator.get_page(page)
    data = _serialize_finance_entries(list(page_obj.object_list))

    return JsonResponse({
        'data': data,
        'meta': {
            'page': page_obj.number,
            'page_size': page_size,
            'page_count': len(data),
            'total_pages': paginator.num_pages,
            'total_filtered_count': paginator.count,
            'total_all_count': paginator.count,
            'has_previous': page_obj.has_previous(),
            'has_next': page_obj.has_next(),
            'start_index': page_obj.start_index() if paginator.count else 0,
            'end_index': page_obj.end_index() if paginator.count else 0,
        }
    })


@login_required(login_url="/login/")
def api_get_payments(request):
    """Trả về danh sách phiếu chi sau khi áp quyền và bộ lọc."""
    should_paginate = request.GET.get('page') is not None or request.GET.get('page_size') is not None
    payment_date_order = request.GET.get('payment_date_order')
    ordering = (
        ('payment_date', 'created_at', 'id')
        if payment_date_order == 'asc'
        else ('-payment_date', '-created_at', '-id')
    )
    payments = (
        Payment.objects
        .select_related(
            'category',
            'cash_book',
            'supplier',
            'customer',
            'goods_receipt',
            'goods_receipt__warehouse',
            'payment_method_option',
            'created_by',
            'approved_by',
            'supplier_schedule',
        )
        .order_by(*ordering)
    )
    payments = _filter_payments_for_user(payments, request)
    total_all_count = payments.count()
    payments = _apply_payment_filters(payments, request)

    if not should_paginate:
        return JsonResponse({
            'data': _serialize_payment_list(payments),
            'next_code': _generate_next_payment_code(),
        })

    page = _to_positive_int(request.GET.get('page'), default=1, minimum=1)
    page_size = _to_positive_int(request.GET.get('page_size'), default=25, minimum=10, maximum=200)
    paginator = Paginator(payments, page_size)
    page_obj = paginator.get_page(page)
    data = _serialize_payment_list(page_obj.object_list)
    next_code = _generate_next_payment_code()

    return JsonResponse({
        'data': data,
        'next_code': next_code,
        'meta': {
            'page': page_obj.number,
            'page_size': page_size,
            'page_count': len(data),
            'total_pages': paginator.num_pages,
            'total_filtered_count': paginator.count,
            'total_all_count': total_all_count,
            'has_previous': page_obj.has_previous(),
            'has_next': page_obj.has_next(),
            'start_index': page_obj.start_index() if paginator.count else 0,
            'end_index': page_obj.end_index() if paginator.count else 0,
            'next_code': next_code,
        }
    })


@login_required(login_url="/login/")
def api_save_payment(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            # 1. Nạp phiếu cũ nếu là cập nhật để biết cần hoàn lại bao nhiêu vào quỹ cũ.
            pid = data.get('id')
            old_amount = Decimal('0')
            old_cash_book_id = None
            old_status = None
            if pid:
                current_payment = _get_payment_for_user(request, pid)
                if not current_payment:
                    return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phiếu chi'})
                # Kiểm quyền bằng query có join trước, sau đó khóa lại chính bản ghi bằng query đơn giản.
                p = Payment.objects.select_for_update().get(id=current_payment.id)
                old_amount = Decimal(str(p.amount or 0))
                old_cash_book_id = p.cash_book_id
                old_status = p.status
            else:
                p = Payment()
                p.created_by = request.user

            # 2. Gán dữ liệu cơ bản từ payload.
            requested_code = (data.get('code', '') or '').strip()
            auto_code = not requested_code and not p.code
            p.code = requested_code or (p.code or _generate_next_payment_code())
            p.category_id = data.get('category_id') or None
            p.cash_book_id = data.get('cash_book_id') or None
            p.supplier_id = data.get('supplier_id') or None
            p.goods_receipt_id = data.get('goods_receipt_id') or None
            p.description = data.get('description', '')
            p.payment_date = data.get('payment_date')
            p.status = data.get('status', 0)
            p.payment_method = data.get('payment_method', 2)
            p.payment_method_option_id = data.get('payment_method_option_id') or None
            p.note = data.get('note', '')

            # 3. Đồng bộ store theo phiếu nhập liên kết hoặc store mặc định của user.
            linked_receipt = _resolve_payment_scope(request, p)

            # Phiếu chi gắn phiếu nhập luôn lấy tiền trước KM từ tổng phiếu
            # nhập (số lượng × đơn giá). Không nhận số tiền gốc do trình duyệt
            # gửi lên, để kế toán chỉ cần nhập phần KM.
            promotion_data = data
            linked_schedule = (
                SupplierPaymentSchedule.objects
                .select_related('goods_receipt', 'goods_receipt__warehouse')
                .select_for_update(of=('self',))
                .filter(payment_id=p.id)
                .first()
                if p.id else None
            )
            if linked_schedule and linked_schedule.status != 2:
                # Phiếu nhập/NCC là nguồn của lịch và không được đổi khi kế
                # toán duyệt phiếu chi. Ngày chi, quỹ và KM vẫn được phép chốt
                # lại theo tình hình thanh toán thực tế.
                p.goods_receipt_id = linked_schedule.goods_receipt_id
                p.supplier_id = linked_schedule.supplier_id
                p.store_id = linked_schedule.store_id
                linked_receipt = linked_schedule.goods_receipt
                promotion_data = dict(data)
                promotion_data['gross_amount'] = linked_schedule.gross_amount
                if not any(key in data for key in (
                    'promotion_mode', 'promotion_amount', 'promotion_percent',
                )):
                    promotion_data['promotion_mode'] = linked_schedule.promotion_mode
                    promotion_data['promotion_amount'] = linked_schedule.promotion_amount
                    promotion_data['promotion_percent'] = linked_schedule.promotion_percent
            elif linked_receipt:
                promotion_data = dict(data)
                promotion_data['gross_amount'] = linked_receipt.total_amount
                if not any(key in data for key in (
                    'promotion_mode', 'promotion_amount', 'promotion_percent',
                )):
                    promotion_data['promotion_mode'] = p.promotion_mode or 'amount'
                    promotion_data['promotion_amount'] = p.promotion_amount or 0
                    promotion_data['promotion_percent'] = p.promotion_percent or 0
            _apply_payment_promotion(p, promotion_data)

            # 4. Bổ sung cấu hình phương thức thanh toán nếu user chọn method option.
            _apply_payment_method_defaults(p)

            new_amount = Decimal(str(p.amount or 0))
            new_status = int(p.status)

            # Người duyệt luôn là tài khoản đang đăng nhập tại đúng lần chuyển
            # từ Nháp/Hủy sang Hoàn thành. Không ghi đè lịch sử khi chỉ sửa lại
            # một phiếu vốn đã Hoàn thành.
            if new_status == 1 and old_status != 1:
                p.approved_by = request.user
                p.approved_at = timezone.now()
            elif new_status != 1:
                p.approved_by = None
                p.approved_at = None

            # 5. Hoàn lại quỹ cũ trước khi áp trạng thái/quỹ mới.
            if pid and old_status == 1 and old_cash_book_id:
                _adjust_cashbook_balance(old_cash_book_id, old_amount)

            # 6. Nếu phiếu mới ở trạng thái hoàn thành thì kiểm tra đủ quỹ rồi mới trừ.
            if new_status == 1 and p.cash_book_id:
                _adjust_cashbook_balance(
                    p.cash_book_id,
                    -new_amount,
                    validate_non_negative=True,
                )

            save_with_generated_code(p, _generate_next_payment_code, auto_code)

            if linked_schedule:
                linked_schedule.status = 1 if new_status == 1 else (2 if new_status == 2 else 0)
                linked_schedule.promotion_mode = p.promotion_mode
                linked_schedule.promotion_amount = p.promotion_amount
                linked_schedule.promotion_percent = p.promotion_percent
                linked_schedule.amount = p.amount
                linked_schedule.save(update_fields=[
                    'status', 'promotion_mode', 'promotion_amount',
                    'promotion_percent', 'amount', 'updated_at',
                ])
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': str(e)})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_payment(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            current_payment = _get_payment_for_user(request, data.get('id'))
            if not current_payment:
                return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phiếu chi'})
            payment = Payment.objects.select_for_update().get(id=current_payment.id)
            linked_schedule = SupplierPaymentSchedule.objects.select_for_update().filter(
                payment_id=payment.id
            ).first()

            # Nếu phiếu chi đã hoàn thành thì xóa phải hoàn lại tiền vào đúng quỹ trước.
            if payment.status == 1 and payment.cash_book_id:
                _adjust_cashbook_balance(payment.cash_book_id, Decimal(str(payment.amount or 0)))

            if linked_schedule:
                linked_schedule.status = 2
                linked_schedule.note = (
                    f'{linked_schedule.note or ""}\n[HỦY] Phiếu chi {payment.code} đã bị xóa.'
                ).strip()
                linked_schedule.save(update_fields=['status', 'note', 'updated_at'])
            payment.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: FINANCE CATEGORY ============

@login_required(login_url="/login/")
def api_get_finance_categories(request):
    type_display_map = dict(FinanceCategory.TYPE_CHOICES)
    cats = list(FinanceCategory.objects.values(
        'id',
        'name',
        'type',
        'description',
        'is_active',
    ))
    data = [{
        'id': row['id'],
        'name': row['name'],
        'type': row['type'],
        'type_display': type_display_map.get(row['type'], ''),
        'description': row['description'] or '',
        'is_active': row['is_active'],
    } for row in cats]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_finance_category(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    if not can_manage_users(request.user):
        return _forbid_json('Bạn không có quyền cấu hình danh mục thu chi')
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
    books = list(CashBook.objects.values(
        'id', 'name', 'description', 'balance', 'minimum_balance', 'is_active',
    ))
    data = [{
        'id': row['id'],
        'name': row['name'],
        'description': row['description'] or '',
        'balance': float(row['balance']),
        'minimum_balance': float(row['minimum_balance']),
        'is_active': row['is_active'],
    } for row in books]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_cashbook(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    if not can_manage_users(request.user):
        return _forbid_json('Bạn không có quyền cấu hình sổ quỹ')
    try:
        data = json.loads(request.body)
        bid = data.get('id')
        if bid:
            b = CashBook.objects.get(id=bid)
        else:
            b = CashBook()
        b.name = data.get('name', '')
        b.description = data.get('description', '')
        minimum_balance = _parse_payment_decimal(
            data.get('minimum_balance', b.minimum_balance or 0),
            'Số dư tối thiểu',
        )
        if minimum_balance < 0:
            raise ValueError('Số dư tối thiểu không được âm.')
        b.minimum_balance = minimum_balance.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        b.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_get_payment_methods(request):
    legacy_type_map = dict(PaymentMethodOption.LEGACY_CHOICES)
    methods = list(PaymentMethodOption.objects.values(
        'id',
        'code',
        'name',
        'description',
        'legacy_type',
        'default_cash_book_id',
        'sort_order',
        'is_active',
        default_cash_book_name=F('default_cash_book__name'),
    ))
    data = [{
        'id': row['id'],
        'code': row['code'],
        'name': row['name'],
        'description': row['description'] or '',
        'legacy_type': row['legacy_type'],
        'legacy_type_display': legacy_type_map.get(row['legacy_type'], ''),
        'default_cash_book_id': row['default_cash_book_id'],
        'default_cash_book': row['default_cash_book_name'] or '',
        'sort_order': row['sort_order'],
        'is_active': row['is_active'],
    } for row in methods]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_payment_method(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    if not can_manage_users(request.user):
        return _forbid_json('Bạn không có quyền cấu hình phương thức thanh toán')
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
        duplicate = PaymentMethodOption.objects.filter(code__iexact=method.code)
        if mid:
            duplicate = duplicate.exclude(id=mid)
        if duplicate.exists():
            return JsonResponse({'status': 'error', 'message': f'Mã phương thức "{method.code}" đã tồn tại'})
        method.save()
        return JsonResponse({
            'status': 'ok',
            'message': 'Lưu phương thức thành công',
            'method': {
                'id': method.id,
                'code': method.code,
                'name': method.name,
                'description': method.description or '',
                'legacy_type': method.legacy_type,
                'legacy_type_display': method.get_legacy_type_display(),
                'default_cash_book_id': method.default_cash_book_id,
                'default_cash_book': method.default_cash_book.name if method.default_cash_book else '',
                'sort_order': method.sort_order,
                'is_active': method.is_active,
            }
        })
    except IntegrityError:
        return JsonResponse({'status': 'error', 'message': 'Mã phương thức đã tồn tại'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_reorder_payment_methods(request):
    """Lưu thứ tự hiển thị của nhiều phương thức thanh toán trong một lần."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    if not can_manage_users(request.user):
        return _forbid_json('Bạn không có quyền cấu hình phương thức thanh toán')

    try:
        data = json.loads(request.body or '{}')
        raw_items = data.get('items')
        if not isinstance(raw_items, list):
            return JsonResponse({'status': 'error', 'message': 'Dữ liệu thứ tự không hợp lệ'})
        if len(raw_items) > 500:
            return JsonResponse({'status': 'error', 'message': 'Số lượng phương thức vượt quá giới hạn'})

        updates = {}
        for item in raw_items:
            if not isinstance(item, dict):
                return JsonResponse({'status': 'error', 'message': 'Dữ liệu thứ tự không hợp lệ'})
            method_id_raw = item.get('id')
            sort_order_raw = item.get('sort_order')
            method_id_text = str(method_id_raw).strip() if not isinstance(method_id_raw, bool) else ''
            sort_order_text = str(sort_order_raw).strip() if not isinstance(sort_order_raw, bool) else ''
            if not method_id_text.isdigit() or not sort_order_text.isdigit():
                return JsonResponse({'status': 'error', 'message': 'Thứ tự phải là số nguyên không âm'})
            method_id = int(method_id_text)
            sort_order = int(sort_order_text)
            if method_id <= 0:
                return JsonResponse({'status': 'error', 'message': 'Thứ tự phải là số nguyên không âm'})
            updates[method_id] = sort_order

        if not updates:
            return JsonResponse({'status': 'ok', 'message': 'Không có thay đổi', 'updated': 0})

        with transaction.atomic():
            methods = list(PaymentMethodOption.objects.filter(id__in=updates.keys()))
            found_ids = {method.id for method in methods}
            missing_ids = set(updates) - found_ids
            if missing_ids:
                return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phương thức thanh toán'})
            updated_at = timezone.now()
            for method in methods:
                method.sort_order = updates[method.id]
                method.updated_at = updated_at
            PaymentMethodOption.objects.bulk_update(methods, ['sort_order', 'updated_at'])

        return JsonResponse({
            'status': 'ok',
            'message': f'Đã cập nhật {len(methods)} phương thức',
            'updated': len(methods),
        })
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'status': 'error', 'message': 'Dữ liệu thứ tự không hợp lệ'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_payment_method(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    if not can_manage_users(request.user):
        return _forbid_json('Bạn không có quyền cấu hình phương thức thanh toán')
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
    """Xuất chi tiết và các bảng tổng hợp phiếu thu ra Excel."""
    from core.excel_export import excel_response
    from datetime import datetime

    receipts = Receipt.objects.select_related(
        'category', 'cash_book', 'customer', 'order', 'order__created_by', 'created_by', 'payment_method_option'
    )
    receipts = _filter_receipts_for_user(receipts, request)
    receipts = _apply_receipt_filters(receipts, request)
    receipts = list(receipts)
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    columns = [
        {'key': 'stt', 'label': 'STT', 'width': 6},
        {'key': 'code', 'label': 'Mã phiếu', 'width': 14},
        {'key': 'category', 'label': 'Danh mục', 'width': 16},
        {'key': 'customer', 'label': 'Khách hàng', 'width': 22},
        {'key': 'order', 'label': 'Đơn hàng', 'width': 14},
        {'key': 'order_creator', 'label': 'Người tạo đơn', 'width': 18},
        {'key': 'amount', 'label': 'Số tiền', 'width': 16},
        {'key': 'method', 'label': 'Hình thức TT', 'width': 16},
        {'key': 'date', 'label': 'Ngày thu', 'width': 13},
        {'key': 'cashbook', 'label': 'Quỹ/Tài khoản', 'width': 20},
        {'key': 'creator', 'label': 'Người tạo phiếu', 'width': 16},
        {'key': 'description', 'label': 'Diễn giải', 'width': 30},
        {'key': 'note', 'label': 'Ghi chú', 'width': 30},
    ]

    rows = []
    total = Decimal('0')
    for i, r in enumerate(receipts, 1):
        total += r.amount or Decimal('0')
        rows.append({
            'stt': i,
            'code': r.code,
            'category': r.category.name if r.category else '',
            'customer': r.customer.name if r.customer else '',
            'order': r.order.code if r.order else '',
            'order_creator': (r.order.creator_name or _get_user_display_name(r.order.created_by)) if r.order else '',
            'amount': r.amount or Decimal('0'),
            'method': r.get_payment_method_label(),
            'date': r.receipt_date,
            'cashbook': r.cash_book.name if r.cash_book else '',
            'creator': _get_user_display_name(r.created_by),
            'description': r.description or '',
            'note': r.note or '',
        })

    period = ''
    if date_from and date_to:
        period = f' ({date_from} → {date_to})'
    elif date_from:
        period = f' (từ {date_from})'
    elif date_to:
        period = f' (đến {date_to})'

    export_subtitle = f'Xuất ngày {datetime.now().strftime("%d/%m/%Y %H:%M")}{period}'

    # Dashboard mặc định chỉ tính tiền đã hoàn thành. Khi người dùng chủ động
    # chọn tab Nháp/Đã hủy, bảng tổng hợp trong file giữ đúng phạm vi tab đó.
    status_filter = request.GET.get('status')
    if status_filter in ('0', '2'):
        summary_receipts = receipts
        summary_scope = 'Phiếu nháp' if status_filter == '0' else 'Phiếu đã hủy'
    else:
        summary_receipts = [receipt for receipt in receipts if receipt.status == 1]
        summary_scope = 'Phiếu hoàn thành'

    cashbook_totals = {}
    method_totals = {}
    summary_total = Decimal('0')
    for receipt in summary_receipts:
        amount = receipt.amount or Decimal('0')
        summary_total += amount

        cashbook_name = receipt.cash_book.name if receipt.cash_book else 'Chưa gán tài khoản'
        cashbook_row = cashbook_totals.setdefault(
            cashbook_name,
            {'name': cashbook_name, 'count': 0, 'amount': Decimal('0')},
        )
        cashbook_row['count'] += 1
        cashbook_row['amount'] += amount

        method_name = receipt.get_payment_method_label()
        method_row = method_totals.setdefault(
            method_name,
            {'name': method_name, 'count': 0, 'amount': Decimal('0')},
        )
        method_row['count'] += 1
        method_row['amount'] += amount

    def build_summary_rows(grouped_values):
        grouped_rows = sorted(
            grouped_values.values(),
            key=lambda item: (-item['amount'], item['name']),
        )
        return [{
            'stt': index,
            'name': item['name'],
            'count': item['count'],
            'amount': item['amount'],
            'percent': round(float(item['amount'] / summary_total * 100), 2) if summary_total else 0,
        } for index, item in enumerate(grouped_rows, 1)]

    cashbook_rows = build_summary_rows(cashbook_totals)
    method_rows = build_summary_rows(method_totals)
    summary_columns = [
        {'key': 'stt', 'label': 'STT', 'width': 8},
        {'key': 'name', 'label': 'Tài khoản', 'width': 32},
        {'key': 'count', 'label': 'Số phiếu', 'width': 14},
        {'key': 'amount', 'label': 'Tổng tiền', 'width': 20},
        {'key': 'percent', 'label': 'Tỷ trọng (%)', 'width': 16},
    ]
    method_columns = [dict(column) for column in summary_columns]
    method_columns[1]['label'] = 'Hình thức nhận'
    summary_total_row = {
        'name': 'TỔNG CỘNG',
        'count': len(summary_receipts),
        'amount': summary_total,
        'percent': 100 if summary_total else 0,
    }

    return excel_response(
        title='DANH SÁCH PHIẾU THU',
        subtitle=export_subtitle,
        columns=columns,
        rows=rows,
        filename=f'Phieu_thu_{datetime.now().strftime("%Y%m%d")}',
        money_cols=['amount'],
        total_row={'stt': '', 'code': 'TỔNG CỘNG', 'amount': total},
        extra_sheets=[
            {
                'sheet_name': 'Tiền về từng tài khoản',
                'title': 'TIỀN VỀ TỪNG TÀI KHOẢN',
                'subtitle': f'{export_subtitle} · {summary_scope}',
                'columns': summary_columns,
                'rows': cashbook_rows,
                'money_cols': ['amount'],
                'total_row': summary_total_row,
            },
            {
                'sheet_name': 'Theo hình thức nhận',
                'title': 'TIỀN VỀ THEO HÌNH THỨC NHẬN',
                'subtitle': f'{export_subtitle} · {summary_scope}',
                'columns': method_columns,
                'rows': method_rows,
                'money_cols': ['amount'],
                'total_row': summary_total_row,
            },
        ],
    )


@login_required(login_url="/login/")
def export_payments_excel(request):
    """Xuất danh sách phiếu chi ra Excel"""
    from core.excel_export import excel_response
    from datetime import datetime

    payments = Payment.objects.select_related(
        'category', 'cash_book', 'supplier', 'customer', 'goods_receipt',
        'goods_receipt__warehouse', 'payment_method_option', 'created_by', 'approved_by',
        'supplier_schedule',
    )
    payments = _filter_payments_for_user(payments, request)
    payments = _apply_payment_filters(payments, request)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    columns = [
        {'key': 'stt', 'label': 'STT', 'width': 6},
        {'key': 'code', 'label': 'Mã phiếu', 'width': 14},
        {'key': 'category', 'label': 'Danh mục', 'width': 16},
        {'key': 'target', 'label': 'Người nhận', 'width': 22},
        {'key': 'goods_receipt', 'label': 'Phiếu nhập', 'width': 16},
        {'key': 'gross_amount', 'label': 'Tiền trước KM', 'width': 16},
        {'key': 'promotion', 'label': 'Khuyến mãi', 'width': 16},
        {'key': 'amount', 'label': 'Thực chi', 'width': 16},
        {'key': 'method', 'label': 'Hình thức TT', 'width': 16},
        {'key': 'date', 'label': 'Ngày chi', 'width': 13},
        {'key': 'cashbook', 'label': 'Quỹ/Tài khoản', 'width': 20},
        {'key': 'status', 'label': 'Trạng thái', 'width': 14},
        {'key': 'creator', 'label': 'Người tạo', 'width': 16},
        {'key': 'approver', 'label': 'Người duyệt', 'width': 16},
        {'key': 'approved_at', 'label': 'Thời gian duyệt', 'width': 18},
        {'key': 'description', 'label': 'Diễn giải', 'width': 30},
        {'key': 'note', 'label': 'Ghi chú', 'width': 30},
    ]

    rows = []
    total_gross = 0
    total_promotion = 0
    total = 0
    for i, p in enumerate(payments, 1):
        amounts = _get_payment_amount_breakdown(p)
        gross_amount = float(amounts['gross_amount'])
        promotion_amount = float(amounts['promotion_amount'])
        actual_amount = float(amounts['actual_amount'])
        total_gross += gross_amount
        total_promotion += promotion_amount
        total += actual_amount
        target = p.supplier.name if p.supplier else (p.customer.name if p.customer else '')
        rows.append({
            'stt': i,
            'code': p.code,
            'category': p.category.name if p.category else '',
            'target': target,
            'goods_receipt': p.goods_receipt.code if p.goods_receipt else '',
            'gross_amount': gross_amount,
            'promotion': promotion_amount,
            'amount': actual_amount,
            'method': p.get_payment_method_label(),
            'date': p.payment_date,
            'cashbook': p.cash_book.name if p.cash_book else '',
            'status': p.get_status_display(),
            'creator': _get_user_display_name(p.created_by),
            'approver': _get_user_display_name(p.approved_by),
            'approved_at': p.approved_at,
            'description': p.description or '',
            'note': p.note or '',
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
        money_cols=['gross_amount', 'promotion', 'amount'],
        total_row={
            'stt': '',
            'code': 'TỔNG CỘNG',
            'gross_amount': total_gross,
            'promotion': total_promotion,
            'amount': total,
        },
    )


# ============ API: FINANCIAL PLANNING ============

def _generate_planning_code(model, prefix, digits=4):
    max_number = 0
    pattern = re.compile(rf'^{re.escape(prefix)}-?(\d+)$', re.IGNORECASE)
    for code in model.all_objects.filter(code__startswith=prefix).values_list('code', flat=True):
        match = pattern.match(code or '')
        if match:
            max_number = max(max_number, int(match.group(1)))
    number = max_number + 1
    while True:
        candidate = f'{prefix}-{number:0{digits}d}'
        if not model.all_objects.filter(code=candidate).exists():
            return candidate
        number += 1


def _financial_plans_for_user(request):
    store_ids = get_managed_store_ids(request.user)
    if request.user.is_superuser or not store_ids:
        return FinancialPlan.objects.none()
    return FinancialPlan.objects.filter(Q(store_id__in=store_ids) | Q(store_id__isnull=True))


def _get_financial_plan(request, plan_id, for_update=False):
    queryset = _financial_plans_for_user(request)
    if for_update:
        queryset = queryset.select_for_update()
    return queryset.filter(id=plan_id).first()


def _plan_receipts(request, plan, end_date=None):
    queryset = _filter_receipts_for_user(
        Receipt.objects.filter(
            status=1,
            receipt_date__gte=plan.start_date,
            receipt_date__lte=end_date or plan.end_date,
        ),
        request,
    )
    if plan.store_id:
        queryset = queryset.filter(
            Q(store_id=plan.store_id) |
            Q(store_id__isnull=True, order__store_id=plan.store_id)
        )
    return queryset


def _plan_payments(request, plan, end_date=None):
    queryset = _filter_payments_for_user(
        Payment.objects.filter(
            status=1,
            payment_date__gte=plan.start_date,
            payment_date__lte=end_date or plan.end_date,
        ),
        request,
    )
    if plan.store_id:
        queryset = queryset.filter(
            Q(store_id=plan.store_id) |
            Q(store_id__isnull=True, goods_receipt__warehouse__store_id=plan.store_id)
        )
    return queryset


def _actual_amounts_by_category(queryset):
    return {
        row['category_id']: Decimal(str(row['total'] or 0))
        for row in queryset.values('category_id').annotate(total=Sum('amount'))
    }


def _serialize_financial_plan(plan):
    return {
        'id': plan.id,
        'code': plan.code,
        'name': plan.name,
        'store_id': plan.store_id,
        'store': plan.store.name if plan.store else 'Toàn công ty',
        'period_type': plan.period_type,
        'period_type_display': plan.get_period_type_display(),
        'start_date': plan.start_date.isoformat(),
        'end_date': plan.end_date.isoformat(),
        'status': plan.status,
        'status_display': plan.get_status_display(),
        'note': plan.note or '',
        'alert_enabled': plan.alert_enabled,
        'alert_lead_days': plan.alert_lead_days or '3,7,15',
        'alert_email_recipients': plan.alert_email_recipients or '',
        'last_alert_sent': (
            plan.last_alert_sent.strftime('%d/%m/%Y %H:%M')
            if plan.last_alert_sent else ''
        ),
    }


def _month_start(value):
    return date(value.year, value.month, 1)


def _iter_plan_months(plan):
    current = _month_start(plan.start_date)
    final = _month_start(plan.end_date)
    while current <= final:
        yield current
        current = date(current.year + (1 if current.month == 12 else 0), (current.month % 12) + 1, 1)


def _month_end(month_value):
    return date(
        month_value.year,
        month_value.month,
        monthrange(month_value.year, month_value.month)[1],
    )


def _plan_snapshot(plan):
    items = []
    for item in plan.items.select_related('category', 'cash_book').prefetch_related('allocations'):
        items.append({
            'id': item.id,
            'direction': item.direction,
            'category_id': item.category_id,
            'category': item.category.name,
            'cash_book_id': item.cash_book_id,
            'planned_amount': float(item.planned_amount or 0),
            'expected_date': item.expected_date.isoformat() if item.expected_date else '',
            'include_in_forecast': item.include_in_forecast,
            'allocations': [{
                'month': allocation.month.isoformat(),
                'planned_amount': float(allocation.planned_amount or 0),
                'expected_date': allocation.expected_date.isoformat() if allocation.expected_date else '',
            } for allocation in item.allocations.all()],
        })
    schedules = [{
        'id': schedule.id,
        'code': schedule.code,
        'supplier_id': schedule.supplier_id,
        'goods_receipt_id': schedule.goods_receipt_id,
        'due_date': schedule.due_date.isoformat(),
        'gross_amount': float(schedule.gross_amount or 0),
        'amount': float(schedule.amount or 0),
        'priority': schedule.priority,
        'status': schedule.status,
        'source': schedule.source,
        'installment_no': schedule.installment_no,
    } for schedule in plan.supplier_schedules.all()]
    return {
        'plan': _serialize_financial_plan(plan),
        'items': items,
        'schedules': schedules,
    }


def _record_plan_revision(plan, actor, reason):
    latest_version = plan.revisions.aggregate(version=Max('version'))['version'] or 0
    return FinancialPlanRevision.objects.create(
        plan=plan,
        version=latest_version + 1,
        reason=(reason or 'Điều chỉnh kế hoạch')[:500],
        snapshot=_plan_snapshot(plan),
        created_by=actor,
    )


def _monthly_actuals(queryset, date_field):
    result = defaultdict(lambda: Decimal('0'))
    for row in queryset.values(date_field, 'category_id', 'cash_book_id', 'amount'):
        document_date = row[date_field]
        if not document_date:
            continue
        key = (_month_start(document_date), row['category_id'], row['cash_book_id'])
        result[key] += Decimal(str(row['amount'] or 0))
    return result


def _financial_plan_dashboard(request, plan):
    today = date.today()
    receipt_queryset = _plan_receipts(request, plan)
    payment_queryset = _plan_payments(request, plan)
    receipt_totals = _actual_amounts_by_category(receipt_queryset)
    payment_totals = _actual_amounts_by_category(payment_queryset)
    receipt_monthly = _monthly_actuals(receipt_queryset, 'receipt_date')
    payment_monthly = _monthly_actuals(payment_queryset, 'payment_date')
    items = list(
        plan.items.select_related('category', 'cash_book')
        .prefetch_related('allocations')
        .order_by('direction', 'category__name')
    )
    schedules = list(
        plan.supplier_schedules.select_related(
            'supplier', 'goods_receipt', 'cash_book', 'plan_item', 'payment',
        ).order_by('status', 'priority', 'due_date', 'id')
    )

    item_rows = []
    planned_income = Decimal('0')
    planned_expense = Decimal('0')
    actual_income = sum(receipt_totals.values(), Decimal('0'))
    actual_expense = sum(payment_totals.values(), Decimal('0'))
    alerts = []
    plan_months = list(_iter_plan_months(plan))
    monthly_summary = {
        month: {
            'month': month.isoformat(),
            'label': month.strftime('%m/%Y'),
            'planned_income': Decimal('0'),
            'planned_expense': Decimal('0'),
            'actual_income': Decimal('0'),
            'actual_expense': Decimal('0'),
        }
        for month in plan_months
    }
    for (month, _category_id, _cashbook_id), amount in receipt_monthly.items():
        if month in monthly_summary:
            monthly_summary[month]['actual_income'] += amount
    for (month, _category_id, _cashbook_id), amount in payment_monthly.items():
        if month in monthly_summary:
            monthly_summary[month]['actual_expense'] += amount

    for item in items:
        actual = (
            receipt_totals.get(item.category_id, Decimal('0'))
            if item.direction == 1
            else payment_totals.get(item.category_id, Decimal('0'))
        )
        planned = Decimal(str(item.planned_amount or 0))
        if item.direction == 1:
            planned_income += planned
        else:
            planned_expense += planned
        allocations = list(item.allocations.all())
        if allocations:
            for allocation in allocations:
                if allocation.month in monthly_summary:
                    key = 'planned_income' if item.direction == 1 else 'planned_expense'
                    monthly_summary[allocation.month][key] += Decimal(str(allocation.planned_amount or 0))
        elif plan_months:
            fallback_month = _month_start(item.expected_date or plan.end_date)
            fallback_month = fallback_month if fallback_month in monthly_summary else plan_months[-1]
            key = 'planned_income' if item.direction == 1 else 'planned_expense'
            monthly_summary[fallback_month][key] += planned
        variance = actual - planned
        if item.direction == 2 and planned and actual > planned:
            alerts.append({
                'type': 'over_budget',
                'level': 'warning',
                'date': '',
                'message': (
                    f'{item.get_direction_display()} "{item.category.name}" vượt kế hoạch '
                    f'{int(actual - planned):,}đ.'
                ),
            })
        item_rows.append({
            'id': item.id,
            'direction': item.direction,
            'direction_display': item.get_direction_display(),
            'category_id': item.category_id,
            'category': item.category.name,
            'cash_book_id': item.cash_book_id,
            'cash_book': item.cash_book.name if item.cash_book else '',
            'planned_amount': float(planned),
            'actual_amount': float(actual),
            'variance': float(variance),
            'completion_percent': round(float(actual * 100 / planned), 2) if planned else 0,
            'expected_date': item.expected_date.isoformat() if item.expected_date else '',
            'include_in_forecast': item.include_in_forecast,
            'note': item.note or '',
            'allocations': [{
                'id': allocation.id,
                'month': allocation.month.isoformat(),
                'month_label': allocation.month.strftime('%m/%Y'),
                'planned_amount': float(allocation.planned_amount),
                'actual_amount': float(sum(
                    amount for (month, category_id, _cashbook_id), amount in (
                        receipt_monthly.items() if item.direction == 1 else payment_monthly.items()
                    ) if month == allocation.month and category_id == item.category_id
                )),
                'expected_date': allocation.expected_date.isoformat() if allocation.expected_date else '',
                'note': allocation.note or '',
            } for allocation in allocations],
        })

    schedule_rows = []
    outstanding_scheduled_by_item = defaultdict(lambda: Decimal('0'))
    event_totals = defaultdict(lambda: {'income': Decimal('0'), 'expense': Decimal('0'), 'details': []})
    cashbook_events = defaultdict(
        lambda: defaultdict(lambda: {'income': Decimal('0'), 'expense': Decimal('0'), 'details': []})
    )

    def add_forecast_event(event_date, direction, amount, detail, cash_book_id=None):
        amount = Decimal(str(amount or 0))
        if amount <= 0:
            return
        key = 'income' if direction == 1 else 'expense'
        event_totals[event_date][key] += amount
        event_totals[event_date]['details'].append(detail)
        cashbook_events[cash_book_id][event_date][key] += amount
        cashbook_events[cash_book_id][event_date]['details'].append(detail)

    lead_days = []
    for raw_day in re.split(r'[,;\s]+', plan.alert_lead_days or '3,7,15'):
        try:
            parsed_day = int(raw_day)
        except (TypeError, ValueError):
            continue
        if 0 <= parsed_day <= 365:
            lead_days.append(parsed_day)
    alert_horizon = max(lead_days or [7])

    for schedule in schedules:
        effective_status = (
            2 if schedule.status == 2
            else (1 if schedule.payment and schedule.payment.status == 1 else schedule.status)
        )
        if effective_status == 0:
            outstanding_scheduled_by_item[schedule.plan_item_id] += Decimal(str(schedule.amount or 0))
            event_date = min(max(schedule.due_date, today), plan.end_date)
            add_forecast_event(
                event_date,
                2,
                schedule.amount,
                f'{schedule.code} · {schedule.supplier.name}',
                schedule.cash_book_id,
            )
            if schedule.due_date < today:
                alerts.append({
                    'type': 'overdue_supplier',
                    'level': 'danger',
                    'date': schedule.due_date.isoformat(),
                    'message': f'{schedule.code} của {schedule.supplier.name} đã quá hạn thanh toán.',
                })
            elif schedule.due_date <= today + timedelta(days=alert_horizon):
                alerts.append({
                    'type': 'supplier_due',
                    'level': 'warning',
                    'date': schedule.due_date.isoformat(),
                    'message': f'{schedule.code} của {schedule.supplier.name} sắp đến hạn.',
                })
        schedule_rows.append({
            'id': schedule.id,
            'code': schedule.code,
            'plan_item_id': schedule.plan_item_id,
            'supplier_id': schedule.supplier_id,
            'supplier': schedule.supplier.name,
            'goods_receipt_id': schedule.goods_receipt_id,
            'goods_receipt': schedule.goods_receipt.code if schedule.goods_receipt else '',
            'cash_book_id': schedule.cash_book_id,
            'cash_book': schedule.cash_book.name if schedule.cash_book else '',
            'due_date': schedule.due_date.isoformat(),
            'gross_amount': float(schedule.gross_amount),
            'promotion_mode': schedule.promotion_mode,
            'promotion_amount': float(schedule.promotion_amount),
            'promotion_percent': float(schedule.promotion_percent),
            'amount': float(schedule.amount),
            'priority': schedule.priority,
            'priority_display': schedule.get_priority_display(),
            'status': effective_status,
            'status_display': dict(SupplierPaymentSchedule.STATUS_CHOICES).get(effective_status, ''),
            'payment_id': schedule.payment_id,
            'payment_code': schedule.payment.code if schedule.payment else '',
            'note': schedule.note or '',
            'source': schedule.source,
            'source_display': schedule.get_source_display(),
            'installment_no': schedule.installment_no,
            'suggestion_reason': schedule.suggestion_reason or '',
        })

    item_actuals = {
        row['id']: Decimal(str(row['actual_amount']))
        for row in item_rows
    }
    for item in items:
        if not item.include_in_forecast:
            continue
        allocations = list(item.allocations.all())
        if allocations:
            scheduled_pool = outstanding_scheduled_by_item.get(item.id, Decimal('0'))
            for allocation in allocations:
                actual = sum(
                    amount for (month, category_id, _cashbook_id), amount in (
                        receipt_monthly.items() if item.direction == 1 else payment_monthly.items()
                    ) if month == allocation.month and category_id == item.category_id
                )
                remaining = max(
                    Decimal(str(allocation.planned_amount or 0)) - actual,
                    Decimal('0'),
                )
                if item.direction == 2:
                    covered_by_schedules = min(remaining, scheduled_pool)
                    remaining -= covered_by_schedules
                    scheduled_pool -= covered_by_schedules
                if not remaining:
                    continue
                event_date = allocation.expected_date or _month_end(allocation.month)
                event_date = min(max(event_date, today, plan.start_date), plan.end_date)
                add_forecast_event(
                    event_date,
                    item.direction,
                    remaining,
                    f'{item.get_direction_display()} · {item.category.name} · {allocation.month:%m/%Y}',
                    item.cash_book_id,
                )
        else:
            planned = Decimal(str(item.planned_amount or 0))
            actual = item_actuals.get(item.id, Decimal('0'))
            remaining = max(planned - actual, Decimal('0'))
            if item.direction == 2:
                remaining = max(
                    remaining - outstanding_scheduled_by_item.get(item.id, Decimal('0')),
                    Decimal('0'),
                )
            if not remaining:
                continue
            event_date = item.expected_date or plan.end_date
            event_date = min(max(event_date, today, plan.start_date), plan.end_date)
            add_forecast_event(
                event_date,
                item.direction,
                remaining,
                f'{item.get_direction_display()} · {item.category.name}',
                item.cash_book_id,
            )

    cashbooks = list(CashBook.objects.filter(is_active=True).order_by('name'))
    current_balance = sum(
        (Decimal(str(cashbook.balance or 0)) for cashbook in cashbooks),
        Decimal('0'),
    )
    minimum_balance = sum(
        (Decimal(str(cashbook.minimum_balance or 0)) for cashbook in cashbooks),
        Decimal('0'),
    )
    running_balance = current_balance
    forecast_rows = []
    first_shortage_date = today if current_balance < minimum_balance else None
    for event_date in sorted(event_totals):
        event = event_totals[event_date]
        running_balance += event['income'] - event['expense']
        if running_balance < minimum_balance and first_shortage_date is None:
            first_shortage_date = event_date
        forecast_rows.append({
            'date': event_date.isoformat(),
            'income': float(event['income']),
            'expense': float(event['expense']),
            'balance': float(running_balance),
            'details': event['details'],
        })
    if first_shortage_date:
        shortage_level = 'danger' if running_balance < 0 else 'warning'
        alerts.insert(0, {
            'type': 'cash_shortage',
            'level': shortage_level,
            'date': first_shortage_date.isoformat(),
            'message': (
                f'Dự kiến số dư xuống dưới mức an toàn từ ngày '
                f'{first_shortage_date.strftime("%d/%m/%Y")}.'
            ),
        })

    cashbook_forecasts = []
    cashbook_map = {cashbook.id: cashbook for cashbook in cashbooks}
    forecast_cashbook_ids = list(cashbook_map)
    if None in cashbook_events:
        forecast_cashbook_ids.append(None)
    for cashbook_id in forecast_cashbook_ids:
        cashbook = cashbook_map.get(cashbook_id)
        balance = Decimal(str(cashbook.balance or 0)) if cashbook else Decimal('0')
        safe_balance = Decimal(str(cashbook.minimum_balance or 0)) if cashbook else Decimal('0')
        shortage_date = today if balance < safe_balance else None
        points = []
        for event_date in sorted(cashbook_events.get(cashbook_id, {})):
            event = cashbook_events[cashbook_id][event_date]
            balance += event['income'] - event['expense']
            if balance < safe_balance and shortage_date is None:
                shortage_date = event_date
            points.append({
                'date': event_date.isoformat(),
                'income': float(event['income']),
                'expense': float(event['expense']),
                'balance': float(balance),
                'details': event['details'],
            })
        if shortage_date:
            alerts.append({
                'type': 'cashbook_shortage',
                'level': 'danger' if balance < 0 else 'warning',
                'date': shortage_date.isoformat(),
                'message': (
                    f'{cashbook.name if cashbook else "Khoản chưa chọn quỹ"} xuống dưới '
                    f'số dư tối thiểu từ ngày {shortage_date.strftime("%d/%m/%Y")}.'
                ),
            })
        cashbook_forecasts.append({
            'cash_book_id': cashbook_id,
            'cash_book': cashbook.name if cashbook else 'Chưa xác định quỹ',
            'current_balance': float(cashbook.balance or 0) if cashbook else 0,
            'minimum_balance': float(safe_balance),
            'forecast_balance': float(balance),
            'shortage_date': shortage_date.isoformat() if shortage_date else '',
            'points': points,
        })

    revisions = [{
        'id': revision.id,
        'version': revision.version,
        'reason': revision.reason,
        'created_by': _get_user_display_name(revision.created_by),
        'created_at': revision.created_at.strftime('%d/%m/%Y %H:%M'),
    } for revision in plan.revisions.select_related('created_by')[:20]]

    return {
        'plan': _serialize_financial_plan(plan),
        'summary': {
            'planned_income': float(planned_income),
            'planned_expense': float(planned_expense),
            'actual_income': float(actual_income),
            'actual_expense': float(actual_expense),
            'current_balance': float(current_balance),
            'minimum_balance': float(minimum_balance),
            'forecast_balance': float(running_balance),
            'alert_count': len(alerts),
        },
        'items': item_rows,
        'schedules': schedule_rows,
        'forecast': forecast_rows,
        'cashbook_forecasts': cashbook_forecasts,
        'monthly_summary': [{
            key: (float(value) if isinstance(value, Decimal) else value)
            for key, value in row.items()
        } for row in monthly_summary.values()],
        'alerts': alerts,
        'revisions': revisions,
    }


@login_required(login_url="/login/")
@brand_owner_required
@financial_plan_menu_required
def api_get_financial_plans(request):
    plans = list(_financial_plans_for_user(request).select_related('store'))
    selected = None
    plan_id = request.GET.get('plan_id')
    if plan_id:
        selected = next((plan for plan in plans if str(plan.id) == str(plan_id)), None)
    if not selected:
        today = date.today()
        selected = next(
            (plan for plan in plans if plan.start_date <= today <= plan.end_date and plan.status == 1),
            plans[0] if plans else None,
        )
    response = {'plans': [_serialize_financial_plan(plan) for plan in plans], 'dashboard': None}
    if selected:
        response['dashboard'] = _financial_plan_dashboard(request, selected)
    return JsonResponse(response)


@login_required(login_url="/login/")
@brand_owner_required
@financial_plan_menu_required
def api_save_financial_plan(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        period_type = str(data.get('period_type') or 'month')
        if period_type not in dict(FinancialPlan.PERIOD_CHOICES):
            raise ValueError('Kỳ kế hoạch không hợp lệ.')
        if period_type == 'month':
            period_value = str(data.get('period_value') or '')
            match = re.match(r'^(\d{4})-(\d{2})$', period_value)
            if not match:
                raise ValueError('Vui lòng chọn tháng kế hoạch.')
            year, month = int(match.group(1)), int(match.group(2))
            if month < 1 or month > 12:
                raise ValueError('Tháng kế hoạch không hợp lệ.')
            start_date = date(year, month, 1)
            end_date = date(year, month, monthrange(year, month)[1])
            default_name = f'Kế hoạch tháng {month:02d}/{year}'
        else:
            try:
                year = int(data.get('period_value'))
            except (TypeError, ValueError):
                raise ValueError('Vui lòng chọn năm kế hoạch.')
            start_date = date(year, 1, 1)
            end_date = date(year, 12, 31)
            default_name = f'Kế hoạch năm {year}'

        store_ids = get_managed_store_ids(request.user)
        store_id = data.get('store_id') or None
        if store_id and int(store_id) not in store_ids:
            raise ValueError('Cửa hàng không thuộc phạm vi quản lý.')
        if not store_id and len(store_ids) == 1:
            store_id = store_ids[0]

        with transaction.atomic():
            plan_id = data.get('id')
            revision_reason = (data.get('revision_reason') or '').strip()
            if plan_id:
                plan = _get_financial_plan(request, plan_id, for_update=True)
                if not plan:
                    raise ValueError('Không tìm thấy kế hoạch.')
                dates_outside = plan.items.filter(
                    Q(expected_date__lt=start_date) | Q(expected_date__gt=end_date)
                ).exists() or plan.supplier_schedules.filter(
                    Q(due_date__lt=start_date) | Q(due_date__gt=end_date)
                ).exists() or FinancialPlanAllocation.objects.filter(
                    item__plan=plan,
                ).filter(
                    Q(month__lt=_month_start(start_date)) |
                    Q(month__gt=_month_start(end_date)) |
                    Q(expected_date__lt=start_date) |
                    Q(expected_date__gt=end_date)
                ).exists()
                if dates_outside:
                    raise ValueError(
                        'Không thể đổi kỳ vì đang có khoản ngân sách hoặc lịch chi nằm ngoài kỳ mới.'
                    )
                if not revision_reason:
                    raise ValueError('Vui lòng nhập lý do điều chỉnh kế hoạch.')
                auto_code = False
            else:
                plan = FinancialPlan(created_by=request.user)
                auto_code = True
            plan.code = (data.get('code') or plan.code or _generate_planning_code(FinancialPlan, 'KHTC')).strip()
            plan.name = (data.get('name') or default_name).strip()
            plan.store_id = store_id
            plan.period_type = period_type
            plan.start_date = start_date
            plan.end_date = end_date
            plan.status = int(data.get('status', 1))
            if plan.status not in dict(FinancialPlan.STATUS_CHOICES):
                raise ValueError('Trạng thái kế hoạch không hợp lệ.')
            plan.note = data.get('note', '')
            plan.alert_enabled = str(data.get('alert_enabled', False)).lower() in ('true', '1')
            lead_days = []
            for raw_day in re.split(r'[,;\s]+', str(data.get('alert_lead_days') or '3,7,15')):
                if not raw_day:
                    continue
                try:
                    lead_day = int(raw_day)
                except ValueError:
                    raise ValueError('Số ngày cảnh báo phải là các số, ví dụ: 3,7,15.')
                if lead_day < 0 or lead_day > 365:
                    raise ValueError('Số ngày cảnh báo phải từ 0 đến 365.')
                lead_days.append(lead_day)
            plan.alert_lead_days = ','.join(str(day) for day in sorted(set(lead_days))) or '3,7,15'
            plan.alert_email_recipients = (data.get('alert_email_recipients') or '').strip()
            save_with_generated_code(
                plan,
                lambda: _generate_planning_code(FinancialPlan, 'KHTC'),
                auto_code,
            )
            _record_plan_revision(
                plan,
                request.user,
                revision_reason or 'Khởi tạo kế hoạch',
            )
        return JsonResponse({'status': 'ok', 'message': 'Đã lưu kế hoạch.', 'id': plan.id})
    except (ValueError, IntegrityError) as exc:
        message = str(exc)
        if 'unique' in message.lower():
            message = 'Mã kế hoạch đã tồn tại.'
        return JsonResponse({'status': 'error', 'message': message})
    except Exception as exc:
        logger.exception('Không thể lưu kế hoạch tài chính')
        return JsonResponse({'status': 'error', 'message': str(exc)})


@login_required(login_url="/login/")
@brand_owner_required
@financial_plan_menu_required
def api_delete_financial_plan(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            plan = _get_financial_plan(request, data.get('id'), for_update=True)
            if not plan:
                raise ValueError('Không tìm thấy kế hoạch.')
            if plan.supplier_schedules.filter(status=1).exists():
                raise ValueError('Kế hoạch đã có lịch thanh toán hoàn thành nên không thể xóa.')
            waiting_schedules = list(
                plan.supplier_schedules.select_related('payment').filter(status=0)
            )
            for schedule in waiting_schedules:
                schedule.status = 2
                schedule.save(update_fields=['status', 'updated_at'])
                if schedule.payment and schedule.payment.status == 0:
                    schedule.payment.status = 2
                    schedule.payment.note = (
                        f'{schedule.payment.note or ""}\n[HỦY KẾ HOẠCH] {plan.code}'
                    ).strip()
                    schedule.payment.save(update_fields=['status', 'note', 'updated_at'])
            plan.delete()
        return JsonResponse({'status': 'ok', 'message': 'Đã xóa kế hoạch.'})
    except Exception as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)})


@login_required(login_url="/login/")
@brand_owner_required
@financial_plan_menu_required
def api_save_financial_plan_item(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            plan = _get_financial_plan(request, data.get('plan_id'), for_update=True)
            if not plan:
                raise ValueError('Không tìm thấy kế hoạch.')
            if plan.status == 2:
                raise ValueError('Kế hoạch đã khóa, không thể chỉnh sửa.')
            direction = int(data.get('direction'))
            if direction not in (1, 2):
                raise ValueError('Loại ngân sách không hợp lệ.')
            category = FinanceCategory.objects.filter(
                id=data.get('category_id'), type=direction, is_active=True,
            ).first()
            if not category:
                raise ValueError('Danh mục thu/chi không hợp lệ.')
            allocation_payload = data.get('allocations') or []
            parsed_allocations = []
            seen_allocation_months = set()
            for allocation_data in allocation_payload:
                allocation_month = parse_date(str(allocation_data.get('month') or '')[:7] + '-01')
                if not allocation_month or not plan.start_date <= allocation_month <= plan.end_date:
                    raise ValueError('Tháng phân bổ không nằm trong kỳ kế hoạch.')
                if allocation_month in seen_allocation_months:
                    raise ValueError(f'Tháng {allocation_month:%m/%Y} bị nhập trùng.')
                seen_allocation_months.add(allocation_month)
                allocation_amount = _parse_payment_decimal(
                    allocation_data.get('planned_amount'),
                    f'Ngân sách tháng {allocation_month:%m/%Y}',
                ).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
                if allocation_amount < 0:
                    raise ValueError('Số tiền phân bổ không được âm.')
                allocation_date = parse_date(allocation_data.get('expected_date') or '')
                if allocation_date and _month_start(allocation_date) != allocation_month:
                    raise ValueError('Ngày dự kiến phải nằm đúng tháng phân bổ.')
                parsed_allocations.append({
                    'month': allocation_month,
                    'planned_amount': allocation_amount,
                    'expected_date': allocation_date,
                    'note': (allocation_data.get('note') or '').strip(),
                })
            amount_source = (
                sum((row['planned_amount'] for row in parsed_allocations), Decimal('0'))
                if parsed_allocations else data.get('planned_amount')
            )
            amount = _parse_payment_decimal(amount_source, 'Số tiền kế hoạch')
            if amount < 0:
                raise ValueError('Số tiền kế hoạch không được âm.')
            expected_date = parse_date(data.get('expected_date') or '')
            if expected_date and not plan.start_date <= expected_date <= plan.end_date:
                raise ValueError('Ngày dự kiến phải nằm trong kỳ kế hoạch.')
            item_id = data.get('id')
            item = plan.items.select_for_update().filter(id=item_id).first() if item_id else FinancialPlanItem(plan=plan)
            if item_id and not item:
                raise ValueError('Không tìm thấy khoản ngân sách.')
            revision_reason = (data.get('revision_reason') or '').strip()
            if item_id and not revision_reason:
                raise ValueError('Vui lòng nhập lý do điều chỉnh ngân sách.')
            item.direction = direction
            item.category = category
            item.cash_book_id = data.get('cash_book_id') or None
            item.planned_amount = amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            item.expected_date = expected_date
            item.include_in_forecast = str(data.get('include_in_forecast', True)).lower() not in ('false', '0')
            item.note = data.get('note', '')
            item.save()
            allocation_months = []
            for allocation_data in parsed_allocations:
                allocation_months.append(allocation_data['month'])
                allocation = FinancialPlanAllocation.all_objects.filter(
                    item=item,
                    month=allocation_data['month'],
                ).first()
                if not allocation:
                    allocation = FinancialPlanAllocation(item=item, month=allocation_data['month'])
                allocation.is_deleted = False
                allocation.deleted_at = None
                allocation.planned_amount = allocation_data['planned_amount']
                allocation.expected_date = allocation_data['expected_date']
                allocation.note = allocation_data['note']
                allocation.save()
            if parsed_allocations:
                item.allocations.exclude(month__in=allocation_months).delete()
            else:
                item.allocations.all().delete()
            _record_plan_revision(
                plan,
                request.user,
                revision_reason or f'Thêm ngân sách {category.name}',
            )
        return JsonResponse({'status': 'ok', 'message': 'Đã lưu khoản ngân sách.', 'id': item.id})
    except IntegrityError:
        return JsonResponse({'status': 'error', 'message': 'Danh mục này đã có trong kế hoạch.'})
    except Exception as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)})


@login_required(login_url="/login/")
@brand_owner_required
@financial_plan_menu_required
def api_delete_financial_plan_item(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            item = FinancialPlanItem.objects.select_related('plan').select_for_update().filter(id=data.get('id')).first()
            plan = _get_financial_plan(request, item.plan_id, for_update=True) if item else None
            if not item or not plan:
                raise ValueError('Không tìm thấy khoản ngân sách.')
            if plan.status == 2:
                raise ValueError('Kế hoạch đã khóa, không thể chỉnh sửa.')
            if item.supplier_schedules.exclude(status=2).exists():
                raise ValueError('Khoản ngân sách đang có lịch thanh toán nhà cung cấp.')
            reason = (data.get('revision_reason') or '').strip()
            if not reason:
                raise ValueError('Vui lòng nhập lý do xóa khoản ngân sách.')
            category_name = item.category.name
            item.delete()
            _record_plan_revision(plan, request.user, f'{reason} (xóa {category_name})')
        return JsonResponse({'status': 'ok', 'message': 'Đã xóa khoản ngân sách.'})
    except Exception as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)})


@login_required(login_url="/login/")
@brand_owner_required
@financial_plan_menu_required
def api_financial_plan_item_details(request, item_id):
    item = FinancialPlanItem.objects.select_related('plan', 'category').filter(id=item_id).first()
    if not item or not _get_financial_plan(request, item.plan_id):
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy khoản ngân sách.'})
    month_value = request.GET.get('month')
    month_start = parse_date(f'{month_value}-01') if month_value else None
    if month_value and not month_start:
        return JsonResponse({'status': 'error', 'message': 'Tháng không hợp lệ.'})
    if month_start:
        range_start = month_start
        range_end = _month_end(month_start)
    else:
        range_start = item.plan.start_date
        range_end = item.plan.end_date

    rows = []
    if item.direction == 1:
        queryset = _filter_receipts_for_user(
            Receipt.objects.select_related('customer', 'cash_book').filter(
                status=1,
                category_id=item.category_id,
                receipt_date__range=(range_start, range_end),
            ),
            request,
        )
        if item.plan.store_id:
            queryset = queryset.filter(
                Q(store_id=item.plan.store_id) |
                Q(store_id__isnull=True, order__store_id=item.plan.store_id)
            )
        for receipt in queryset.order_by('receipt_date', 'id'):
            rows.append({
                'id': receipt.id,
                'type': 'receipt',
                'code': receipt.code,
                'date': receipt.receipt_date.isoformat(),
                'amount': float(receipt.amount),
                'cash_book': receipt.cash_book.name if receipt.cash_book else '',
                'target': receipt.customer.name if receipt.customer else '',
                'description': receipt.description or '',
            })
    else:
        queryset = _filter_payments_for_user(
            Payment.objects.select_related('supplier', 'customer', 'cash_book').filter(
                status=1,
                category_id=item.category_id,
                payment_date__range=(range_start, range_end),
            ),
            request,
        )
        if item.plan.store_id:
            queryset = queryset.filter(
                Q(store_id=item.plan.store_id) |
                Q(store_id__isnull=True, goods_receipt__warehouse__store_id=item.plan.store_id)
            )
        for payment in queryset.order_by('payment_date', 'id'):
            rows.append({
                'id': payment.id,
                'type': 'payment',
                'code': payment.code,
                'date': payment.payment_date.isoformat(),
                'amount': float(payment.amount),
                'cash_book': payment.cash_book.name if payment.cash_book else '',
                'target': (
                    payment.supplier.name if payment.supplier
                    else (payment.customer.name if payment.customer else '')
                ),
                'description': payment.description or '',
            })
    return JsonResponse({
        'status': 'ok',
        'item': {
            'id': item.id,
            'direction': item.direction,
            'category': item.category.name,
            'period': f'{range_start:%d/%m/%Y} - {range_end:%d/%m/%Y}',
        },
        'rows': rows,
        'total': sum(row['amount'] for row in rows),
    })


@login_required(login_url="/login/")
@brand_owner_required
@financial_plan_menu_required
def api_financial_plan_revision_detail(request, revision_id):
    revision = FinancialPlanRevision.objects.select_related('plan', 'created_by').filter(
        id=revision_id
    ).first()
    if not revision or not _get_financial_plan(request, revision.plan_id):
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy phiên bản kế hoạch.'})
    return JsonResponse({
        'status': 'ok',
        'revision': {
            'id': revision.id,
            'version': revision.version,
            'reason': revision.reason,
            'created_by': _get_user_display_name(revision.created_by),
            'created_at': revision.created_at.strftime('%d/%m/%Y %H:%M'),
            'snapshot': revision.snapshot,
        },
    })


def _goods_receipt_schedule_capacity(receipt, current_schedule_id=None):
    returned = Decimal(str(
        PurchaseReturn.objects.filter(goods_receipt=receipt, status=1)
        .aggregate(total=Sum('total_amount'))['total'] or 0
    ))
    payable = max(Decimal(str(receipt.total_amount or 0)) - returned, Decimal('0'))
    paid_rows = Payment.objects.filter(goods_receipt=receipt, status=1).aggregate(
        amount=Sum('amount'), promotion=Sum('promotion_amount'),
    )
    settled = Decimal(str(paid_rows['amount'] or 0)) + Decimal(str(paid_rows['promotion'] or 0))
    schedules = SupplierPaymentSchedule.objects.filter(goods_receipt=receipt, status=0)
    if current_schedule_id:
        schedules = schedules.exclude(id=current_schedule_id)
    scheduled = Decimal(str(schedules.aggregate(total=Sum('gross_amount'))['total'] or 0))
    return payable, settled, scheduled, max(payable - settled - scheduled, Decimal('0'))


def _build_supplier_payment_suggestions(request, plan):
    """Xếp thử công nợ vào các quỹ mà vẫn giữ số dư tối thiểu.

    Thu kế hoạch làm tăng khả năng chi ở ngày dự kiến; các lịch chi đã có và
    những ngân sách chi không phải nhập hàng được giữ chỗ trước. Công nợ còn
    lại được xếp theo ưu tiên NCC, ngày đến hạn rồi mới đến ngày nhập.
    """
    today = date.today()
    cashbooks = list(CashBook.objects.filter(is_active=True).order_by('name'))
    cashbook_map = {cashbook.id: cashbook for cashbook in cashbooks}
    ledger = defaultdict(lambda: defaultdict(lambda: Decimal('0')))

    receipt_monthly = _monthly_actuals(_plan_receipts(request, plan), 'receipt_date')
    payment_monthly = _monthly_actuals(_plan_payments(request, plan), 'payment_date')
    items = list(
        plan.items.select_related('category', 'cash_book')
        .prefetch_related('allocations')
        .order_by('direction', 'id')
    )
    import_item = next(
        (
            item for item in items
            if item.direction == 2 and 'nhập' in item.category.name.lower()
        ),
        next((item for item in items if item.direction == 2), None),
    )

    for item in items:
        if not item.include_in_forecast or not item.cash_book_id:
            continue
        is_import_budget = item.direction == 2 and import_item and item.id == import_item.id
        if is_import_budget:
            # Công nợ phiếu nhập bên dưới chính là chi tiết của ngân sách này.
            continue
        allocations = list(item.allocations.all())
        if allocations:
            for allocation in allocations:
                monthly_actuals = receipt_monthly if item.direction == 1 else payment_monthly
                actual = sum(
                    amount for (month, category_id, _cashbook_id), amount in monthly_actuals.items()
                    if month == allocation.month and category_id == item.category_id
                )
                remaining = max(
                    Decimal(str(allocation.planned_amount or 0)) - actual,
                    Decimal('0'),
                )
                event_date = allocation.expected_date or _month_end(allocation.month)
                event_date = min(max(event_date, today, plan.start_date), plan.end_date)
                ledger[item.cash_book_id][event_date] += remaining if item.direction == 1 else -remaining
        else:
            actual = (
                sum(
                    amount for (_month, category_id, _cashbook_id), amount in receipt_monthly.items()
                    if category_id == item.category_id
                ) if item.direction == 1 else sum(
                    amount for (_month, category_id, _cashbook_id), amount in payment_monthly.items()
                    if category_id == item.category_id
                )
            )
            remaining = max(Decimal(str(item.planned_amount or 0)) - actual, Decimal('0'))
            event_date = min(max(item.expected_date or plan.end_date, today, plan.start_date), plan.end_date)
            ledger[item.cash_book_id][event_date] += remaining if item.direction == 1 else -remaining

    committed_schedules = SupplierPaymentSchedule.objects.filter(
        status=0,
        cash_book_id__isnull=False,
        due_date__range=(max(today, plan.start_date), plan.end_date),
        store_id__in=get_managed_store_ids(request.user),
    )
    if plan.store_id:
        committed_schedules = committed_schedules.filter(store_id=plan.store_id)
    for schedule in committed_schedules:
        event_date = min(max(schedule.due_date, today, plan.start_date), plan.end_date)
        ledger[schedule.cash_book_id][event_date] -= Decimal(str(schedule.amount or 0))

    receipts = list(
        filter_by_store(
            GoodsReceipt.objects.select_related('supplier', 'warehouse').filter(
                status=1,
                receipt_date__lte=plan.end_date,
                supplier_id__isnull=False,
            ),
            request,
            field_name='warehouse__store',
        ).order_by('receipt_date', 'id')
    )
    if plan.store_id:
        receipts = [
            receipt for receipt in receipts
            if receipt.warehouse_id and receipt.warehouse.store_id == plan.store_id
        ]

    candidates = []
    for receipt in receipts:
        _payable, _settled, _scheduled, available = _goods_receipt_schedule_capacity(receipt)
        if available <= 0:
            continue
        contractual_due = receipt.receipt_date + timedelta(
            days=int(receipt.supplier.payment_term_days or 0)
        )
        if contractual_due > plan.end_date:
            continue
        desired_date = min(max(contractual_due, today, plan.start_date), plan.end_date)
        candidates.append({
            'receipt': receipt,
            'remaining': available,
            'contractual_due': contractual_due,
            'desired_date': desired_date,
            'priority': receipt.supplier.payment_priority or 3,
        })
    candidates.sort(key=lambda row: (
        row['priority'], row['contractual_due'], row['receipt'].receipt_date, row['receipt'].id,
    ))

    def available_balance(cashbook, target_date):
        balance = Decimal(str(cashbook.balance or 0))
        for event_date, delta in ledger[cashbook.id].items():
            if event_date <= target_date:
                balance += delta
        return max(balance - Decimal(str(cashbook.minimum_balance or 0)), Decimal('0'))

    suggestions = []
    for candidate in candidates:
        receipt = candidate['receipt']
        remaining = candidate['remaining']
        candidate_dates = {candidate['desired_date'], plan.end_date}
        for cashbook_id in cashbook_map:
            candidate_dates.update(
                event_date for event_date, delta in ledger[cashbook_id].items()
                if delta > 0 and event_date >= candidate['desired_date']
            )
        for suggested_date in sorted(
            event_date for event_date in candidate_dates
            if candidate['desired_date'] <= event_date <= plan.end_date
        ):
            ranked_books = sorted(
                cashbooks,
                key=lambda cashbook: available_balance(cashbook, suggested_date),
                reverse=True,
            )
            for cashbook in ranked_books:
                capacity = available_balance(cashbook, suggested_date)
                if capacity <= 0 or remaining <= 0:
                    continue
                amount = min(capacity, remaining)
                ledger[cashbook.id][suggested_date] -= amount
                installment_no = len([
                    row for row in suggestions if row['goods_receipt_id'] == receipt.id
                ]) + 1
                late = suggested_date > candidate['contractual_due']
                suggestions.append({
                    'key': f'{receipt.id}:{cashbook.id}:{suggested_date.isoformat()}:{installment_no}',
                    'goods_receipt_id': receipt.id,
                    'goods_receipt': receipt.code,
                    'supplier_id': receipt.supplier_id,
                    'supplier': receipt.supplier.name,
                    'plan_item_id': import_item.id if import_item else None,
                    'cash_book_id': cashbook.id,
                    'cash_book': cashbook.name,
                    'contractual_due_date': candidate['contractual_due'].isoformat(),
                    'due_date': suggested_date.isoformat(),
                    'gross_amount': float(amount),
                    'amount': float(amount),
                    'priority': candidate['priority'],
                    'priority_display': dict(Supplier.PAYMENT_PRIORITY_CHOICES).get(
                        candidate['priority'], ''
                    ),
                    'installment_no': installment_no,
                    'late': late,
                    'insufficient': False,
                    'reason': (
                        f'Ưu tiên {dict(Supplier.PAYMENT_PRIORITY_CHOICES).get(candidate["priority"], "")}; '
                        f'hạn nợ {candidate["contractual_due"]:%d/%m/%Y}; '
                        f'quỹ vẫn giữ tối thiểu {int(cashbook.minimum_balance or 0):,}đ.'
                    ),
                })
                remaining -= amount
            if remaining <= 0:
                break
        if remaining > 0:
            suggestions.append({
                'key': f'{receipt.id}:unfunded',
                'goods_receipt_id': receipt.id,
                'goods_receipt': receipt.code,
                'supplier_id': receipt.supplier_id,
                'supplier': receipt.supplier.name,
                'plan_item_id': import_item.id if import_item else None,
                'cash_book_id': None,
                'cash_book': 'Chưa đủ nguồn tiền',
                'contractual_due_date': candidate['contractual_due'].isoformat(),
                'due_date': plan.end_date.isoformat(),
                'gross_amount': float(remaining),
                'amount': float(remaining),
                'priority': candidate['priority'],
                'priority_display': dict(Supplier.PAYMENT_PRIORITY_CHOICES).get(
                    candidate['priority'], ''
                ),
                'installment_no': 0,
                'late': True,
                'insufficient': True,
                'reason': 'Không có quỹ nào còn đủ tiền sau khi giữ số dư tối thiểu.',
            })
    return suggestions


@login_required(login_url="/login/")
@brand_owner_required
@financial_plan_menu_required
def api_suggest_supplier_payment_schedules(request):
    plan = _get_financial_plan(request, request.GET.get('plan_id'))
    if not plan:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy kế hoạch.'})
    suggestions = _build_supplier_payment_suggestions(request, plan)
    return JsonResponse({
        'status': 'ok',
        'suggestions': suggestions,
        'summary': {
            'funded_count': len([row for row in suggestions if not row['insufficient']]),
            'unfunded_count': len([row for row in suggestions if row['insufficient']]),
            'funded_amount': sum(row['amount'] for row in suggestions if not row['insufficient']),
            'unfunded_amount': sum(row['amount'] for row in suggestions if row['insufficient']),
        },
    })


@login_required(login_url="/login/")
@brand_owner_required
@financial_plan_menu_required
def api_apply_supplier_payment_suggestions(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            plan = _get_financial_plan(request, data.get('plan_id'), for_update=True)
            if not plan:
                raise ValueError('Không tìm thấy kế hoạch.')
            if plan.status == 2:
                raise ValueError('Kế hoạch đã khóa, không thể xếp lịch.')
            # Giữ nguyên số dư trong suốt lượt tính và tạo lịch để hai kế toán
            # không cùng lúc dùng chung một phần tiền khả dụng.
            list(CashBook.objects.select_for_update().filter(is_active=True))
            current_suggestions = {
                row['key']: row for row in _build_supplier_payment_suggestions(request, plan)
                if not row['insufficient']
            }
            selected_keys = list(dict.fromkeys(data.get('suggestion_keys') or []))
            if not selected_keys:
                raise ValueError('Vui lòng chọn ít nhất một đề xuất có đủ nguồn tiền.')
            created = []
            for suggestion_key in selected_keys:
                suggestion = current_suggestions.get(str(suggestion_key))
                if not suggestion:
                    raise ValueError('Đề xuất đã thay đổi. Vui lòng tính lại trước khi áp dụng.')
                receipt = filter_by_store(
                    GoodsReceipt.objects.select_related('supplier', 'warehouse').filter(
                        id=suggestion['goods_receipt_id'], status=1,
                    ),
                    request,
                    field_name='warehouse__store',
                ).first()
                if not receipt:
                    raise ValueError('Phiếu nhập trong đề xuất không còn hợp lệ.')
                gross = Decimal(str(suggestion['gross_amount'])).quantize(
                    Decimal('1'), rounding=ROUND_HALF_UP
                )
                _payable, _settled, _scheduled, available = _goods_receipt_schedule_capacity(receipt)
                if gross > available:
                    raise ValueError(f'Công nợ {receipt.code} vừa thay đổi. Vui lòng tính lại đề xuất.')
                schedule = SupplierPaymentSchedule(
                    code=_generate_planning_code(SupplierPaymentSchedule, 'LCT'),
                    plan=plan,
                    plan_item_id=suggestion.get('plan_item_id'),
                    store_id=receipt.warehouse.store_id if receipt.warehouse_id else None,
                    supplier_id=receipt.supplier_id,
                    goods_receipt=receipt,
                    cash_book_id=suggestion['cash_book_id'],
                    due_date=parse_date(suggestion['due_date']),
                    gross_amount=gross,
                    promotion_mode='amount',
                    promotion_amount=0,
                    promotion_percent=0,
                    amount=gross,
                    priority=suggestion['priority'],
                    status=0,
                    source='automatic',
                    installment_no=(
                        SupplierPaymentSchedule.objects.filter(goods_receipt=receipt)
                        .aggregate(max_no=Max('installment_no'))['max_no'] or 0
                    ) + 1,
                    suggestion_reason=suggestion['reason'],
                    note='Hệ thống đề xuất; chờ kế toán kiểm tra và duyệt.',
                    created_by=request.user,
                )
                save_with_generated_code(
                    schedule,
                    lambda: _generate_planning_code(SupplierPaymentSchedule, 'LCT'),
                    True,
                )
                payment = _sync_supplier_schedule_payment(schedule, request.user)
                created.append({'schedule': schedule.code, 'payment': payment.code})
            _record_plan_revision(
                plan,
                request.user,
                data.get('revision_reason') or f'Áp dụng {len(created)} đề xuất lịch thanh toán tự động',
            )
        return JsonResponse({
            'status': 'ok',
            'message': f'Đã tạo {len(created)} lịch và phiếu chi Nháp.',
            'created': created,
        })
    except ValueError as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)})
    except Exception as exc:
        logger.exception('Không thể áp dụng đề xuất lịch thanh toán')
        return JsonResponse({'status': 'error', 'message': str(exc)})


def _sync_supplier_schedule_payment(schedule, actor):
    payment = schedule.payment
    if payment and payment.status == 1:
        raise ValueError('Lịch đã thanh toán nên không thể sửa.')
    if not payment and schedule.goods_receipt_id:
        payment = (
            Payment.objects.select_for_update(of=('self',))
            .filter(
                goods_receipt_id=schedule.goods_receipt_id,
                status=0,
                supplier_schedule__isnull=True,
            )
            .order_by('id')
            .first()
        )
    if not payment:
        payment = Payment(
            code=_generate_next_payment_code(),
            created_by=actor,
            status=0,
            payment_method=2,
            reference=f'FINANCE_SCHEDULE:{schedule.id}',
        )
        auto_code = True
    else:
        auto_code = False
    payment.store_id = schedule.store_id
    payment.supplier_id = schedule.supplier_id
    payment.goods_receipt_id = schedule.goods_receipt_id
    payment.category_id = schedule.plan_item.category_id if schedule.plan_item_id else (
        FinanceCategory.objects.filter(type=2, is_active=True, name__iexact='Nhập hàng')
        .values_list('id', flat=True).first()
    )
    payment.cash_book_id = schedule.cash_book_id
    payment.payment_date = schedule.due_date
    payment.promotion_mode = schedule.promotion_mode
    payment.promotion_amount = schedule.promotion_amount
    payment.promotion_percent = schedule.promotion_percent
    payment.amount = schedule.amount
    payment.description = f'Thanh toán theo lịch {schedule.code} - {schedule.supplier.name}'
    if not payment.note or payment.note.startswith('Tự động tạo từ phiếu nhập'):
        payment.note = 'Tạo từ lịch thanh toán nhà cung cấp; chờ kế toán duyệt.'
    payment.status = 0
    payment.approved_by = None
    payment.approved_at = None
    save_with_generated_code(payment, _generate_next_payment_code, auto_code)
    if schedule.payment_id != payment.id:
        schedule.payment = payment
        schedule.save(update_fields=['payment', 'updated_at'])
    return payment


@login_required(login_url="/login/")
@brand_owner_required
@financial_plan_menu_required
def api_save_supplier_payment_schedule(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            plan = _get_financial_plan(request, data.get('plan_id'), for_update=True)
            if not plan:
                raise ValueError('Không tìm thấy kế hoạch.')
            if plan.status == 2:
                raise ValueError('Kế hoạch đã khóa, không thể chỉnh sửa.')
            schedule_id = data.get('id')
            revision_reason = (data.get('revision_reason') or '').strip()
            schedule = (
                plan.supplier_schedules.select_for_update().filter(id=schedule_id).first()
                if schedule_id else SupplierPaymentSchedule(plan=plan, created_by=request.user)
            )
            if schedule_id and not schedule:
                raise ValueError('Không tìm thấy lịch thanh toán.')
            if schedule_id and (schedule.status == 1 or (schedule.payment and schedule.payment.status == 1)):
                raise ValueError('Lịch đã thanh toán nên không thể sửa.')
            if schedule_id and not revision_reason:
                raise ValueError('Vui lòng nhập lý do điều chỉnh lịch thanh toán.')

            plan_item_id = data.get('plan_item_id') or None
            plan_item = plan.items.filter(id=plan_item_id, direction=2).first() if plan_item_id else None
            if plan_item_id and not plan_item:
                raise ValueError('Khoản ngân sách chi không hợp lệ.')
            due_date = parse_date(data.get('due_date') or '')
            if not due_date:
                raise ValueError('Vui lòng chọn ngày dự kiến thanh toán.')
            if not plan.start_date <= due_date <= plan.end_date:
                raise ValueError('Ngày thanh toán phải nằm trong kỳ kế hoạch.')

            receipt = None
            receipt_id = data.get('goods_receipt_id') or None
            if receipt_id:
                receipt = filter_by_store(
                    GoodsReceipt.objects.select_related('supplier', 'warehouse').filter(id=receipt_id, status=1),
                    request,
                    field_name='warehouse__store',
                ).first()
                if not receipt:
                    raise ValueError('Phiếu nhập không hợp lệ hoặc không thuộc phạm vi quản lý.')
                supplier_id = receipt.supplier_id
                store_id = receipt.warehouse.store_id if receipt.warehouse_id else None
                if plan.store_id and store_id != plan.store_id:
                    raise ValueError('Phiếu nhập không thuộc cửa hàng của kế hoạch.')
            else:
                supplier_id = data.get('supplier_id') or None
                store_id = plan.store_id or (_get_default_store_for_request(request).id if _get_default_store_for_request(request) else None)
            if not supplier_id or not Supplier.objects.filter(id=supplier_id, is_active=True).exists():
                raise ValueError('Vui lòng chọn nhà cung cấp.')

            gross = _parse_payment_decimal(data.get('gross_amount'), 'Số tiền trước khuyến mãi')
            if gross <= 0:
                raise ValueError('Số tiền trước khuyến mãi phải lớn hơn 0.')
            gross = gross.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            if receipt:
                _, _, _, available = _goods_receipt_schedule_capacity(receipt, schedule_id)
                if gross > available:
                    raise ValueError(
                        f'Số tiền xếp lịch vượt công nợ còn có thể xếp: {int(available):,}đ.'
                    )

            calculator = Payment(
                amount=schedule.amount or 0,
                promotion_mode=schedule.promotion_mode or 'amount',
                promotion_amount=schedule.promotion_amount or 0,
                promotion_percent=schedule.promotion_percent or 0,
            )
            promotion_data = dict(data)
            promotion_data['gross_amount'] = gross
            _apply_payment_promotion(calculator, promotion_data)
            priority = int(data.get('priority', 3))
            if priority not in dict(SupplierPaymentSchedule.PRIORITY_CHOICES):
                raise ValueError('Mức ưu tiên không hợp lệ.')

            auto_code = not schedule_id
            schedule.code = schedule.code or _generate_planning_code(SupplierPaymentSchedule, 'LCT')
            schedule.plan_item = plan_item
            schedule.store_id = store_id
            schedule.supplier_id = supplier_id
            schedule.goods_receipt = receipt
            schedule.cash_book_id = data.get('cash_book_id') or (plan_item.cash_book_id if plan_item else None)
            schedule.due_date = due_date
            schedule.gross_amount = gross
            schedule.promotion_mode = calculator.promotion_mode
            schedule.promotion_amount = calculator.promotion_amount
            schedule.promotion_percent = calculator.promotion_percent
            schedule.amount = calculator.amount
            schedule.priority = priority
            schedule.status = 0
            source = str(data.get('source') or schedule.source or 'manual')
            schedule.source = source if source in dict(SupplierPaymentSchedule.SOURCE_CHOICES) else 'manual'
            if not schedule_id:
                schedule.installment_no = (
                    SupplierPaymentSchedule.objects.filter(goods_receipt=receipt)
                    .aggregate(max_no=Max('installment_no'))['max_no'] or 0
                ) + 1 if receipt else 1
            schedule.suggestion_reason = (data.get('suggestion_reason') or '').strip()
            schedule.note = data.get('note', '')
            save_with_generated_code(
                schedule,
                lambda: _generate_planning_code(SupplierPaymentSchedule, 'LCT'),
                auto_code,
            )
            payment = _sync_supplier_schedule_payment(schedule, request.user)
            _record_plan_revision(
                plan,
                request.user,
                revision_reason or (
                    f'Xếp lịch thanh toán {schedule.code}' if not schedule_id
                    else f'Điều chỉnh lịch thanh toán {schedule.code}'
                ),
            )
        return JsonResponse({
            'status': 'ok', 'message': 'Đã xếp lịch và tạo phiếu chi Nháp.',
            'id': schedule.id, 'payment_id': payment.id, 'payment_code': payment.code,
        })
    except ValueError as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)})
    except Exception as exc:
        logger.exception('Không thể lưu lịch thanh toán nhà cung cấp')
        return JsonResponse({'status': 'error', 'message': str(exc)})


@login_required(login_url="/login/")
@brand_owner_required
@financial_plan_menu_required
def api_delete_supplier_payment_schedule(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            schedule = SupplierPaymentSchedule.objects.select_related('plan', 'payment').select_for_update(
                of=('self',)
            ).filter(
                id=data.get('id')
            ).first()
            if not schedule or not _get_financial_plan(request, schedule.plan_id):
                raise ValueError('Không tìm thấy lịch thanh toán.')
            if schedule.status == 1 or (schedule.payment and schedule.payment.status == 1):
                raise ValueError('Lịch đã thanh toán nên không thể hủy.')
            revision_reason = (data.get('revision_reason') or '').strip()
            if not revision_reason:
                raise ValueError('Vui lòng nhập lý do hủy lịch thanh toán.')
            schedule.status = 2
            schedule.save(update_fields=['status', 'updated_at'])
            if schedule.payment and schedule.payment.status == 0:
                schedule.payment.status = 2
                schedule.payment.note = (
                    f'{schedule.payment.note or ""}\n[HỦY LỊCH] {schedule.code}'
                ).strip()
                schedule.payment.save(update_fields=['status', 'note', 'updated_at'])
            _record_plan_revision(
                schedule.plan,
                request.user,
                f'{revision_reason} (hủy {schedule.code})',
            )
        return JsonResponse({'status': 'ok', 'message': 'Đã hủy lịch và phiếu chi Nháp liên quan.'})
    except Exception as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)})
