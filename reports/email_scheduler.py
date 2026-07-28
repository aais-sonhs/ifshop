import logging

from django.db import transaction
from django.utils import timezone

from reports.daily_email_reports import send_daily_email_report
from reports.models import DailyEmailReport, StockAlert
from reports.stock_alerts import send_stock_alert_email


logger = logging.getLogger(__name__)


def _local_now(now=None):
    now = now or timezone.now()
    return timezone.localtime(now) if timezone.is_aware(now) else now


def _empty_totals(statuses):
    return {status: 0 for status in statuses}


def stock_alert_is_due(config, now=None):
    now = _local_now(now)
    if not config.is_active or not config.alert_on_min or not config.brand_id:
        return False
    if now.time() < config.send_time:
        return False
    if config.last_run_at:
        last_run_at = _local_now(config.last_run_at)
        if last_run_at.date() == now.date():
            return False
    return True


def process_stock_alert(config_id, *, now=None, force=False):
    """Đánh dấu lần chạy trong transaction để nhiều lời gọi API không gửi trùng."""
    now = _local_now(now)
    with transaction.atomic():
        config = StockAlert.objects.select_for_update().get(id=config_id)
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
        logger.info(
            'Bắt đầu xử lý cảnh báo tồn kho: stock_alert_id=%s, brand=%s, '
            'thời_điểm=%s',
            config_id,
            config.brand.name,
            now.isoformat(),
        )
        result = send_stock_alert_email(config, now=now)
        config.last_status = 'sent' if result['sent'] else 'no_low_stock'
        config.last_error = ''
        update_fields = ['last_status', 'last_error', 'updated_at']
        if result['sent']:
            config.last_sent = now
            update_fields.append('last_sent')
        config.save(update_fields=update_fields)
        if result['sent']:
            logger.info(
                'Đã gửi cảnh báo tồn kho: stock_alert_id=%s, brand=%s, '
                'người_nhận=%s, số_dòng=%s, thời_điểm=%s',
                config_id,
                config.brand.name,
                result.get('sent_recipient_count', result['recipient_count']),
                result['row_count'],
                now.isoformat(),
            )
        else:
            logger.info(
                'Không gửi cảnh báo tồn kho vì không có sản phẩm tồn thấp: '
                'stock_alert_id=%s, brand=%s, thời_điểm=%s',
                config_id,
                config.brand.name,
                now.isoformat(),
            )
        return {
            'status': config.last_status,
            'sent': result['sent'],
            'row_count': result['row_count'],
            'recipient_count': result.get(
                'sent_recipient_count',
                result['recipient_count'],
            ),
        }
    except Exception as exc:
        logger.exception(
            'Gửi cảnh báo tồn kho thất bại cho stock_alert_id=%s',
            config_id,
        )
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
    """Đánh dấu lần chạy trong transaction để nhiều lời gọi API không gửi trùng."""
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
        logger.info(
            'Bắt đầu gửi báo cáo email hằng ngày: daily_email_report_id=%s, '
            'brand=%s, thời_điểm=%s',
            config_id,
            config.brand.name,
            now.isoformat(),
        )
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
        logger.info(
            'Đã gửi báo cáo email hằng ngày: daily_email_report_id=%s, '
            'brand=%s, người_nhận=%s, thời_điểm=%s',
            config_id,
            config.brand.name,
            result['sent_recipient_count'],
            now.isoformat(),
        )
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


def run_due_email_jobs(now=None):
    """Kiểm tra một lượt mọi cấu hình email đến hạn rồi trả kết quả tổng hợp."""
    now = _local_now(now)
    logger.info('Bắt đầu lượt email scheduler: thời_điểm=%s', now.isoformat())

    stock_totals = _empty_totals(('sent', 'no_low_stock', 'error', 'skipped'))
    stock_results = []
    stock_configs = StockAlert.objects.filter(
        is_active=True,
        alert_on_min=True,
        brand__isnull=False,
        brand__is_active=True,
    ).values_list('id', 'brand__name')
    for config_id, brand_name in stock_configs:
        result = process_stock_alert(config_id, now=now)
        stock_totals[result['status']] = stock_totals.get(result['status'], 0) + 1
        stock_results.append({
            'config_id': config_id,
            'brand_name': brand_name,
            'status': result['status'],
        })

    daily_totals = _empty_totals(('sent', 'error', 'skipped'))
    daily_results = []
    daily_configs = DailyEmailReport.objects.filter(
        is_active=True,
        brand__isnull=False,
        brand__is_active=True,
    ).values_list('id', 'brand__name')
    for config_id, brand_name in daily_configs:
        result = process_daily_email_report(config_id, now=now)
        daily_totals[result['status']] = daily_totals.get(result['status'], 0) + 1
        daily_results.append({
            'config_id': config_id,
            'brand_name': brand_name,
            'status': result['status'],
        })

    has_errors = bool(
        stock_totals.get('error') or daily_totals.get('error')
    )
    logger.info(
        'Hoàn tất lượt email scheduler: thời_điểm=%s, stock_alerts=%s, '
        'daily_email_reports=%s, có_lỗi=%s',
        now.isoformat(),
        stock_totals,
        daily_totals,
        has_errors,
    )
    return {
        'status': 'partial_error' if has_errors else 'ok',
        'checked_at': now.isoformat(),
        'stock_alerts': {
            'totals': stock_totals,
            'results': stock_results,
        },
        'daily_email_reports': {
            'totals': daily_totals,
            'results': daily_results,
        },
    }
