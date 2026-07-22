import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from reports.models import StockAlert
from reports.stock_alerts import send_stock_alert_email


logger = logging.getLogger(__name__)


def stock_alert_is_due(config, now=None):
    now = now or timezone.now()
    if not config.is_active or not config.alert_on_min or not config.brand_id:
        return False
    if now.time() < config.send_time:
        return False
    if config.last_run_at and config.last_run_at.date() == now.date():
        return False
    return True


def process_stock_alert(config_id, *, now=None, force=False):
    """Claim cấu hình trong transaction trước khi gửi để nhiều tiến trình không gửi trùng."""
    now = now or timezone.now()
    with transaction.atomic():
        config = (
            StockAlert.objects.select_for_update()
            .get(id=config_id)
        )
        if not force and not stock_alert_is_due(config, now=now):
            return {'status': 'skipped', 'sent': False, 'row_count': 0}
        if not config.is_active or not config.brand_id:
            return {'status': 'skipped', 'sent': False, 'row_count': 0}
        config.last_run_at = now
        config.last_status = 'running'
        config.last_error = ''
        config.save(update_fields=['last_run_at', 'last_status', 'last_error', 'updated_at'])

    try:
        config = StockAlert.objects.select_related('brand').get(id=config_id)
        result = send_stock_alert_email(config, now=now)
        config.last_status = 'sent' if result['sent'] else 'no_low_stock'
        config.last_error = ''
        update_fields = ['last_status', 'last_error', 'updated_at']
        if result['sent']:
            config.last_sent = now
            update_fields.append('last_sent')
        config.save(update_fields=update_fields)
        return {
            'status': config.last_status,
            'sent': result['sent'],
            'row_count': result['row_count'],
            'recipient_count': result.get('sent_recipient_count', result['recipient_count']),
        }
    except Exception as exc:
        logger.exception('Gửi cảnh báo tồn kho thất bại cho stock_alert_id=%s', config_id)
        StockAlert.objects.filter(id=config_id).update(
            last_status='error',
            last_error=str(exc),
            updated_at=now,
        )
        return {
            'status': 'error',
            'sent': False,
            'row_count': 0,
            'error': str(exc),
        }


class Command(BaseCommand):
    help = 'Gửi các email cảnh báo tồn kho đã đến giờ và chưa chạy trong ngày.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Chạy ngay tất cả cấu hình đang bật, bỏ qua giờ gửi và lần chạy trong ngày.',
        )

    def handle(self, *args, **options):
        now = timezone.now()
        force = bool(options.get('force'))
        configs = StockAlert.objects.filter(
            is_active=True,
            alert_on_min=True,
            brand__isnull=False,
            brand__is_active=True,
        ).values_list('id', 'brand__name')

        totals = {'sent': 0, 'no_low_stock': 0, 'error': 0, 'skipped': 0}
        for config_id, brand_name in configs:
            result = process_stock_alert(config_id, now=now, force=force)
            status = result['status']
            totals[status] = totals.get(status, 0) + 1
            if status == 'sent':
                self.stdout.write(self.style.SUCCESS(
                    f'{brand_name}: đã gửi {result["row_count"]} sản phẩm tới '
                    f'{result["recipient_count"]} người nhận.'
                ))
            elif status == 'no_low_stock':
                self.stdout.write(f'{brand_name}: không có sản phẩm tồn thấp, không gửi email.')
            elif status == 'error':
                self.stderr.write(self.style.ERROR(f'{brand_name}: {result["error"]}'))

        self.stdout.write(
            'Hoàn tất: '
            f'{totals.get("sent", 0)} đã gửi, '
            f'{totals.get("no_low_stock", 0)} không có tồn thấp, '
            f'{totals.get("error", 0)} lỗi, '
            f'{totals.get("skipped", 0)} chưa đến giờ/đã chạy.'
        )
