from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0012_add_product_location"),
    ]

    operations = [
        # Rename listed_price → import_price (giữ data cũ)
        migrations.RenameField(
            model_name="product",
            old_name="listed_price",
            new_name="import_price",
        ),
        migrations.RenameField(
            model_name="productvariant",
            old_name="listed_price",
            new_name="import_price",
        ),
        # Đổi verbose_name
        migrations.AlterField(
            model_name="product",
            name="import_price",
            field=models.DecimalField(
                decimal_places=0, default=0, max_digits=15, verbose_name="Giá nhập"
            ),
        ),
        migrations.AlterField(
            model_name="productvariant",
            name="import_price",
            field=models.DecimalField(
                decimal_places=0, default=0, max_digits=15, verbose_name="Giá nhập"
            ),
        ),
        # Thêm giá sỉ KBH, sỉ BH
        migrations.AddField(
            model_name="product",
            name="wholesale_price_no_warranty",
            field=models.DecimalField(
                decimal_places=0, default=0, max_digits=15, verbose_name="Giá sỉ KBH"
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="wholesale_price_warranty",
            field=models.DecimalField(
                decimal_places=0, default=0, max_digits=15, verbose_name="Giá sỉ BH"
            ),
        ),
        migrations.AddField(
            model_name="productvariant",
            name="wholesale_price_no_warranty",
            field=models.DecimalField(
                decimal_places=0, default=0, max_digits=15, verbose_name="Giá sỉ KBH"
            ),
        ),
        migrations.AddField(
            model_name="productvariant",
            name="wholesale_price_warranty",
            field=models.DecimalField(
                decimal_places=0, default=0, max_digits=15, verbose_name="Giá sỉ BH"
            ),
        ),
        # Update verbose_name
        migrations.AlterField(
            model_name="product",
            name="cost_price",
            field=models.DecimalField(
                decimal_places=0, default=0, max_digits=15,
                verbose_name="Giá vốn (TB gia quyền)",
            ),
        ),
        migrations.AlterField(
            model_name="product",
            name="selling_price",
            field=models.DecimalField(
                decimal_places=0, default=0, max_digits=15, verbose_name="Giá bán lẻ"
            ),
        ),
        migrations.AlterField(
            model_name="productvariant",
            name="selling_price",
            field=models.DecimalField(
                decimal_places=0, default=0, max_digits=15, verbose_name="Giá bán lẻ"
            ),
        ),
    ]
