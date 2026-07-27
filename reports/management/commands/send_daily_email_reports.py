import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from reports.daily_email_reports import send_daily_email_report
from reports.models import DailyEmailReport


logger = logging.getLogger(__name__)


def _local_now(now=None):
    now = now or timezone.now()
    return timezone.localtime(now) if timezone.is_aware(now) else now


def daily_email_report_is_due(config, now=None):
    now = _local_now(now)
    if not config.is_active or not config.brand_id:
        return False
    if now.time() < config.send_time:
        return False
    if config.last_run_at:
        last_run_at = _local_now(config.last_run_at)
        if last_run_at.date() == now.date():
            return False
    return True


def process_daily_email_report(config_id, *, now=None, force=False):
    """Đánh dấu lần chạy trong transaction để nhiều tiến trình không gửi trùng."""
    now = _local_now(now)
    with transaction.atomic():
        config = DailyEmailReport.objects.select_for_update().get(id=config_id)
        if not force and not daily_email_report_is_due(config, now=now):
            return {'status': 'skipped', 'sent': False, 'recipient_count': 0}
        if not config.is_active or not config.brand_id:
            return {'status': 'skipped', 'sent': False, 'recipient_count': 0}
        config.last_run_at = now
        config.last_status = 'running'
        config.last_error = ''
        config.save(update_fields=['last_run_at', 'last_status', 'last_error', 'updated_at'])

    try:
        config = DailyEmailReport.objects.select_related('brand').get(id=config_id)
        result = send_daily_email_report(config, now=now)
        config.last_status = 'sent'
        config.last_sent = now
        config.last_error = ''
        config.save(update_fields=[
            'last_status',
            'last_sent',
            'last_error',
            'updated_at',
        ])
        return {
            'status': 'sent',
            'sent': True,
            'recipient_count': result['sent_recipient_count'],
        }
    except Exception as exc:
        logger.exception(
            'Gửi báo cáo email hằng ngày thất bại cho daily_email_report_id=%s',
            config_id,
        )
        DailyEmailReport.objects.filter(id=config_id).update(
            last_status='error',
            last_error=str(exc),
            updated_at=now,
        )
        return {
            'status': 'error',
            'sent': False,
            'recipient_count': 0,
            'error': str(exc),
        }


class Command(BaseCommand):
    help = 'Gửi các báo cáo email hằng ngày đã đến giờ và chưa chạy trong ngày.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Chạy ngay tất cả cấu hình đang bật, bỏ qua giờ gửi và lần chạy trong ngày.',
        )

    def handle(self, *args, **options):
        now = _local_now()
        force = bool(options.get('force'))
        configs = DailyEmailReport.objects.filter(
            is_active=True,
            brand__is_active=True,
        ).values_list('id', 'brand__name')

        totals = {'sent': 0, 'error': 0, 'skipped': 0}
        for config_id, brand_name in configs:
            result = process_daily_email_report(config_id, now=now, force=force)
            status = result['status']
            totals[status] = totals.get(status, 0) + 1
            if status == 'sent':
                self.stdout.write(self.style.SUCCESS(
                    f'{brand_name}: đã gửi báo cáo tới '
                    f'{result["recipient_count"]} người nhận.'
                ))
            elif status == 'error':
                self.stderr.write(self.style.ERROR(
                    f'{brand_name}: {result["error"]}'
                ))

        self.stdout.write(
            'Hoàn tất: '
            f'{totals.get("sent", 0)} đã gửi, '
            f'{totals.get("error", 0)} lỗi, '
            f'{totals.get("skipped", 0)} chưa đến giờ/đã chạy.'
        )
