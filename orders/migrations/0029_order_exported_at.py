from datetime import datetime, time

from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def backfill_order_exported_at(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    OrderEditHistory = apps.get_model('orders', 'OrderEditHistory')

    exported_orders = list(
        Order.objects.filter(
            status__in=(4, 5),
            exported_at__isnull=True,
        ).only('id', 'order_date', 'exported_at')
    )
    if not exported_orders:
        return

    order_ids = [order.id for order in exported_orders]
    first_export_times = {}

    export_histories = OrderEditHistory.objects.filter(
        order_id__in=order_ids,
        action='stock_export',
    ).order_by('order_id', 'created_at', 'id').values_list('order_id', 'created_at')
    for order_id, created_at in export_histories.iterator():
        first_export_times.setdefault(order_id, created_at)

    missing_order_ids = [
        order_id for order_id in order_ids
        if order_id not in first_export_times
    ]
    if missing_order_ids:
        transition_histories = OrderEditHistory.objects.filter(
            order_id__in=missing_order_ids,
            status_after__in=(4, 5),
        ).order_by('order_id', 'created_at', 'id').values_list('order_id', 'created_at')
        for order_id, created_at in transition_histories.iterator():
            first_export_times.setdefault(order_id, created_at)

    default_timezone = timezone.get_default_timezone()
    for order in exported_orders:
        exported_at = first_export_times.get(order.id)
        if exported_at is None and order.order_date:
            exported_at = datetime.combine(order.order_date, time.min)
            if settings.USE_TZ:
                exported_at = timezone.make_aware(exported_at, default_timezone)
        order.exported_at = exported_at

    Order.objects.bulk_update(exported_orders, ['exported_at'], batch_size=1000)


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0028_quotationitem_cost_price'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='exported_at',
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name='Thời điểm xuất kho',
            ),
        ),
        migrations.RunPython(
            backfill_order_exported_at,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
