"""Reports Views — Phase 10"""
from decimal import Decimal
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from apps.core.jalali import to_jalali_str, jalali_str_to_gregorian

from .services import ReportService

PERIOD_CHOICES = [
    ('today',      'امروز'),
    ('yesterday',  'دیروز'),
    ('this_week',  'این هفته'),
    ('last_week',  'هفته گذشته'),
    ('this_month', 'این ماه'),
    ('last_month', 'ماه گذشته'),
    ('this_year',  'امسال'),
]

@login_required
def sales_report(request):
    period        = request.GET.get('period', 'this_month')
    date_from_raw = request.GET.get('date_from', '')
    date_to_raw   = request.GET.get('date_to', '')

    # date_from/date_to now arrive as Jalali strings ("1405/04/16") from the
    # optional dropdown pickers. Convert to real date objects here, in the
    # view — ReportService.get_date_range() is unchanged and still only
    # ever receives a date object or None for the custom period.
    custom_from = None
    if date_from_raw:
        try:
            custom_from = jalali_str_to_gregorian(date_from_raw)
        except ValueError:
            custom_from = None

    custom_to = None
    if date_to_raw:
        try:
            custom_to = jalali_str_to_gregorian(date_to_raw)
        except ValueError:
            custom_to = None

    df, dt = ReportService.get_date_range(
        period,
        custom_from=custom_from,
        custom_to=custom_to,
    )

    data = ReportService.get_sales_report(df, dt)

    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'reports/sales_report.html', {
        'page_title': 'گزارش فروش',
        'period': period,
        'period_choices': PERIOD_CHOICES,
        'date_from': to_jalali_str(df) if df else '',
        'date_to': to_jalali_str(dt) if dt else '',
        'current_jalali_year': current_jalali_year,
        **data,
    })


@login_required
def purchase_report(request):
    period        = request.GET.get('period', 'this_month')
    date_from_raw = request.GET.get('date_from', '')
    date_to_raw   = request.GET.get('date_to', '')

    custom_from = None
    if date_from_raw:
        try:
            custom_from = jalali_str_to_gregorian(date_from_raw)
        except ValueError:
            custom_from = None

    custom_to = None
    if date_to_raw:
        try:
            custom_to = jalali_str_to_gregorian(date_to_raw)
        except ValueError:
            custom_to = None

    df, dt = ReportService.get_date_range(
        period,
        custom_from=custom_from,
        custom_to=custom_to,
    )

    data = ReportService.get_purchase_report(df, dt)

    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'reports/purchase_report.html', {
        'page_title': 'گزارش خریداری',
        'period': period,
        'period_choices': PERIOD_CHOICES,
        'date_from': to_jalali_str(df) if df else '',
        'date_to': to_jalali_str(dt) if dt else '',
        'current_jalali_year': current_jalali_year,
        **data,
    })


@login_required
def profit_loss(request):
    period        = request.GET.get('period', 'this_month')
    date_from_raw = request.GET.get('date_from', '')
    date_to_raw   = request.GET.get('date_to', '')

    custom_from = None
    if date_from_raw:
        try:
            custom_from = jalali_str_to_gregorian(date_from_raw)
        except ValueError:
            custom_from = None

    custom_to = None
    if date_to_raw:
        try:
            custom_to = jalali_str_to_gregorian(date_to_raw)
        except ValueError:
            custom_to = None

    df, dt = ReportService.get_date_range(
        period,
        custom_from=custom_from,
        custom_to=custom_to,
    )

    data = ReportService.get_profit_loss(df, dt)

    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'reports/profit_loss.html', {
        'page_title': 'سود و زیان',
        'period': period,
        'period_choices': PERIOD_CHOICES,
        'date_from': to_jalali_str(df) if df else '',
        'date_to': to_jalali_str(dt) if dt else '',
        'current_jalali_year': current_jalali_year,
        **data,
    })


@login_required
def inventory_report(request):
    data = ReportService.get_inventory_report()
    return render(request, 'reports/inventory_report.html', {
        'page_title': 'گزارش موجودی انبار',
        **data,
    })


@login_required
def financial_summary(request):
    period        = request.GET.get('period', 'this_month')
    date_from_raw = request.GET.get('date_from', '')
    date_to_raw   = request.GET.get('date_to', '')

    custom_from = None
    if date_from_raw:
        try:
            custom_from = jalali_str_to_gregorian(date_from_raw)
        except ValueError:
            custom_from = None

    custom_to = None
    if date_to_raw:
        try:
            custom_to = jalali_str_to_gregorian(date_to_raw)
        except ValueError:
            custom_to = None

    df, dt = ReportService.get_date_range(
        period,
        custom_from=custom_from,
        custom_to=custom_to,
    )

    data = ReportService.get_financial_summary(df, dt)

    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'reports/financial_summary.html', {
        'page_title': 'خلاصه مالی',
        'period': period,
        'period_choices': PERIOD_CHOICES,
        'date_from': to_jalali_str(df) if df else '',
        'date_to': to_jalali_str(dt) if dt else '',
        'current_jalali_year': current_jalali_year,
        **data,
    })