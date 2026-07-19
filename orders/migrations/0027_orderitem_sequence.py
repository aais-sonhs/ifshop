from django.db import migrations, models


def backfill_order_item_sequences(apps, schema_editor):
    OrderItem = apps.get_model('orders', 'OrderItem')
    pending = []
    current_order_id = None
    sequence = 0

    for item in OrderItem.objects.order_by('order_id', 'id').iterator(chunk_size=2000):
        if item.order_id != current_order_id:
            current_order_id = item.order_id
            sequence = 1
        else:
            sequence += 1
        item.sequence = sequence
        pending.append(item)
        if len(pending) >= 2000:
            OrderItem.objects.bulk_update(pending, ['sequence'], batch_size=2000)
            pending = []

    if pending:
        OrderItem.objects.bulk_update(pending, ['sequence'], batch_size=2000)


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0026_order_shipping_phone'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderitem',
            name='sequence',
            field=models.PositiveIntegerField(default=0, verbose_name='Số thứ tự'),
        ),
        migrations.RunPython(backfill_order_item_sequences, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name='orderitem',
            options={
                'ordering': ['sequence', 'id'],
                'verbose_name': 'Chi tiết đơn hàng',
                'verbose_name_plural': 'Chi tiết đơn hàng',
            },
        ),
        migrations.AddConstraint(
            model_name='orderitem',
            constraint=models.UniqueConstraint(
                fields=('order', 'sequence'),
                name='uniq_order_item_sequence',
            ),
        ),
    ]
