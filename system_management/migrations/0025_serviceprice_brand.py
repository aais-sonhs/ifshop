import django.db.models.deletion
from django.db import migrations, models


def copy_legacy_prices_to_brands(apps, schema_editor):
    """Sao chép bảng giá chung hiện có thành bảng giá riêng cho từng công ty."""
    Brand = apps.get_model('system_management', 'Brand')
    ServicePrice = apps.get_model('system_management', 'ServicePrice')
    company_brand_ids = list(
        Brand.objects.filter(brand_type='company').values_list('id', flat=True)
    )
    if not company_brand_ids:
        return

    for service in ServicePrice.objects.filter(brand__isnull=True).iterator():
        ServicePrice.objects.bulk_create([
            ServicePrice(
                brand_id=brand_id,
                name=service.name,
                price=service.price,
                unit=service.unit,
                description=service.description,
                is_active=service.is_active,
            )
            for brand_id in company_brand_ids
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('system_management', '0024_brand_menu_visibility'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviceprice',
            name='brand',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='service_prices',
                to='system_management.brand',
                verbose_name='Thương hiệu',
            ),
        ),
        migrations.RunPython(
            copy_legacy_prices_to_brands,
            migrations.RunPython.noop,
        ),
    ]
