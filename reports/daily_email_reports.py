from collections import defaultdict
from datetime import date as date_type
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q, Sum
from django.template.loader import render_to_string
from django.utils import timezone

from finance.models import Receipt
from orders.models import Order, OrderItem, OrderReturn, OrderReturnItem
from reports.stock_alerts import parse_recipient_emails


class DailyEmailReportConfigurationError(ValueError):
    pass


def _decimal(value):
    return Decimal(str(value or 0))


def _money_text(value):
    return f'{int(round(_decimal(value))):,}'.replace(',', '.') + 'đ'


def _report_date(now=None):
    now = now or timezone.now()
    if isinstance(now, date_type) and not hasattr(now, 'hour'):
        return now
    if timezone.is_aware(now):
        now = timezone.localtime(now)
    return now.date()


def get_daily_email_report_recipients(config):
    user_emails = list(
        config.recipient_users.filter(is_active=True)
        .exclude(email='')
        .values_list('email', flat=True)
    )
    extra_emails, invalid_emails = parse_recipient_emails(config.email_recipients)
    if invalid_emails:
        raise DailyEmailReportConfigurationError(
            'Email không hợp lệ: ' + ', '.join(invalid_emails)
        )

    recipients = []
    seen = set()
    for raw_email in user_emails + extra_emails:
        parsed, invalid = parse_recipient_emails(raw_email)
        if invalid:
            raise DailyEmailReportConfigurationError(
                'Email không hợp lệ: ' + ', '.join(invalid)
            )
        if not parsed:
            continue
        email = parsed[0]
        if email in seen:
            continue
        seen.add(email)
        recipients.append(email)
    return recipients


def _product_unit_cost(product, cache):
    if not product:
        return Decimal('0')
    if product.id in cache:
        return cache[product.id]

    for candidate in (product.cost_price, product.import_price):
        value = _decimal(candidate)
        if value > 0:
            cache[product.id] = value
            return value

    combo_cost = Decimal('0')
    if product.is_combo:
        for combo_item in product.combo_items.select_related('product').all():
            component_cost = _product_unit_cost(combo_item.product, cache)
            combo_cost += component_cost * _decimal(combo_item.quantity)
    cache[product.id] = combo_cost
    return combo_cost


def _item_unit_cost(item, product_cost_cache):
    candidates = [item.cost_price]
    if item.variant_id:
        candidates.extend([item.variant.cost_price, item.variant.import_price])
    for candidate in candidates:
        value = _decimal(candidate)
        if value > 0:
            return value
    return _product_unit_cost(item.product if item.product_id else None, product_cost_cache)


def collect_daily_email_report_metrics(config, report_date=None):
    """Tổng hợp đúng ngày và trong toàn bộ cửa hàng thuộc thương hiệu."""
    report_date = report_date or _report_date()
    product_cost_cache = {}

    orders = list(
        Order.objects.filter(
            store__brand_id=config.brand_id,
            store__is_active=True,
            order_date=report_date,
            status__in=[4, 5],
        ).order_by('id')
    )
    order_ids = [order.id for order in orders]
    revenue = sum(
        (max(_decimal(order.final_amount), Decimal('0')) for order in orders),
        Decimal('0'),
    )

    sale_items = OrderItem.objects.filter(order_id__in=order_ids).select_related(
        'product', 'variant'
    )
    sales_cost = sum(
        (
            _item_unit_cost(item, product_cost_cache) * _decimal(item.quantity)
            for item in sale_items
        ),
        Decimal('0'),
    )

    brand_return_scope = (
        Q(order__store__brand_id=config.brand_id) |
        Q(order__isnull=True, warehouse__store__brand_id=config.brand_id) |
        Q(
            order__isnull=True,
            warehouse__isnull=True,
            customer__store__brand_id=config.brand_id,
        )
    )
    returns = OrderReturn.objects.filter(
        brand_return_scope,
        return_date=report_date,
    ).exclude(status=3).distinct()
    returns_total = _decimal(returns.aggregate(total=Sum('total_refund'))['total'])

    return_items = list(
        OrderReturnItem.objects.filter(order_return__in=returns).select_related(
            'product', 'order_return'
        )
    )
    original_order_ids = {
        item.order_return.order_id for item in return_items if item.order_return.order_id
    }
    returned_product_ids = {item.product_id for item in return_items if item.product_id}
    original_costs = defaultdict(lambda: {'quantity': Decimal('0'), 'cost': Decimal('0')})
    if original_order_ids and returned_product_ids:
        original_items = OrderItem.objects.filter(
            order_id__in=original_order_ids,
            product_id__in=returned_product_ids,
        ).select_related('product', 'variant')
        for item in original_items:
            quantity = _decimal(item.quantity)
            if quantity <= 0:
                continue
            key = (item.order_id, item.product_id)
            original_costs[key]['quantity'] += quantity
            original_costs[key]['cost'] += (
                _item_unit_cost(item, product_cost_cache) * quantity
            )

    return_cost = Decimal('0')
    for item in return_items:
        quantity = _decimal(item.quantity)
        original = original_costs.get((item.order_return.order_id, item.product_id))
        if original and original['quantity'] > 0:
            unit_cost = original['cost'] / original['quantity']
        else:
            unit_cost = _product_unit_cost(item.product, product_cost_cache)
        return_cost += unit_cost * quantity

    receipt_scope = (
        Q(store__brand_id=config.brand_id) |
        Q(store__isnull=True, order__store__brand_id=config.brand_id)
    )
    completed_receipts = Receipt.objects.filter(
        receipt_scope,
        receipt_date=report_date,
        status=1,
    ).distinct()
    money_received_by_cash_book = [
        {
            'cash_book_id': row['cash_book_id'],
            'name': row['cash_book__name'] or 'Chưa gán tài khoản',
            'amount': _decimal(row['amount']),
            'amount_text': _money_text(row['amount']),
        }
        for row in completed_receipts.order_by()
        .values('cash_book_id', 'cash_book__name')
        .annotate(amount=Sum('amount'))
        .order_by('-amount', 'cash_book__name', 'cash_book_id')
    ]
    total_money_received = sum(
        (row['amount'] for row in money_received_by_cash_book),
        Decimal('0'),
    )

    net_revenue = revenue - returns_total
    net_cost = sales_cost - return_cost
    gross_profit = net_revenue - net_cost
    gross_margin = (
        gross_profit / net_revenue * Decimal('100')
        if net_revenue > 0 else Decimal('0')
    )
    return {
        'report_date': report_date,
        'order_count': len(orders),
        'revenue': revenue,
        'returns_total': returns_total,
        'net_revenue': net_revenue,
        'sales_cost': sales_cost,
        'return_cost': return_cost,
        'net_cost': net_cost,
        'gross_profit': gross_profit,
        'gross_margin': gross_margin.quantize(Decimal('0.1')),
        'total_money_received': total_money_received,
        'money_received_by_cash_book': money_received_by_cash_book,
        'revenue_text': _money_text(revenue),
        'gross_profit_text': _money_text(gross_profit),
        'total_money_received_text': _money_text(total_money_received),
        'returns_total_text': _money_text(returns_total),
        'net_revenue_text': _money_text(net_revenue),
        'net_cost_text': _money_text(net_cost),
    }


def _ensure_email_backend_is_configured():
    backend = str(getattr(settings, 'EMAIL_BACKEND', '') or '')
    if backend.endswith('smtp.EmailBackend') and not getattr(settings, 'EMAIL_HOST_USER', ''):
        raise DailyEmailReportConfigurationError(
            'Máy chủ chưa cấu hình tài khoản gửi email (EMAIL_HOST_USER).'
        )


def send_daily_email_report(config, *, is_test=False, now=None, report_date=None):
    now = now or timezone.now()
    report_date = report_date or _report_date(now)
    recipients = get_daily_email_report_recipients(config)
    if not recipients:
        raise DailyEmailReportConfigurationError('Chưa có người nhận email hợp lệ.')

    _ensure_email_backend_is_configured()
    metrics = collect_daily_email_report_metrics(config, report_date=report_date)
    brand_name = config.brand.name
    subject_prefix = '[THỬ] ' if is_test else ''
    subject = (
        f'{subject_prefix}[IFShop] Báo cáo bán hàng ngày '
        f'{report_date:%d/%m/%Y} - {brand_name}'
    )
    from_email = (
        getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        or getattr(settings, 'EMAIL_HOST_USER', None)
    )
    context = {
        'brand_name': brand_name,
        'generated_at': now,
        'metrics': metrics,
        'is_test': is_test,
    }
    html_body = render_to_string('reports/email/daily_sales_report.html', context)
    text_lines = [
        f'BÁO CÁO BÁN HÀNG NGÀY - {brand_name}',
        f'Ngày báo cáo: {report_date:%d/%m/%Y}',
        f"Doanh thu: {metrics['revenue_text']}",
        f"Lợi nhuận gộp: {metrics['gross_profit_text']}",
        f"Tổng tiền về: {metrics['total_money_received_text']}",
    ]
    if metrics['money_received_by_cash_book']:
        text_lines.append('Chi tiết tiền về theo tài khoản:')
        text_lines.extend(
            f"- {row['name']}: {row['amount_text']}"
            for row in metrics['money_received_by_cash_book']
        )
    text_body = '\n'.join(text_lines)

    sent_recipients = []
    for email in recipients:
        message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[email],
        )
        message.attach_alternative(html_body, 'text/html')
        sent_count = message.send(fail_silently=False)
        if sent_count != 1:
            raise RuntimeError(
                f'Máy chủ email không xác nhận đã gửi thư tới {email}.'
            )
        sent_recipients.append(email)

    return {
        'sent': bool(sent_recipients),
        'recipient_count': len(recipients),
        'sent_recipient_count': len(sent_recipients),
        'recipients': sent_recipients,
        'metrics': metrics,
    }
