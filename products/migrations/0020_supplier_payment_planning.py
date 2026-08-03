from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0019_recalculate_weighted_purchase_cost'),
    ]

    operations = [
        migrations.AddField(
            model_name='supplier',
            name='payment_term_days',
            field=models.PositiveIntegerField(default=0, verbose_name='Số ngày được nợ'),
        ),
        migrations.AddField(
            model_name='supplier',
            name='payment_priority',
            field=models.IntegerField(
                choices=[
                    (1, 'Khẩn cấp'),
                    (2, 'Cao'),
                    (3, 'Bình thường'),
                    (4, 'Thấp'),
                ],
                default=3,
                verbose_name='Ưu tiên thanh toán',
            ),
        ),
    ]
