"""
Template filters:
  {{ some_date|jalali }}              -> '1405/04/11'         (for DateField)
  {{ some_datetime|jalali_datetime }} -> '1405/04/11 16:23'    (for DateTimeField)

Both convert Gregorian to Jalali (Shamsi) for DISPLAY only,
anywhere in any template, without touching the view or the DB.
"""
from django import template
from django.utils import timezone
from apps.core.jalali import to_jalali_str

register = template.Library()


@register.filter(name='jalali')
def jalali(value):
    """Usage in template: {{ invoice.invoice_date|jalali }} -> '1405/04/11'"""
    if not value:
        return ''
    try:
        return to_jalali_str(value)
    except Exception:
        return value


@register.filter(name='jalali_datetime')
def jalali_datetime(value):
    """
    Usage in template: {{ batch.created_at|jalali_datetime }} -> '1405/04/11 16:23'
    Accepts a DateTimeField value, converts to local timezone (Asia/Kabul)
    first, then converts the date part to Jalali and appends H:i time.
    """
    if not value:
        return ''
    try:
        local_dt = timezone.localtime(value)
        jalali_date_str = to_jalali_str(local_dt.date())
        return f'{jalali_date_str} {local_dt.strftime("%H:%M")}'
    except Exception:
        return value