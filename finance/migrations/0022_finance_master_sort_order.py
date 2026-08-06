from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0021_backfill_order_return_payment_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='cashbook',
            name='sort_order',
            field=models.PositiveIntegerField(default=0, verbose_name='Thứ tự ưu tiên'),
        ),
        migrations.AddField(
            model_name='expenseclassification',
            name='sort_order',
            field=models.PositiveIntegerField(default=0, verbose_name='Thứ tự ưu tiên'),
        ),
        migrations.AddField(
            model_name='financecategory',
            name='sort_order',
            field=models.PositiveIntegerField(default=0, verbose_name='Thứ tự ưu tiên'),
        ),
        migrations.AlterModelOptions(
            name='cashbook',
            options={
                'ordering': ['sort_order', 'name', 'id'],
                'verbose_name': 'Quỹ',
                'verbose_name_plural': 'Quỹ',
            },
        ),
        migrations.AlterModelOptions(
            name='expenseclassification',
            options={
                'ordering': ['sort_order', 'name', 'id'],
                'verbose_name': 'Phân loại chi',
                'verbose_name_plural': 'Phân loại chi',
            },
        ),
        migrations.AlterModelOptions(
            name='financecategory',
            options={
                'ordering': ['type', 'sort_order', 'name', 'id'],
                'verbose_name': 'Danh mục thu chi',
                'verbose_name_plural': 'Danh mục thu chi',
            },
        ),
    ]
