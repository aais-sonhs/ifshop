import re

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def copy_existing_recipient_scopes(apps, schema_editor):
    StockAlert = apps.get_model('reports', 'StockAlert')
    StockAlertEmailRecipient = apps.get_model('reports', 'StockAlertEmailRecipient')

    for config in StockAlert.objects.all().iterator():
        category_ids = list(config.categories.values_list('id', flat=True))
        seen_emails = set()

        for user in config.recipient_users.exclude(email='').iterator():
            email = str(user.email or '').strip().lower()
            recipient, _ = StockAlertEmailRecipient.objects.get_or_create(
                stock_alert_id=config.id,
                user_id=user.id,
                defaults={'email': email},
            )
            recipient.categories.set(category_ids)
            seen_emails.add(email)

        for raw_email in re.split(r'[,;\s]+', str(config.email_recipients or '').strip()):
            email = raw_email.strip().lower()
            if not email or email in seen_emails:
                continue
            seen_emails.add(email)
            recipient, _ = StockAlertEmailRecipient.objects.get_or_create(
                stock_alert_id=config.id,
                user_id=None,
                email=email,
            )
            recipient.categories.set(category_ids)


def remove_copied_recipient_scopes(apps, schema_editor):
    StockAlertEmailRecipient = apps.get_model('reports', 'StockAlertEmailRecipient')
    StockAlertEmailRecipient.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('products', '0019_recalculate_weighted_purchase_cost'),
        ('reports', '0002_stock_alert_email_settings'),
    ]

    operations = [
        migrations.CreateModel(
            name='StockAlertEmailRecipient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(max_length=254, verbose_name='Email nhận cảnh báo')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('categories', models.ManyToManyField(blank=True, related_name='stock_alert_email_recipient_scopes', to='products.productcategory', verbose_name='Danh mục được nhận')),
                ('stock_alert', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='email_recipient_scopes', to='reports.stockalert', verbose_name='Cấu hình cảnh báo')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='stock_alert_email_scopes', to=settings.AUTH_USER_MODEL, verbose_name='Tài khoản hệ thống')),
            ],
            options={
                'verbose_name': 'Người nhận email cảnh báo tồn kho',
                'verbose_name_plural': 'Người nhận email cảnh báo tồn kho',
                'db_table': 'stock_alert_email_recipients',
            },
        ),
        migrations.AddConstraint(
            model_name='stockalertemailrecipient',
            constraint=models.UniqueConstraint(condition=models.Q(user__isnull=False), fields=('stock_alert', 'user'), name='uniq_stock_alert_recipient_user'),
        ),
        migrations.AddConstraint(
            model_name='stockalertemailrecipient',
            constraint=models.UniqueConstraint(condition=models.Q(user__isnull=True), fields=('stock_alert', 'email'), name='uniq_stock_alert_recipient_extra_email'),
        ),
        migrations.RunPython(copy_existing_recipient_scopes, remove_copied_recipient_scopes),
    ]
