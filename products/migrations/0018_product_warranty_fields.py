from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0017_purchase_return'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='warranty_period_months',
            field=models.PositiveIntegerField(default=0, verbose_name='Kỳ hạn bảo hành (tháng)'),
        ),
        migrations.AddField(
            model_name='product',
            name='warranty_policy',
            field=models.TextField(blank=True, null=True, verbose_name='Chính sách bảo hành'),
        ),
    ]
