from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0010_receipt_cashbook_applied'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='receipt',
            options={
                'ordering': ['-receipt_date', '-id'],
                'verbose_name': 'Phiếu thu',
                'verbose_name_plural': 'Phiếu thu',
            },
        ),
    ]
