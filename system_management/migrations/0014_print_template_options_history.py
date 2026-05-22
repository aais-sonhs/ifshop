from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('system_management', '0013_printtemplate'),
    ]

    operations = [
        migrations.AddField(
            model_name='printtemplate',
            name='show_brand_logo',
            field=models.BooleanField(default=True, verbose_name='Hiện logo thương hiệu'),
        ),
        migrations.AddField(
            model_name='printtemplate',
            name='show_discount',
            field=models.BooleanField(default=True, verbose_name='Hiện chiết khấu'),
        ),
        migrations.AddField(
            model_name='printtemplate',
            name='show_item_note',
            field=models.BooleanField(default=False, verbose_name='Hiện ghi chú sản phẩm'),
        ),
        migrations.AddField(
            model_name='printtemplate',
            name='show_order_note',
            field=models.BooleanField(default=True, verbose_name='Hiện ghi chú chứng từ'),
        ),
        migrations.AddField(
            model_name='printtemplate',
            name='show_payment_info',
            field=models.BooleanField(default=True, verbose_name='Hiện thông tin thanh toán'),
        ),
        migrations.AddField(
            model_name='printtemplate',
            name='show_product_code',
            field=models.BooleanField(default=True, verbose_name='Hiện mã sản phẩm'),
        ),
        migrations.AddField(
            model_name='printtemplate',
            name='show_product_images',
            field=models.BooleanField(default=False, verbose_name='Hiện ảnh sản phẩm'),
        ),
        migrations.AddField(
            model_name='printtemplate',
            name='show_shipping_fee',
            field=models.BooleanField(default=True, verbose_name='Hiện phí vận chuyển'),
        ),
        migrations.AddField(
            model_name='printtemplate',
            name='show_tax',
            field=models.BooleanField(default=True, verbose_name='Hiện thuế'),
        ),
        migrations.AddField(
            model_name='printtemplate',
            name='show_terms',
            field=models.BooleanField(default=True, verbose_name='Hiện điều khoản / nội dung cuối phiếu'),
        ),
        migrations.AddField(
            model_name='printtemplate',
            name='show_unit_price',
            field=models.BooleanField(default=True, verbose_name='Hiện đơn giá'),
        ),
        migrations.CreateModel(
            name='PrintTemplateHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('template_type', models.CharField(choices=[('k80', 'Hóa đơn K80'), ('a4', 'Hóa đơn A4'), ('quotation', 'Báo giá A5'), ('quotation_a4', 'Báo giá A4'), ('warranty', 'Phiếu bảo hành'), ('export', 'Phiếu xuất kho')], max_length=30, verbose_name='Loại mẫu')),
                ('title', models.CharField(max_length=255, verbose_name='Tiêu đề mẫu in')),
                ('snapshot', models.JSONField(default=dict, verbose_name='Dữ liệu mẫu in')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Thời gian lưu')),
                ('brand', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='print_template_histories', to='system_management.brand', verbose_name='Thương hiệu')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='print_template_histories', to=settings.AUTH_USER_MODEL, verbose_name='Người lưu')),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='histories', to='system_management.printtemplate', verbose_name='Mẫu in')),
            ],
            options={
                'verbose_name': 'Lịch sử mẫu in',
                'verbose_name_plural': 'Lịch sử mẫu in',
                'db_table': 'print_template_histories',
                'ordering': ['-created_at', '-id'],
            },
        ),
    ]
