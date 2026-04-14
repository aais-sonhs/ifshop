from django.db import migrations, models
import django.db.models.deletion


def migrate_location_data(apps, schema_editor):
    """Migrate existing location text values to ProductLocation records"""
    Product = apps.get_model('products', 'Product')
    ProductLocation = apps.get_model('products', 'ProductLocation')
    
    # Collect distinct non-empty location strings
    locations = set()
    for p in Product.objects.exclude(old_location__isnull=True).exclude(old_location=''):
        locations.add(p.old_location.strip())
    
    # Create ProductLocation records and map name -> id
    loc_map = {}
    for loc_name in locations:
        obj, _ = ProductLocation.objects.get_or_create(name=loc_name)
        loc_map[loc_name] = obj.id
    
    # Update products with FK
    for p in Product.objects.exclude(old_location__isnull=True).exclude(old_location=''):
        loc_id = loc_map.get(p.old_location.strip())
        if loc_id:
            Product.objects.filter(id=p.id).update(location_id=loc_id)


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0013_update_product_price_fields"),
    ]

    operations = [
        # 1. Create ProductLocation model
        migrations.CreateModel(
            name="ProductLocation",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True, verbose_name="Tên vị trí")),
                ("is_active", models.BooleanField(default=True, verbose_name="Đang hoạt động")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "product_locations",
                "verbose_name": "Vị trí sản phẩm",
                "verbose_name_plural": "Vị trí sản phẩm",
                "ordering": ["name"],
            },
        ),
        # 2. Add specification field
        migrations.AddField(
            model_name="product",
            name="specification",
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name="Quy cách sản phẩm"),
        ),
        # 3. Rename old location to old_location temporarily
        migrations.RenameField(
            model_name="product",
            old_name="location",
            new_name="old_location",
        ),
        # 4. Add new location FK field
        migrations.AddField(
            model_name="product",
            name="location",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="products",
                to="products.productlocation",
                verbose_name="Vị trí sản phẩm",
            ),
        ),
        # 5. Migrate data from old_location text to location FK
        migrations.RunPython(migrate_location_data, migrations.RunPython.noop),
        # 6. Remove old_location field
        migrations.RemoveField(
            model_name="product",
            name="old_location",
        ),
    ]
