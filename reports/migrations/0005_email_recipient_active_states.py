import re

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def copy_daily_email_report_recipients(apps, schema_editor):
    DailyEmailReport = apps.get_model('reports', 'DailyEmailReport')
    DailyEmailReportRecipient = apps.get_model('reports', 'DailyEmailReportRecipient')

    for config in DailyEmailReport.objects.all().iterator():
        seen_emails = set()
        for user in config.recipient_users.exclude(email='').iterator():
            email = str(user.email or '').strip().lower()
            if not email:
                continue
            DailyEmailReportRecipient.objects.get_or_create(
                daily_email_report_id=config.id,
                user_id=user.id,
                defaults={'email': email, 'is_active': True},
            )
            seen_emails.add(email)

        for raw_email in re.split(r'[,;\s]+', str(config.email_recipients or '').strip()):
            email = raw_email.strip().lower()
            if not email or email in seen_emails:
                continue
            seen_emails.add(email)
            DailyEmailReportRecipient.objects.get_or_create(
                daily_email_report_id=config.id,
                user_id=None,
                email=email,
                defaults={'is_active': True},
            )


def remove_daily_email_report_recipients(apps, schema_editor):
    DailyEmailReportRecipient = apps.get_model('reports', 'DailyEmailReportRecipient')
    DailyEmailReportRecipient.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('reports', '0004_dailyemailreport'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockalertemailrecipient',
            name='is_active',
            field=models.BooleanField(default=True, verbose_name='Đang nhận email'),
        ),
        migrations.CreateModel(
            name='DailyEmailReportRecipient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(max_length=254, verbose_name='Email nhận báo cáo')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang nhận email')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('daily_email_report', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recipient_settings', to='reports.dailyemailreport', verbose_name='Cấu hình báo cáo')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='daily_email_report_recipient_settings', to=settings.AUTH_USER_MODEL, verbose_name='Tài khoản hệ thống')),
            ],
            options={
                'verbose_name': 'Người nhận báo cáo email hằng ngày',
                'verbose_name_plural': 'Người nhận báo cáo email hằng ngày',
                'db_table': 'daily_email_report_recipients',
            },
        ),
        migrations.AddConstraint(
            model_name='dailyemailreportrecipient',
            constraint=models.UniqueConstraint(condition=models.Q(user__isnull=False), fields=('daily_email_report', 'user'), name='uniq_daily_email_report_recipient_user'),
        ),
        migrations.AddConstraint(
            model_name='dailyemailreportrecipient',
            constraint=models.UniqueConstraint(condition=models.Q(user__isnull=True), fields=('daily_email_report', 'email'), name='uniq_daily_email_report_recipient_extra_email'),
        ),
        migrations.RunPython(
            copy_daily_email_report_recipients,
            remove_daily_email_report_recipients,
        ),
    ]
