from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations


def recalculate_draft_goods_receipt_payments(apps, schema_editor):
    Payment = apps.get_model('finance', 'Payment')
    drafts = list(
        Payment.objects.filter(
            status=0,
            goods_receipt_id__isnull=False,
            is_deleted=False,
        ).select_related('goods_receipt')
    )

    for payment in drafts:
        gross_amount = Decimal(str(payment.goods_receipt.total_amount or 0))
        promotion_percent = Decimal(str(payment.promotion_percent or 0))
        if payment.promotion_mode == 'percent':
            promotion_amount = (
                gross_amount * promotion_percent / Decimal('100')
            ).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        else:
            promotion_amount = Decimal(str(payment.promotion_amount or 0))

        promotion_amount = min(max(promotion_amount, Decimal('0')), gross_amount)
        if payment.promotion_mode == 'amount':
            promotion_percent = (
                promotion_amount * Decimal('100') / gross_amount
                if gross_amount else Decimal('0')
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        payment.promotion_amount = promotion_amount
        payment.promotion_percent = promotion_percent
        payment.amount = gross_amount - promotion_amount

    if drafts:
        Payment.objects.bulk_update(
            drafts,
            ['promotion_amount', 'promotion_percent', 'amount'],
            batch_size=500,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0014_payment_promotion'),
    ]

    operations = [
        migrations.RunPython(
            recalculate_draft_goods_receipt_payments,
            migrations.RunPython.noop,
        ),
    ]
