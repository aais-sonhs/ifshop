from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0015_product_note'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockcheck',
            name='stock_applied',
            field=models.BooleanField(default=False, verbose_name='Đã cập nhật tồn kho'),
        ),
    ]
