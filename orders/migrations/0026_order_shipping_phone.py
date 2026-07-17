from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0025_warranty_certificate'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='shipping_phone',
            field=models.CharField(blank=True, max_length=30, null=True, verbose_name='SĐT nhận hàng'),
        ),
    ]
