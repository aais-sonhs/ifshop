from django.db import migrations, models


PRINT_TEMPLATE_CHOICES = [
    ('k80', 'Hóa đơn K80'),
    ('a4', 'Hóa đơn A4'),
    ('quotation', 'Báo giá A5'),
    ('quotation_a4', 'Báo giá A4'),
    ('warranty', 'Phiếu bảo hành'),
    ('export', 'Phiếu xuất kho'),
    ('packing', 'Phiếu đóng hàng A5'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('system_management', '0022_brand_print_priority'),
    ]

    operations = [
        migrations.AlterField(
            model_name='printtemplate',
            name='template_type',
            field=models.CharField(
                choices=PRINT_TEMPLATE_CHOICES,
                max_length=30,
                verbose_name='Loại mẫu',
            ),
        ),
        migrations.AlterField(
            model_name='printtemplatehistory',
            name='template_type',
            field=models.CharField(
                choices=PRINT_TEMPLATE_CHOICES,
                max_length=30,
                verbose_name='Loại mẫu',
            ),
        ),
    ]
