from decimal import Decimal

from django.db import transaction

from .models import CashBook, Receipt


def capture_receipt_effect(receipt):
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
    if not effect or effect['status'] != 1 or not effect['cash_book_id']:
        return False
    if require_applied and not effect.get('cashbook_applied'):
        return False
    amount = effect['amount'] * Decimal(str(multiplier))
    if amount == 0:
        return False
    cash_book = CashBook.objects.select_for_update().get(id=effect['cash_book_id'])
    cash_book.balance += amount
    cash_book.save(update_fields=['balance'])
    return True


def update_order_payment_status(order):
    if not order:
        return
    total_paid = sum(
        Decimal(str(receipt.amount or 0))
        for receipt in Receipt.objects.filter(order=order, status=1)
    )
    order.paid_amount = total_paid
    if total_paid >= Decimal(str(order.final_amount or 0)):
        order.payment_status = 2
    elif total_paid > 0:
        order.payment_status = 1
    else:
        order.payment_status = 0
    order.save(update_fields=['paid_amount', 'payment_status'])


def save_receipt_with_effect(receipt, old_effect=None):
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
    if not receipt:
        return
    old_effect = capture_receipt_effect(receipt)
    receipt.status = 2
    if note_prefix:
        receipt.note = f'{note_prefix} {receipt.note or ""}'.strip()
    save_receipt_with_effect(receipt, old_effect=old_effect)


def delete_receipt_with_effect(receipt):
    if not receipt:
        return
    old_effect = capture_receipt_effect(receipt)
    order = receipt.order
    with transaction.atomic():
        _apply_receipt_cashbook_delta(old_effect, -1)
        receipt.delete()
        if order:
            update_order_payment_status(order)
