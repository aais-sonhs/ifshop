from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0011_alter_receipt_options'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='payment',
            options={
                'ordering': ['-payment_date', '-created_at', '-id'],
                'verbose_name': 'Phiếu chi',
                'verbose_name_plural': 'Phiếu chi',
            },
        ),
    ]
