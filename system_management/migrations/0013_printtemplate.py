from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('system_management', '0012_add_allow_negative_stock'),
    ]

    operations = [
        migrations.CreateModel(
            name='PrintTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('template_type', models.CharField(choices=[('k80', 'Hóa đơn K80'), ('a4', 'Hóa đơn A4'), ('quotation', 'Báo giá A5'), ('quotation_a4', 'Báo giá A4'), ('warranty', 'Phiếu bảo hành'), ('export', 'Phiếu xuất kho')], max_length=30, verbose_name='Loại mẫu')),
                ('title', models.CharField(max_length=255, verbose_name='Tiêu đề mẫu in')),
                ('header_note', models.TextField(blank=True, null=True, verbose_name='Ghi chú đầu phiếu')),
                ('terms', models.TextField(blank=True, null=True, verbose_name='Điều khoản / nội dung cuối phiếu')),
                ('footer_note', models.TextField(blank=True, null=True, verbose_name='Lời cảm ơn / chân phiếu')),
                ('show_brand_info', models.BooleanField(default=True, verbose_name='Hiện thông tin thương hiệu')),
                ('show_customer_info', models.BooleanField(default=True, verbose_name='Hiện thông tin khách hàng')),
                ('show_signatures', models.BooleanField(default=True, verbose_name='Hiện khu vực ký tên')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('brand', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='print_templates', to='system_management.brand', verbose_name='Thương hiệu')),
            ],
            options={
                'verbose_name': 'Mẫu in',
                'verbose_name_plural': 'Mẫu in',
                'db_table': 'print_templates',
                'ordering': ['template_type'],
                'unique_together': {('brand', 'template_type')},
            },
        ),
    ]
