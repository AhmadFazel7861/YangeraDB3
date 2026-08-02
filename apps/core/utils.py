"""
Shared utility functions used across the ERP.
"""
from django.conf import settings
from datetime import datetime
import zoneinfo


def get_kabul_now():
    """Return current datetime in Kabul timezone."""
    tz = zoneinfo.ZoneInfo('Asia/Kabul')
    return datetime.now(tz)


def format_currency(amount, currency='AFN'):
    """Format a decimal amount as Afghan currency string."""
    if amount is None:
        return '۰ افغانی'
    if currency == 'AFN':
        return f'{amount:,.0f} افغانی'
    elif currency == 'USD':
        return f'${amount:,.2f}'
    return f'{amount:,.2f}'


def persian_number(number):
    """Convert Western digits to Persian/Dari digits."""
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    western_digits = '0123456789'
    result = str(number)
    for w, p in zip(western_digits, persian_digits):
        result = result.replace(w, p)
    return result