from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0014_productlocation_and_specification'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='note',
            field=models.TextField(blank=True, null=True, verbose_name='Ghi chú in đơn / báo giá'),
        ),
    ]
