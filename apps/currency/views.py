"""Currency Views — Phase 8"""
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.http import JsonResponse

from .models import Currency, ExchangeRate
from .forms import ExchangeRateForm
from .services import CurrencyService


@login_required
def currency_list(request):
    """Show all currencies with their latest rates."""
    currencies = Currency.objects.filter(
        is_deleted=False
    ).order_by('sort_order')

    today = timezone.now().date()
    currency_data = []
    for cur in currencies:
        latest = ExchangeRate.objects.filter(
            currency=cur,
            rate_date__lte=today,
        ).order_by('-rate_date').first()
        currency_data.append({
            'currency': cur,
            'latest_rate': latest,
        })

    return render(request, 'currency/currency_list.html', {
        'page_title': 'ارزها و نرخ‌ها',
        'currency_data': currency_data,
        'today': today,
    })


@login_required
def rate_list(request):
    """Exchange rate history with filters."""
    currency_filter = request.GET.get('currency', '')
    date_from = request.GET.get('date_from', '')
    date_to   = request.GET.get('date_to', '')

    qs = ExchangeRate.objects.filter(
        is_deleted=False
    ).select_related('currency', 'created_by')

    if currency_filter:
        qs = qs.filter(currency_id=currency_filter)
    if date_from:
        qs = qs.filter(rate_date__gte=date_from)
    if date_to:
        qs = qs.filter(rate_date__lte=date_to)

    paginator = Paginator(
        qs.order_by('-rate_date', 'currency__sort_order'), 30
    )
    page = paginator.get_page(request.GET.get('page'))

    currencies = Currency.objects.filter(
        is_active=True, is_deleted=False, is_base=False
    ).order_by('sort_order')

    return render(request, 'currency/rate_list.html', {
        'page_title': 'تاریخچه نرخ ارز',
        'rates': page,
        'currencies': currencies,
        'currency_filter': currency_filter,
        'date_from': date_from,
        'date_to': date_to,
        'total': paginator.count,
    })


@login_required
def rate_create(request):
    form = ExchangeRateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        rate = form.save(commit=False)
        rate.created_by = request.user
        rate.save()
        messages.success(
            request,
            f'نرخ {rate.currency.code} برای {rate.rate_date}: '
            f'{rate.rate_to_afn:,.4f} افغانی ثبت شد.'
        )
        if request.POST.get('save_and_new'):
            return redirect('currency:rate_create')
        return redirect('currency:currency_list')
    return render(request, 'currency/rate_form.html', {
        'page_title': 'ثبت نرخ ارز',
        'form': form,
        'action': 'ثبت',
    })


@login_required
def rate_edit(request, pk):
    rate = get_object_or_404(ExchangeRate, pk=pk, is_deleted=False)
    form = ExchangeRateForm(request.POST or None, instance=rate)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'نرخ ارز ویرایش شد.')
        return redirect('currency:currency_list')
    return render(request, 'currency/rate_form.html', {
        'page_title': 'ویرایش نرخ ارز',
        'form': form,
        'action': 'ویرایش',
        'object': rate,
    })


@login_required
def get_rate_ajax(request):
    """AJAX: Get current rate for a currency."""
    currency_code = request.GET.get('code', '')
    date_str = request.GET.get('date', '')
    try:
        from datetime import date as date_type
        date = (
            date_type.fromisoformat(date_str)
            if date_str
            else timezone.now().date()
        )
        rate = CurrencyService.get_rate(currency_code, date)
        return JsonResponse({
            'success': True,
            'rate': float(rate),
            'currency': currency_code,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def convert_ajax(request):
    """AJAX: Convert between currencies."""
    try:
        amount = Decimal(request.GET.get('amount', '0'))
        from_currency = request.GET.get('from', 'AFN')
        to_currency   = request.GET.get('to', 'USD')
        date_str      = request.GET.get('date', '')

        from datetime import date as date_type
        date = (
            date_type.fromisoformat(date_str)
            if date_str
            else timezone.now().date()
        )

        # Convert to AFN first, then to target
        afn_amount = CurrencyService.to_afn(amount, from_currency, date)
        result     = CurrencyService.from_afn(afn_amount, to_currency, date)

        return JsonResponse({
            'success': True,
            'result': float(result),
            'from': from_currency,
            'to': to_currency,
            'rate': float(CurrencyService.get_rate(
                to_currency if from_currency == 'AFN' else from_currency,
                date
            )),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def setup_currencies(request):
    """One-time setup: create default currencies."""
    CurrencyService.initialize_default_currencies()
    messages.success(request, 'ارزهای پیش‌فرض ایجاد شدند.')
    return redirect('currency:currency_list')