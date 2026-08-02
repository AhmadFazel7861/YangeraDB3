"""
Capital Views — سرمایه دکان page
"""
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone

from .services import CapitalService
from apps.core.jalali import to_jalali_str, jalali_str_to_gregorian


@login_required
def capital_dashboard(request):
    """Main سرمایه دکان page."""

    # ── Date filter params ──
    date_from_str = request.GET.get('date_from', '')
    date_to_str   = request.GET.get('date_to', '')
    filter_mode   = request.GET.get('filter', 'all')   # all | month | range
    currency      = request.GET.get('currency', 'USD') # default = USD
    active_tab    = request.GET.get('tab', 'income')   # income | stock | expenses | banker | transfers

    today       = timezone.now().date()
    month_start = today.replace(day=1)

    date_from = None
    date_to   = None

    if filter_mode == 'month':
        date_from = month_start
        date_to   = today
    elif filter_mode == 'range':
        # date_from_str / date_to_str now arrive as Jalali strings
        # (e.g. "1405/04/16") from the dropdown pickers in the template.
        if date_from_str:
            try:
                date_from = jalali_str_to_gregorian(date_from_str)
            except ValueError:
                pass
        if date_to_str:
            try:
                date_to = jalali_str_to_gregorian(date_to_str)
            except ValueError:
                pass

    # ── Section data ──
    income_data  = CapitalService.get_shop_income(date_from, date_to, currency or None)
    stock_data   = CapitalService.get_stock_value()
    expense_data = CapitalService.get_expenses_summary(date_from, date_to)
    banker_data  = CapitalService.get_banker_balances()
    transfers    = CapitalService.get_transfers(date_from, date_to)

    # Transfer totals for the transfers section display
    transfer_total_afn = sum(t.amount for t in transfers if t.currency == 'AFN')
    transfer_total_usd = sum(t.amount for t in transfers if t.currency == 'USD')

    # KPI card totals — fetch combined (both currencies)
    income_all       = CapitalService.get_shop_income(date_from, date_to, None)
    income_afn_total = income_all['net_afn']
    income_usd_total = income_all['net_usd']
    net_afn_total    = income_all['net_afn']
    net_usd_total    = income_all['net_usd']

    # ── Net Worth Total ──
    # Mirrors ReportService.get_financial_summary() exactly:
    # = بدهی مشتریان + دخل دکان + مانده صرافان + موجودی انبار − بدهی به تامین‌کنندگان
    net_worth_data = CapitalService.get_net_worth()

    net_worth_usd = (
        net_worth_data['customer_debt_usd']   # بدهی مشتریان  (+)
        - net_worth_data['supplier_debt_usd']  # بدهی به تامین‌کنندگان  (−)
        + income_all['net_usd']                # دخل دکان (cash in hand)
        + banker_data['total_usd']             # مانده صرافان
        + stock_data['total_usd']              # موجودی گدام
    )
    net_worth_afn = (
        net_worth_data['customer_debt_afn']
        - net_worth_data['supplier_debt_afn']
        + income_all['net_afn']
        + banker_data['total_afn']
        + stock_data['total_afn']
    )

    # ── Bankers for transfer form ──
    from apps.banker.models import Banker
    bankers = Banker.objects.filter(is_active=True, is_deleted=False).order_by('name')

    current_jalali_year = int(to_jalali_str(today).split('/')[0])

    context = {
        'page_title': 'سرمایه دکان',

        # Filter state
        'filter_mode':   filter_mode,
        'date_from_str': date_from_str,
        'date_to_str':   date_to_str,
        'currency':      currency,
        'active_tab':    active_tab,
        'today':         today,
        'month_start':   month_start,
        'current_jalali_year': current_jalali_year,

        # Section data
        'income':             income_data,
        'income_all':         income_all,
        'income_afn_total':   income_afn_total,
        'income_usd_total':   income_usd_total,
        'net_afn_total':      net_afn_total,
        'net_usd_total':      net_usd_total,
        'stock':              stock_data,
        'expenses':           expense_data,
        'banker_data':        banker_data,
        'transfers':          list(transfers),
        'transfer_total_afn': transfer_total_afn,
        'transfer_total_usd': transfer_total_usd,

        # Net Worth
        'net_worth_usd':  net_worth_usd,
        'net_worth_afn':  net_worth_afn,
        'net_worth_data': net_worth_data,  # breakdown available in template if needed

        # Form
        'bankers':       bankers,
        'transfer_date': today,
    }
    return render(request, 'capital/dashboard.html', context)


@login_required
def transfer_to_banker(request):
    """POST — transfer دخل دکان to banker."""
    if request.method != 'POST':
        return redirect('capital:dashboard')

    from apps.banker.models import Banker
    from datetime import date
    from django.urls import reverse

    banker_id  = request.POST.get('banker_id')
    amount_str = request.POST.get('amount', '0')
    currency   = request.POST.get('currency', 'AFN')
    date_str   = request.POST.get('transfer_date', '')
    notes      = request.POST.get('notes', '')

    try:
        banker = Banker.objects.get(pk=banker_id, is_active=True, is_deleted=False)
    except Banker.DoesNotExist:
        messages.error(request, 'صراف انتخاب شده معتبر نیست.')
        return redirect('capital:dashboard')

    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            raise InvalidOperation()
    except (InvalidOperation, ValueError):
        messages.error(request, 'مبلغ وارد شده نامعتبر است.')
        return redirect('capital:dashboard')

    if currency not in ('AFN', 'USD'):
        messages.error(request, 'واحد پول نامعتبر است.')
        return redirect('capital:dashboard')

    try:
        transfer_date = jalali_str_to_gregorian(date_str) if date_str else timezone.now().date()
    except ValueError:
        transfer_date = timezone.now().date()

    try:
        CapitalService.transfer_to_banker(
            banker=banker,
            amount=amount,
            currency=currency,
            transfer_date=transfer_date,
            notes=notes,
            user=request.user,
        )
        sym = '$' if currency == 'USD' else '؋'
        messages.success(
            request,
            f'مبلغ {amount:,.2f} {sym} با موفقیت به صراف «{banker.name}» انتقال یافت.'
        )
    except Exception as e:
        messages.error(request, str(e))

    return redirect(reverse('capital:dashboard') + '?tab=transfers')