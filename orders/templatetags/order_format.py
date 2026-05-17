from decimal import Decimal, InvalidOperation

from django import template


register = template.Library()


def _to_decimal(value):
    try:
        return Decimal(str(value if value not in (None, '') else 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0')


def _format_vn_number(value, decimal_places=0):
    number = _to_decimal(value)
    if decimal_places == 0:
        formatted = f'{number.quantize(Decimal("1")):,.0f}'
    else:
        quantizer = Decimal('1').scaleb(-decimal_places)
        formatted = f'{number.quantize(quantizer):,.{decimal_places}f}'
        formatted = formatted.rstrip('0').rstrip('.')
    return formatted.replace(',', 'X').replace('.', ',').replace('X', '.')


@register.filter
def money_vnd(value):
    return _format_vn_number(value, 0)


@register.filter
def qty_vn(value):
    number = _to_decimal(value)
    decimal_places = 0 if number == number.quantize(Decimal('1')) else 2
    return _format_vn_number(number, decimal_places)
