from datetime import date, timedelta

from core.store_utils import get_company_brand_for_user
from system_management.models import BusinessConfig


DEFAULT_FINANCIAL_PERIOD_START_DAY = 1


def normalize_financial_period_start_day(value):
    """Chuẩn hóa ngày bắt đầu kỳ; chỉ 1-28 để mọi tháng đều hợp lệ."""
    try:
        start_day = int(value)
    except (TypeError, ValueError):
        return DEFAULT_FINANCIAL_PERIOD_START_DAY
    if 1 <= start_day <= 28:
        return start_day
    return DEFAULT_FINANCIAL_PERIOD_START_DAY


def get_financial_period_start_day(user):
    """Lấy mốc kỳ dùng chung theo công ty của người đang xem báo cáo."""
    store = None
    try:
        store = user.profile.store
    except Exception:
        pass
    brand = get_company_brand_for_user(user, store=store)
    config = BusinessConfig.get_config(brand=brand)
    return normalize_financial_period_start_day(config.financial_period_start_day)


def financial_month_bounds(year, month, start_day):
    """Kỳ mang nhãn YYYY-MM: ngày bắt đầu đến trước cùng ngày tháng sau."""
    start_day = normalize_financial_period_start_day(start_day)
    start = date(int(year), int(month), start_day)
    if start.month == 12:
        next_start = date(start.year + 1, 1, start_day)
    else:
        next_start = date(start.year, start.month + 1, start_day)
    return start, next_start - timedelta(days=1)


def financial_year_bounds(year, start_day):
    """Năm tài chính mang nhãn YYYY luôn bắt đầu trong tháng 1."""
    start_day = normalize_financial_period_start_day(start_day)
    start = date(int(year), 1, start_day)
    next_start = date(start.year + 1, 1, start_day)
    return start, next_start - timedelta(days=1)


def current_financial_month_bounds(today, start_day):
    """Trả kỳ tài chính theo tháng đang chứa `today`."""
    start_day = normalize_financial_period_start_day(start_day)
    year, month = today.year, today.month
    if today.day < start_day:
        if month == 1:
            year, month = year - 1, 12
        else:
            month -= 1
    return financial_month_bounds(year, month, start_day)


def financial_time_bucket(value, time_group, start_day):
    """Gom một ngày vào đúng tháng/năm tài chính mang nhãn ngày bắt đầu."""
    start_day = normalize_financial_period_start_day(start_day)
    value = value.date() if hasattr(value, 'date') else value
    if time_group == 'month':
        year, month = value.year, value.month
        if value.day < start_day:
            if month == 1:
                year, month = year - 1, 12
            else:
                month -= 1
        return f'{year:04d}-{month:02d}', f'{month:02d}/{year:04d}'
    if time_group == 'year':
        year = value.year if value >= date(value.year, 1, start_day) else value.year - 1
        return f'{year:04d}', f'{year:04d}'
    return value.strftime('%Y-%m-%d'), value.strftime('%d/%m/%Y')
