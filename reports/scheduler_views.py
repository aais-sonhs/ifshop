import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from reports.email_scheduler import run_due_email_jobs


logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def api_run_scheduled_emails(request):
    """Endpoint nội bộ để cron kích hoạt một lượt kiểm tra email đến hạn."""
    try:
        result = run_due_email_jobs()
    except Exception:
        logger.exception('API lịch email không thể hoàn tất lượt kiểm tra.')
        return JsonResponse({
            'status': 'error',
            'message': 'Không thể chạy lịch email.',
        }, status=500)

    status_code = 500 if result['status'] == 'partial_error' else 200
    return JsonResponse(result, status=status_code)
