from django.db import migrations


CATEGORY_NAME = 'Hoàn hàng'
CATEGORY_DESCRIPTION = 'Chi hoàn tiền cho khách khi trả hàng'


def backfill_order_return_payment_category(apps, schema_editor):
    FinanceCategory = apps.get_model('finance', 'FinanceCategory')
    Payment = apps.get_model('finance', 'Payment')

    refund_payments = Payment.objects.filter(reference__startswith='ORDER_RETURN:')
    brand_ids = set(refund_payments.values_list('store__brand_id', flat=True))
    for brand_id in brand_ids:
        category = (
            FinanceCategory.objects
            .filter(
                brand_id=brand_id,
                type=2,
                name__iexact=CATEGORY_NAME,
                is_deleted=False,
            )
            .order_by('-is_active', 'id')
            .first()
        )
        if not category:
            category = FinanceCategory.objects.create(
                brand_id=brand_id,
                name=CATEGORY_NAME,
                type=2,
                description=CATEGORY_DESCRIPTION,
                is_active=True,
                is_deleted=False,
            )
        refund_payments.filter(store__brand_id=brand_id).update(category_id=category.id)


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0020_expenseclassification_parent_category'),
    ]

    operations = [
        migrations.RunPython(
            backfill_order_return_payment_category,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
