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

    result = []
    seen = set()
    for raw_email in recipient_emails + extra_emails:
        email = str(raw_email or '').strip().lower()
        if email and email not in seen:
            seen.add(email)
            result.append(email)
    return result


def get_stock_alert_category_ids(config):
    selected_ids = set(config.categories.values_list('id', flat=True))
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


def _quantity_text(value):
    number = Decimal(str(value or 0))
    if number == number.to_integral_value():
        return f'{int(number):,}'.replace(',', '.')
    return f'{number:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def collect_low_stock_rows(config):
    """Lấy tồn thấp theo từng kho trong đúng thương hiệu và danh mục cấu hình."""
    category_ids = get_stock_alert_category_ids(config)
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
    """Gửi một email tổng hợp; bản chạy lịch không gửi nếu không có tồn thấp."""
    now = now or timezone.now()
    recipients = get_stock_alert_recipients(config)
    if not recipients:
        raise StockAlertConfigurationError('Chưa có người nhận email hợp lệ.')
    if not config.categories.exists():
        raise StockAlertConfigurationError('Chưa chọn danh mục sản phẩm cần thông báo.')

    rows = collect_low_stock_rows(config)
    if not rows and not is_test:
        return {
            'sent': False,
            'row_count': 0,
            'recipient_count': len(recipients),
            'recipients': recipients,
        }

    _ensure_email_backend_is_configured()
    brand_name = config.brand.name if config.brand_id else 'IFShop'
    subject_prefix = '[THỬ] ' if is_test else ''
    subject = f'{subject_prefix}[IFShop] Cảnh báo tồn kho thấp - {brand_name} - {now:%d/%m/%Y}'
    context = {
        'brand_name': brand_name,
        'generated_at': now,
        'rows': rows,
        'row_count': len(rows),
        'is_test': is_test,
    }
    html_body = render_to_string('reports/email/low_stock_alert.html', context)

    if rows:
        text_lines = [
            f'CẢNH BÁO TỒN KHO THẤP - {brand_name}',
            f'Thời gian: {now:%d/%m/%Y %H:%M}',
            '',
        ]
        for row in rows:
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
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None),
        to=recipients,
    )
    message.attach_alternative(html_body, 'text/html')
    sent_count = message.send(fail_silently=False)
    if sent_count != 1:
        raise RuntimeError('Máy chủ email không xác nhận đã gửi thư.')

    return {
        'sent': True,
        'row_count': len(rows),
        'recipient_count': len(recipients),
        'recipients': recipients,
    }
