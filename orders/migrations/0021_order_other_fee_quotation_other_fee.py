from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0020_orderitem_note'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='other_fee',
            field=models.DecimalField(decimal_places=0, default=0, max_digits=18, verbose_name='Chi phí khác'),
        ),
        migrations.AddField(
            model_name='quotation',
            name='other_fee',
            field=models.DecimalField(decimal_places=0, default=0, max_digits=18, verbose_name='Chi phí khác'),
        ),
    ]
