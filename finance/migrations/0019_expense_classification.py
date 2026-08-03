import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0018_financial_plan_brand_scope'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExpenseClassification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_deleted', models.BooleanField(default=False, verbose_name='Đã xóa')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='Ngày xóa')),
                ('name', models.CharField(max_length=255, verbose_name='Tên phân loại chi')),
                ('description', models.TextField(blank=True, default='', verbose_name='Mô tả')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang sử dụng')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('brand', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='expense_classifications', to='system_management.brand', verbose_name='Thương hiệu')),
            ],
            options={
                'verbose_name': 'Phân loại chi',
                'verbose_name_plural': 'Phân loại chi',
                'db_table': 'expense_classifications',
                'ordering': ['name', 'id'],
            },
        ),
        migrations.AddField(
            model_name='payment',
            name='expense_classification',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payments', to='finance.expenseclassification', verbose_name='Phân loại chi'),
        ),
    ]
