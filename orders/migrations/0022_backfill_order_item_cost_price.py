from decimal import Decimal

from django.db import migrations


def backfill_order_item_cost_price(apps, schema_editor):
    OrderItem = apps.get_model('orders', 'OrderItem')
    ComboItem = apps.get_model('products', 'ComboItem')
    items = OrderItem.objects.filter(
        cost_price__lte=0,
        product__isnull=False,
    ).select_related('product', 'variant')

    pending = []
    for item in items.iterator(chunk_size=500):
        candidates = []
        if item.variant_id:
            candidates.extend([item.variant.cost_price, item.variant.import_price])
        candidates.extend([item.product.cost_price, item.product.import_price])
        effective_cost = next(
            (Decimal(str(value)) for value in candidates if Decimal(str(value or 0)) > 0),
            Decimal('0'),
        )
        if effective_cost <= 0 and item.product.is_combo:
            combo_cost = Decimal('0')
            for combo_item in ComboItem.objects.filter(combo_id=item.product_id).select_related('product'):
                component_cost = next(
                    (
                        Decimal(str(value))
                        for value in (combo_item.product.cost_price, combo_item.product.import_price)
                        if Decimal(str(value or 0)) > 0
                    ),
                    Decimal('0'),
                )
                combo_cost += component_cost * Decimal(str(combo_item.quantity or 0))
            effective_cost = combo_cost
        if effective_cost <= 0:
            continue
        item.cost_price = effective_cost
        pending.append(item)
        if len(pending) >= 500:
            OrderItem.objects.bulk_update(pending, ['cost_price'], batch_size=500)
            pending = []

    if pending:
        OrderItem.objects.bulk_update(pending, ['cost_price'], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0021_order_other_fee_quotation_other_fee'),
    ]

    operations = [
        migrations.RunPython(backfill_order_item_cost_price, migrations.RunPython.noop),
    ]
