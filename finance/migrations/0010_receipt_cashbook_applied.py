from django.db import migrations, models


def mark_existing_receipts(apps, schema_editor):
    Receipt = apps.get_model('finance', 'Receipt')
    Receipt.objects.filter(
        status=1,
        cash_book_id__isnull=False,
    ).exclude(
        description__icontains='tự động',
    ).exclude(
        description__icontains='thanh toán nhanh',
    ).update(cashbook_applied=True)


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0009_add_payment_method_option'),
    ]

    operations = [
        migrations.AddField(
            model_name='receipt',
            name='cashbook_applied',
            field=models.BooleanField(default=False, verbose_name='Đã ghi sổ quỹ'),
        ),
        migrations.RunPython(mark_existing_receipts, migrations.RunPython.noop),
    ]
