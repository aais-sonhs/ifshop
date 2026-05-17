from decimal import Decimal

from django.db import migrations
from django.db.models import Sum


def demote_unpaid_completed_orders(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    Receipt = apps.get_model('finance', 'Receipt')

    receipt_totals = {
        row['order_id']: row['total'] or Decimal('0')
        for row in Receipt.objects.filter(
            order_id__isnull=False,
            status=1,
            is_deleted=False,
        ).values('order_id').annotate(total=Sum('amount'))
    }

    completed_orders = Order.objects.filter(
        status=5,
        is_deleted=False,
    ).only('id', 'final_amount', 'paid_amount', 'payment_status')

    for order in completed_orders.iterator():
        target_total = max(Decimal(str(order.final_amount or 0)), Decimal('0'))
        receipt_total = receipt_totals.get(order.id)
        paid_amount = receipt_total if receipt_total is not None else Decimal(str(order.paid_amount or 0))

        if paid_amount >= target_total:
            payment_status = 2
        elif paid_amount > 0:
            payment_status = 1
        else:
            payment_status = 0

        updates = {}
        if Decimal(str(order.paid_amount or 0)) != paid_amount:
            updates['paid_amount'] = paid_amount
        if order.payment_status != payment_status:
            updates['payment_status'] = payment_status
        if target_total > 0 and payment_status != 2:
            updates['status'] = 4

        if updates:
            Order.objects.filter(pk=order.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0010_receipt_cashbook_applied'),
        ('orders', '0014_alter_order_status_alter_orderedithistory_action'),
    ]

    operations = [
        migrations.RunPython(demote_unpaid_completed_orders, migrations.RunPython.noop),
    ]
