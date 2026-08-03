import html
import re
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from finance.models import CashBook, FinancialPlan, Payment, Receipt
from core.store_utils import get_managed_store_ids


def _local_now(now=None):
    now = now or timezone.now()
    return timezone.localtime(now) if timezone.is_aware(now) else now


def _parse_lead_days(value):
    days = set()
    for raw_value in re.split(r'[,;\s]+', value or '3,7,15'):
        try:
            parsed = int(raw_value)
        except (TypeError, ValueError):
            continue
        if 0 <= parsed <= 365:
            days.add(parsed)
    return days or {3, 7, 15}


def _parse_recipients(plan):
    recipients = []
    for value in re.split(r'[,;\s]+', plan.alert_email_recipients or ''):
        value = value.strip()
        if value and '@' in value and value not in recipients:
            recipients.append(value)
    if not recipients and plan.created_by and plan.created_by.email:
        recipients.append(plan.created_by.email)
    if plan.store_id and plan.store.brand.owner_id:
        owner_email = plan.store.brand.owner.email
        if owner_email and owner_email not in recipients:
            recipients.append(owner_email)
    return recipients


def collect_financial_plan_alerts(plan, *, today=None):
    """Tính cảnh báo độc lập với HTTP để cron có thể chạy định kỳ."""
    today = today or date.today()
    lead_days = _parse_lead_days(plan.alert_lead_days)
    alerts = []
    schedules = plan.supplier_schedules.select_related('supplier', 'cash_book', 'payment').filter(status=0)
    for schedule in schedules:
        if schedule.payment and schedule.payment.status == 1:
            continue
        days_until_due = (schedule.due_date - today).days
        if days_until_due < 0:
            alerts.append({
                'level': 'danger',
                'date': schedule.due_date,
                'message': (
                    f'{schedule.code} của {schedule.supplier.name} quá hạn '
                    f'{abs(days_until_due)} ngày, dự chi {int(schedule.amount):,}đ.'
                ),
            })
        elif days_until_due in lead_days:
            alerts.append({
                'level': 'warning',
                'date': schedule.due_date,
                'message': (
                    f'{schedule.code} của {schedule.supplier.name} đến hạn sau '
                    f'{days_until_due} ngày, dự chi {int(schedule.amount):,}đ.'
                ),
            })

    receipt_filter = Q(status=1, receipt_date__range=(plan.start_date, plan.end_date))
    payment_filter = Q(status=1, payment_date__range=(plan.start_date, plan.end_date))
    if plan.store_id:
        receipt_filter &= Q(store_id=plan.store_id) | Q(
            store_id__isnull=True, order__store_id=plan.store_id,
        )
        payment_filter &= Q(store_id=plan.store_id) | Q(
            store_id__isnull=True, goods_receipt__warehouse__store_id=plan.store_id,
        )
    else:
        store_ids = get_managed_store_ids(plan.created_by) if plan.created_by else []
        receipt_filter &= Q(store_id__in=store_ids) | Q(
            store_id__isnull=True, order__store_id__in=store_ids,
        )
        payment_filter &= Q(store_id__in=store_ids) | Q(
            store_id__isnull=True, goods_receipt__warehouse__store_id__in=store_ids,
        )
    receipt_queryset = Receipt.objects.filter(receipt_filter)
    payment_queryset = Payment.objects.filter(payment_filter)
    receipt_actuals = {
        row['category_id']: Decimal(str(row['total'] or 0))
        for row in receipt_queryset.values('category_id').annotate(total=Sum('amount'))
    }
    payment_actuals = {
        row['category_id']: Decimal(str(row['total'] or 0))
        for row in payment_queryset.values('category_id').annotate(total=Sum('amount'))
    }
    monthly_actuals = {1: defaultdict(lambda: Decimal('0')), 2: defaultdict(lambda: Decimal('0'))}
    for receipt in receipt_queryset.values('receipt_date', 'category_id', 'amount'):
        month = date(receipt['receipt_date'].year, receipt['receipt_date'].month, 1)
        monthly_actuals[1][(month, receipt['category_id'])] += Decimal(str(receipt['amount'] or 0))
    for payment in payment_queryset.values('payment_date', 'category_id', 'amount'):
        month = date(payment['payment_date'].year, payment['payment_date'].month, 1)
        monthly_actuals[2][(month, payment['category_id'])] += Decimal(str(payment['amount'] or 0))

    cashbooks = list(CashBook.objects.filter(is_active=True))
    balances = {cashbook.id: Decimal(str(cashbook.balance or 0)) for cashbook in cashbooks}
    minimums = {cashbook.id: Decimal(str(cashbook.minimum_balance or 0)) for cashbook in cashbooks}
    events = defaultdict(lambda: defaultdict(lambda: Decimal('0')))
    scheduled_by_item = defaultdict(lambda: Decimal('0'))
    for schedule in schedules:
        if schedule.cash_book_id and (not schedule.payment or schedule.payment.status != 1):
            events[schedule.due_date][schedule.cash_book_id] -= Decimal(str(schedule.amount or 0))
            scheduled_by_item[schedule.plan_item_id] += Decimal(str(schedule.amount or 0))
    for item in plan.items.select_related('category').prefetch_related('allocations'):
        if not item.include_in_forecast or not item.cash_book_id:
            continue
        allocations = list(item.allocations.all())
        if allocations:
            scheduled_pool = scheduled_by_item[item.id]
            for allocation in allocations:
                remaining = max(
                    Decimal(str(allocation.planned_amount or 0))
                    - monthly_actuals[item.direction].get(
                        (allocation.month, item.category_id), Decimal('0')
                    ),
                    Decimal('0'),
                )
                if item.direction == 2:
                    covered_by_schedules = min(remaining, scheduled_pool)
                    remaining -= covered_by_schedules
                    scheduled_pool -= covered_by_schedules
                if not remaining:
                    continue
                month_end = date(
                    allocation.month.year,
                    allocation.month.month,
                    monthrange(allocation.month.year, allocation.month.month)[1],
                )
                event_date = allocation.expected_date or month_end
                event_date = min(max(event_date, today), plan.end_date)
                events[event_date][item.cash_book_id] += (
                    remaining if item.direction == 1 else -remaining
                )
        else:
            actuals = receipt_actuals if item.direction == 1 else payment_actuals
            remaining = max(
                Decimal(str(item.planned_amount or 0)) - actuals.get(item.category_id, Decimal('0')),
                Decimal('0'),
            )
            if item.direction == 2:
                remaining = max(remaining - scheduled_by_item[item.id], Decimal('0'))
            if not remaining:
                continue
            event_date = item.expected_date or plan.end_date
            event_date = min(max(event_date, today), plan.end_date)
            events[event_date][item.cash_book_id] += remaining if item.direction == 1 else -remaining

    shortage_seen = set()
    for event_date in sorted(events):
        for cashbook_id, delta in events[event_date].items():
            balances[cashbook_id] = balances.get(cashbook_id, Decimal('0')) + delta
            if balances[cashbook_id] < minimums.get(cashbook_id, Decimal('0')) and cashbook_id not in shortage_seen:
                shortage_seen.add(cashbook_id)
                cashbook = next((book for book in cashbooks if book.id == cashbook_id), None)
                alerts.append({
                    'level': 'danger' if balances[cashbook_id] < 0 else 'warning',
                    'date': event_date,
                    'message': (
                        f'{cashbook.name if cashbook else "Quỹ"} dự kiến còn '
                        f'{int(balances[cashbook_id]):,}đ, dưới mức tối thiểu '
                        f'{int(minimums.get(cashbook_id, 0)):,}đ.'
                    ),
                })
    return alerts


def _send_plan_alert_email(plan, alerts, recipients, now):
    subject = f'[IFSHOP] Cảnh báo tài chính - {plan.name}'
    rows = ''.join(
        '<li><strong>{}</strong> – {}</li>'.format(
            alert['date'].strftime('%d/%m/%Y'),
            html.escape(alert['message']),
        )
        for alert in alerts
    )
    body = (
        f'<h3>{html.escape(plan.name)}</h3>'
        f'<p>Hệ thống ghi nhận {len(alerts)} cảnh báo:</p><ul>{rows}</ul>'
        '<p>Vui lòng mở mục <b>Kế hoạch tài chính</b> để xem dự báo và xử lý.</p>'
    )
    message = EmailMultiAlternatives(
        subject=subject,
        body=re.sub(r'<[^>]+>', '', body),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    message.attach_alternative(body, 'text/html')
    message.send(fail_silently=False)
    plan.last_alert_sent = now


def run_due_financial_alerts(now=None):
    now = _local_now(now)
    totals = {'sent': 0, 'no_alert': 0, 'no_recipient': 0, 'skipped': 0, 'error': 0}
    results = []
    plan_ids = list(
        FinancialPlan.objects.filter(
            alert_enabled=True,
            status=1,
            end_date__gte=now.date(),
        ).values_list('id', flat=True)
    )
    for plan_id in plan_ids:
        try:
            with transaction.atomic():
                plan = FinancialPlan.objects.select_related(
                    'created_by', 'store', 'store__brand', 'store__brand__owner',
                ).select_for_update(of=('self',)).get(id=plan_id)
                if plan.last_alert_run_at:
                    last_run = _local_now(plan.last_alert_run_at)
                    if last_run.date() == now.date():
                        totals['skipped'] += 1
                        results.append({'plan_id': plan_id, 'status': 'skipped'})
                        continue
                plan.last_alert_run_at = now
                plan.save(update_fields=['last_alert_run_at', 'updated_at'])
            alerts = collect_financial_plan_alerts(plan, today=now.date())
            recipients = _parse_recipients(plan)
            if not alerts:
                status = 'no_alert'
            elif not recipients:
                status = 'no_recipient'
            else:
                _send_plan_alert_email(plan, alerts, recipients, now)
                plan.save(update_fields=['last_alert_sent', 'updated_at'])
                status = 'sent'
            totals[status] += 1
            results.append({'plan_id': plan_id, 'status': status, 'alert_count': len(alerts)})
        except Exception as exc:
            totals['error'] += 1
            results.append({'plan_id': plan_id, 'status': 'error', 'error': str(exc)})
    return {'totals': totals, 'results': results}
