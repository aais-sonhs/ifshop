import re
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db.models import F
from django.template.loader import render_to_string
from django.utils import timezone

from products.models import ProductCategory, ProductStock


class StockAlertConfigurationError(ValueError):
    pass


def parse_recipient_emails(raw_value):
    """Tách, kiểm tra và loại trùng danh sách email nhập tay."""
    emails = []
    invalid = []
    seen = set()
    for value in re.split(r'[,;\s]+', str(raw_value or '').strip()):
        email = value.strip().lower()
        if not email or email in seen:
            continue
        try:
            validate_email(email)
        except ValidationError:
            invalid.append(value.strip())
            continue
        seen.add(email)
        emails.append(email)
    return emails, invalid


def get_stock_alert_recipients(config):
    scoped_recipients = list(
        config.email_recipient_scopes.select_related('user').all()
    )
    if scoped_recipients:
        raw_emails = []
        for recipient in scoped_recipients:
            if recipient.user_id:
                if not recipient.user.is_active:
                    continue
                raw_emails.append(recipient.user.email)
            else:
                raw_emails.append(recipient.email)
        return _normalize_recipient_emails(raw_emails)

    recipient_emails = list(
        config.recipient_users.filter(is_active=True)
        .exclude(email='')
        .values_list('email', flat=True)
    )
    extra_emails, invalid = parse_recipient_emails(config.email_recipients)
    if invalid:
        raise StockAlertConfigurationError(
            'Email không hợp lệ: ' + ', '.join(invalid)
        )

    return _normalize_recipient_emails(recipient_emails + extra_emails)


def _normalize_recipient_emails(raw_emails):
    result = []
    seen = set()
    invalid = []
    for raw_email in raw_emails:
        email = str(raw_email or '').strip().lower()
        if not email or email in seen:
            continue
        try:
            validate_email(email)
        except ValidationError:
            invalid.append(str(raw_email or '').strip())
            continue
        seen.add(email)
        result.append(email)
    if invalid:
        raise StockAlertConfigurationError(
            'Email không hợp lệ: ' + ', '.join(invalid)
        )
    return result


def get_stock_alert_category_ids(config, selected_ids=None):
    if selected_ids is None:
        selected_ids = config.categories.values_list('id', flat=True)
    selected_ids = set(selected_ids)
    if not selected_ids or not config.include_child_categories:
        return selected_ids

    children_by_parent = {}
    for category_id, parent_id in ProductCategory.objects.filter(is_active=True).values_list('id', 'parent_id'):
        children_by_parent.setdefault(parent_id, []).append(category_id)

    scoped_ids = set(selected_ids)
    pending = list(selected_ids)
    while pending:
        parent_id = pending.pop()
        for child_id in children_by_parent.get(parent_id, []):
            if child_id not in scoped_ids:
                scoped_ids.add(child_id)
                pending.append(child_id)
    return scoped_ids


def get_stock_alert_recipient_scopes(config):
    """Trả về phạm vi danh mục gộp theo email; hỗ trợ dữ liệu cấu hình cũ."""
    recipients = list(
        config.email_recipient_scopes.select_related('user')
        .prefetch_related('categories')
        .order_by('id')
    )
    if not recipients:
        legacy_category_ids = set(config.categories.values_list('id', flat=True))
        return [
            {'email': email, 'category_ids': set(legacy_category_ids)}
            for email in get_stock_alert_recipients(config)
        ]

    scopes_by_email = {}
    for recipient in recipients:
        if recipient.user_id:
            if not recipient.user.is_active:
                continue
            raw_email = recipient.user.email
        else:
            raw_email = recipient.email
        normalized = _normalize_recipient_emails([raw_email])
        if not normalized:
            continue
        email = normalized[0]
        scope = scopes_by_email.setdefault(email, {
            'email': email,
            'category_ids': set(),
        })
        scope['category_ids'].update(
            category.id for category in recipient.categories.all()
        )
    return list(scopes_by_email.values())


def _quantity_text(value):
    number = Decimal(str(value or 0))
    if number == number.to_integral_value():
        return f'{int(number):,}'.replace(',', '.')
    return f'{number:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def collect_low_stock_rows(config, category_ids=None):
    """Lấy tồn thấp theo từng kho trong đúng thương hiệu và danh mục cấu hình."""
    category_ids = get_stock_alert_category_ids(config, category_ids)
    if not config.brand_id or not category_ids:
        return []

    stocks = (
        ProductStock.objects.select_related(
            'product',
            'product__category',
            'product__supplier',
            'warehouse',
            'warehouse__store',
        )
        .filter(
            warehouse__store__brand_id=config.brand_id,
            warehouse__store__is_active=True,
            warehouse__is_active=True,
            product__category_id__in=category_ids,
            product__is_active=True,
            product__is_service=False,
            product__is_combo=False,
            quantity__lt=F('product__min_stock'),
        )
        .order_by(
            'warehouse__store__name',
            'warehouse__name',
            'product__category__name',
            'product__name',
            'product__code',
        )
    )

    rows = []
    for stock in stocks:
        current = Decimal(str(stock.quantity or 0))
        minimum = Decimal(str(stock.product.min_stock or 0))
        shortage = max(minimum - current, Decimal('0'))
        store_name = stock.warehouse.store.name if stock.warehouse.store_id else ''
        warehouse_label = f'{store_name} / {stock.warehouse.name}' if store_name else stock.warehouse.name
        rows.append({
            'category_id': stock.product.category_id,
            'store_name': store_name,
            'warehouse_name': stock.warehouse.name,
            'warehouse_label': warehouse_label,
            'category_name': stock.product.category.name if stock.product.category_id else '',
            'product_code': stock.product.code,
            'product_name': stock.product.name,
            'unit': stock.product.unit or '',
            'supplier_name': stock.product.supplier.name if stock.product.supplier_id else '',
            'current_stock': current,
            'minimum_stock': minimum,
            'shortage': shortage,
            'current_stock_text': _quantity_text(current),
            'minimum_stock_text': _quantity_text(minimum),
            'shortage_text': _quantity_text(shortage),
        })
    return rows


def _ensure_email_backend_is_configured():
    backend = str(getattr(settings, 'EMAIL_BACKEND', '') or '')
    if backend.endswith('smtp.EmailBackend') and not getattr(settings, 'EMAIL_HOST_USER', ''):
        raise StockAlertConfigurationError(
            'Máy chủ chưa cấu hình tài khoản gửi email (EMAIL_HOST_USER).'
        )


def send_stock_alert_email(config, *, is_test=False, now=None):
    """Gửi email riêng cho từng người nhận theo phạm vi danh mục của họ."""
    now = now or timezone.now()
    recipient_scopes = get_stock_alert_recipient_scopes(config)
    if not recipient_scopes:
        raise StockAlertConfigurationError('Chưa có người nhận email hợp lệ.')

    expanded_scopes = []
    for scope in recipient_scopes:
        if not scope['category_ids']:
            raise StockAlertConfigurationError(
                f"Email {scope['email']} chưa được chọn danh mục sản phẩm."
            )
        expanded_scopes.append({
            'email': scope['email'],
            'category_ids': get_stock_alert_category_ids(config, scope['category_ids']),
        })

    all_category_ids = set().union(*[
        scope['category_ids'] for scope in expanded_scopes
    ])
    rows = collect_low_stock_rows(config, all_category_ids)
    if not rows and not is_test:
        return {
            'sent': False,
            'row_count': 0,
            'sent_row_count': 0,
            'recipient_count': len(recipient_scopes),
            'sent_recipient_count': 0,
            'recipients': [],
        }

    _ensure_email_backend_is_configured()
    brand_name = config.brand.name if config.brand_id else 'IFShop'
    subject_prefix = '[THỬ] ' if is_test else ''
    subject = f'{subject_prefix}[IFShop] Cảnh báo tồn kho thấp - {brand_name} - {now:%d/%m/%Y}'
    from_email = (
        getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        or getattr(settings, 'EMAIL_HOST_USER', None)
    )
    sent_recipients = []
    sent_row_count = 0

    for scope in expanded_scopes:
        scoped_rows = [
            row for row in rows if row['category_id'] in scope['category_ids']
        ]
        if not scoped_rows and not is_test:
            continue

        context = {
            'brand_name': brand_name,
            'generated_at': now,
            'rows': scoped_rows,
            'row_count': len(scoped_rows),
            'is_test': is_test,
        }
        html_body = render_to_string('reports/email/low_stock_alert.html', context)

        if scoped_rows:
            text_lines = [
                f'CẢNH BÁO TỒN KHO THẤP - {brand_name}',
                f'Thời gian: {now:%d/%m/%Y %H:%M}',
                '',
            ]
            for row in scoped_rows:
                text_lines.append(
                    f"{row['warehouse_label']} | {row['product_code']} - {row['product_name']} | "
                    f"Tồn {row['current_stock_text']} | Tối thiểu {row['minimum_stock_text']} | "
                    f"Cần bổ sung {row['shortage_text']}"
                )
        else:
            text_lines = [
                f'EMAIL THỬ CẢNH BÁO TỒN KHO - {brand_name}',
                'Hiện không có sản phẩm nào dưới tồn kho tối thiểu trong các danh mục đã chọn.',
            ]

        message = EmailMultiAlternatives(
            subject=subject,
            body='\n'.join(text_lines),
            from_email=from_email,
            to=[scope['email']],
        )
        message.attach_alternative(html_body, 'text/html')
        sent_count = message.send(fail_silently=False)
        if sent_count != 1:
            raise RuntimeError(
                f"Máy chủ email không xác nhận đã gửi thư tới {scope['email']}."
            )
        sent_recipients.append(scope['email'])
        sent_row_count += len(scoped_rows)

    return {
        'sent': bool(sent_recipients),
        'row_count': len(rows),
        'sent_row_count': sent_row_count,
        'recipient_count': len(recipient_scopes),
        'sent_recipient_count': len(sent_recipients),
        'recipients': sent_recipients,
    }
