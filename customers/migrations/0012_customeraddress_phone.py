from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0011_customeraddress'),
    ]

    operations = [
        migrations.AddField(
            model_name='customeraddress',
            name='phone',
            field=models.CharField(blank=True, default='', max_length=30, verbose_name='SĐT nhận hàng'),
        ),
    ]
