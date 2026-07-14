from datetime import date as date_type, datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import CashBook, Receipt


def normalize_order_receipt_date(order, value=None):
    """Chuẩn hóa ngày thu của đơn và chặn ngày không thể xảy ra trong thực tế."""
    now = timezone.now()
    today = timezone.localtime(now).date() if timezone.is_aware(now) else now.date()
    if value in (None, ''):
        receipt_date = today
    elif isinstance(value, datetime):
        receipt_date = value.date()
    elif isinstance(value, date_type):
        receipt_date = value
    else:
        receipt_date = parse_date(str(value).strip())
        if not receipt_date:
            raise ValueError('Ngày thanh toán không hợp lệ.')

    created_date = None
    if order and getattr(order, 'created_at', None):
        created_at = order.created_at
        if timezone.is_aware(created_at):
            created_at = timezone.localtime(created_at)
        created_date = created_at.date()

    if created_date and receipt_date < created_date:
        raise ValueError(
            f'Ngày thanh toán không được trước ngày tạo đơn ({created_date.strftime("%d/%m/%Y")}).'
        )
    if receipt_date > today:
        raise ValueError(
            f'Ngày thanh toán không được vượt quá ngày hiện tại ({today.strftime("%d/%m/%Y")}).'
        )
    return receipt_date


def capture_receipt_effect(receipt):
    """Chụp lại trạng thái đã áp hiệu ứng của phiếu thu để hoàn/tái áp an toàn khi sửa."""
    if not receipt:
        return None
    return {
        'status': int(receipt.status or 0),
        'cash_book_id': receipt.cash_book_id,
        'amount': Decimal(str(receipt.amount or 0)),
        'order_id': receipt.order_id,
        'cashbook_applied': bool(getattr(receipt, 'cashbook_applied', False)),
    }


def _apply_receipt_cashbook_delta(effect, multiplier, require_applied=True):
    """Áp delta vào quỹ theo ảnh chụp hiệu ứng của phiếu thu.

    `multiplier = 1` dùng để cộng lại hiệu ứng.
    `multiplier = -1` dùng để hoàn tác hiệu ứng cũ.
    """
    if not effect or effect['status'] != 1 or not effect['cash_book_id']:
        return False
    if require_applied and not effect.get('cashbook_applied'):
        return False
    amount = effect['amount'] * Decimal(str(multiplier))
    if amount == 0:
        return False
    cash_book = CashBook.objects.select_for_update().get(id=effect['cash_book_id'])
    cash_book.balance = Decimal(str(cash_book.balance or 0)) + amount
    cash_book.save(update_fields=['balance'])
    return True


def update_order_payment_status(order):
    """Tổng hợp lại số tiền đã thu thực tế và trạng thái thanh toán của đơn."""
    if not order:
        return
    total_paid = sum(
        Decimal(str(receipt.amount or 0))
        for receipt in Receipt.objects.filter(order=order, status=1)
    )
    target_total = max(Decimal(str(order.final_amount or 0)), Decimal('0'))
    order.paid_amount = total_paid
    if total_paid >= target_total:
        order.payment_status = 2
    elif total_paid > 0:
        order.payment_status = 1
    else:
        order.payment_status = 0

    update_fields = ['paid_amount', 'payment_status']
    if order.status == 0 and total_paid > 0:
        order.status = 1
        update_fields.append('status')
    if order.status == 5 and order.payment_status != 2 and target_total > 0:
        order.status = 4
        update_fields.append('status')
    if (
        order.status == 4
        and order.payment_status == 2
        and (not getattr(order, 'approver_id', None) or order.approval_status == 2)
    ):
        order.status = 5
        update_fields.append('status')
    order.save(update_fields=update_fields)


def save_receipt_with_effect(receipt, old_effect=None):
    """Lưu phiếu thu và đồng bộ toàn bộ hiệu ứng phụ trong cùng một transaction.

    Thứ tự xử lý:
    1. Hoàn tác hiệu ứng cũ nếu đang sửa phiếu.
    2. Lưu chứng từ mới.
    3. Áp hiệu ứng mới vào quỹ nếu phiếu ở trạng thái hoàn thành.
    4. Cập nhật lại trạng thái thanh toán của các đơn bị ảnh hưởng.
    """
    from orders.models import Order

    with transaction.atomic():
        _apply_receipt_cashbook_delta(old_effect, -1)
        receipt.cashbook_applied = False
        receipt.save()
        new_effect = capture_receipt_effect(receipt)
        if _apply_receipt_cashbook_delta(new_effect, 1, require_applied=False):
            receipt.cashbook_applied = True
            receipt.save(update_fields=['cashbook_applied'])

        touched_order_ids = {
            effect['order_id']
            for effect in (old_effect, new_effect)
            if effect and effect.get('order_id')
        }
        for order in Order.objects.filter(id__in=touched_order_ids):
            update_order_payment_status(order)

    return receipt


def cancel_receipt_with_effect(receipt, note_prefix=''):
    """Hủy phiếu thu bằng cách chuyển trạng thái và đi lại luồng save tiêu chuẩn."""
    if not receipt:
        return
    old_effect = capture_receipt_effect(receipt)
    receipt.status = 2
    if note_prefix:
        receipt.note = f'{note_prefix} {receipt.note or ""}'.strip()
    save_receipt_with_effect(receipt, old_effect=old_effect)


def delete_receipt_with_effect(receipt):
    """Xóa phiếu thu và hoàn toàn bộ hiệu ứng đã áp lên quỹ/đơn hàng."""
    if not receipt:
        return
    old_effect = capture_receipt_effect(receipt)
    order = receipt.order
    with transaction.atomic():
        _apply_receipt_cashbook_delta(old_effect, -1)
        receipt.delete()
        if order:
            update_order_payment_status(order)
