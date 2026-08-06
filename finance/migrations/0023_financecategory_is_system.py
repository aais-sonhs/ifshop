from django.db import migrations, models


SYSTEM_EXPENSE_CATEGORY_NAME = 'hoàn hàng'


def mark_order_return_category_as_system(apps, schema_editor):
    FinanceCategory = apps.get_model('finance', 'FinanceCategory')
    system_category_ids = [
        category.id
        for category in FinanceCategory.objects.filter(type=2)
        if ' '.join((category.name or '').split()).casefold()
        == SYSTEM_EXPENSE_CATEGORY_NAME
    ]
    FinanceCategory.objects.filter(id__in=system_category_ids).update(
        is_system=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0022_finance_master_sort_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='financecategory',
            name='is_system',
            field=models.BooleanField(
                default=False,
                editable=False,
                verbose_name='Danh mục hệ thống',
            ),
        ),
        migrations.RunPython(
            mark_order_return_category_as_system,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
