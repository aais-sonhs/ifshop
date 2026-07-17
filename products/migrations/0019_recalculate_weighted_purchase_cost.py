from collections import defaultdict
from decimal import Decimal

from django.db import migrations


def recalculate_weighted_purchase_cost(apps, schema_editor):
    Product = apps.get_model('products', 'Product')
    ProductVariant = apps.get_model('products', 'ProductVariant')
    GoodsReceiptItem = apps.get_model('products', 'GoodsReceiptItem')
    PurchaseReturnItem = apps.get_model('products', 'PurchaseReturnItem')

    received_quantity = defaultdict(Decimal)
    received_value = defaultdict(Decimal)
    variant_received_quantity = defaultdict(Decimal)
    variant_received_value = defaultdict(Decimal)

    completed_receipt_items = GoodsReceiptItem.objects.filter(
        goods_receipt__status=1,
        goods_receipt__is_deleted=False,
    )
    for product_id, variant_id, quantity, unit_price in completed_receipt_items.values_list(
        'product_id',
        'variant_id',
        'quantity',
        'unit_price',
    ).iterator():
        quantity = Decimal(quantity or 0)
        unit_price = Decimal(unit_price or 0)
        received_quantity[product_id] += quantity
        received_value[product_id] += quantity * unit_price
        if variant_id:
            variant_received_quantity[variant_id] += quantity
            variant_received_value[variant_id] += quantity * unit_price

    returned_quantity = defaultdict(Decimal)
    returned_value = defaultdict(Decimal)
    variant_returned_quantity = defaultdict(Decimal)
    variant_returned_value = defaultdict(Decimal)
    completed_return_items = PurchaseReturnItem.objects.filter(
        purchase_return__status=1,
        purchase_return__is_deleted=False,
        goods_receipt_item__goods_receipt__status=1,
        goods_receipt_item__goods_receipt__is_deleted=False,
    )
    for product_id, variant_id, quantity, original_unit_price in completed_return_items.values_list(
        'product_id',
        'goods_receipt_item__variant_id',
        'quantity',
        'goods_receipt_item__unit_price',
    ).iterator():
        quantity = Decimal(quantity or 0)
        original_unit_price = Decimal(original_unit_price or 0)
        returned_quantity[product_id] += quantity
        returned_value[product_id] += quantity * original_unit_price
        if variant_id:
            variant_returned_quantity[variant_id] += quantity
            variant_returned_value[variant_id] += quantity * original_unit_price

    latest_product_price = {}
    latest_variant_price = {}
    for product_id, variant_id, unit_price in completed_receipt_items.order_by(
        '-goods_receipt__receipt_date',
        '-goods_receipt__id',
        '-id',
    ).values_list('product_id', 'variant_id', 'unit_price').iterator():
        latest_product_price.setdefault(product_id, Decimal(unit_price or 0))
        if variant_id:
            latest_variant_price.setdefault(variant_id, Decimal(unit_price or 0))

    products_to_update = []
    for product in Product.objects.filter(
        id__in=received_quantity.keys(),
        is_deleted=False,
    ):
        net_quantity = received_quantity[product.id] - returned_quantity[product.id]
        net_value = received_value[product.id] - returned_value[product.id]
        product.cost_price = round(net_value / net_quantity) if net_quantity > 0 else Decimal('0')
        product.import_price = latest_product_price.get(product.id, Decimal('0'))
        products_to_update.append(product)
    if products_to_update:
        Product.objects.bulk_update(products_to_update, ['cost_price', 'import_price'], batch_size=500)

    variants_to_update = []
    for variant in ProductVariant.objects.filter(id__in=variant_received_quantity.keys()):
        net_quantity = variant_received_quantity[variant.id] - variant_returned_quantity[variant.id]
        net_value = variant_received_value[variant.id] - variant_returned_value[variant.id]
        variant.cost_price = round(net_value / net_quantity) if net_quantity > 0 else Decimal('0')
        variant.import_price = latest_variant_price.get(variant.id, Decimal('0'))
        variants_to_update.append(variant)
    if variants_to_update:
        ProductVariant.objects.bulk_update(
            variants_to_update,
            ['cost_price', 'import_price'],
            batch_size=500,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0018_product_warranty_fields'),
    ]

    operations = [
        migrations.RunPython(
            recalculate_weighted_purchase_cost,
            migrations.RunPython.noop,
        ),
    ]
