from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0010_customer_customer_kind'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomerAddress',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(blank=True, default='', max_length=100, verbose_name='Tên điểm nhận')),
                ('address', models.TextField(verbose_name='Địa chỉ nhận hàng')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='delivery_addresses', to='customers.customer', verbose_name='Khách hàng')),
            ],
            options={
                'verbose_name': 'Địa chỉ nhận hàng của khách',
                'verbose_name_plural': 'Địa chỉ nhận hàng của khách',
                'db_table': 'customer_addresses',
                'ordering': ['sort_order', 'id'],
            },
        ),
    ]
