"""Expense Views — Phase 7 + Saraf & USD"""
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Min, Max
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction as db_transaction

from .models import ExpenseCategory, Expense
from .forms import ExpenseCategoryForm, ExpenseForm
from apps.settings_app.models import BusinessSettings  # ← NEW
from apps.core.jalali import to_jalali_str, jalali_str_to_gregorian, jalali_month_range_str


# ══════════════════════════════════════════════════════════════
# EXPENSE LIST
# ══════════════════════════════════════════════════════════════

@login_required
def expense_list(request):
    search       = request.GET.get('q', '').strip()
    cat_filter   = request.GET.get('category', '')
    date_from    = request.GET.get('date_from', '')  # Jalali string typed by user
    date_to      = request.GET.get('date_to', '')     # Jalali string typed by user
    month_filter = request.GET.get('month', '')

    qs = Expense.objects.filter(
        is_deleted=False, status='approved'
    ).select_related('category', 'created_by', 'banker')

    if search:
        qs = qs.filter(
            Q(title__icontains=search) |
            Q(paid_to__icontains=search) |
            Q(description__icontains=search)
        )
    if cat_filter:
        qs = qs.filter(category_id=cat_filter)

    # Convert Jalali filter inputs to Gregorian before filtering the DB.
    # If conversion fails (invalid/partial typing), that filter is simply skipped.
    if date_from:
        try:
            qs = qs.filter(expense_date__gte=jalali_str_to_gregorian(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            qs = qs.filter(expense_date__lte=jalali_str_to_gregorian(date_to))
        except ValueError:
            pass

    if month_filter:
        try:
            year, month = month_filter.split('-')
            qs = qs.filter(
                expense_date__year=int(year),
                expense_date__month=int(month)
            )
        except (ValueError, AttributeError):
            pass

    # ── Separate AFN and USD totals ──
    afn_qs = qs.filter(currency='AFN')
    usd_qs = qs.filter(currency='USD')

    totals_afn = afn_qs.aggregate(
        total=Sum('amount'),
        count=Count('id'),
    )
    totals_usd = usd_qs.aggregate(
        total=Sum('amount'),
        count=Count('id'),
    )
    total_count = qs.count()

    cat_totals = qs.values(
        'category__name'
    ).annotate(
        total_afn=Sum('amount_afn'),
        count=Count('id')
    ).order_by('-total_afn')

    paginator = Paginator(qs.order_by('-expense_date', '-created_at'), 25)
    page = paginator.get_page(request.GET.get('page'))

    categories = ExpenseCategory.objects.filter(
        is_active=True, is_deleted=False
    ).order_by('name')

    # Saraf debts summary
    saraf_debts = Expense.objects.filter(
        is_deleted=False,
        status='approved',
        payment_method='saraf',
        saraf_settled=False,
        saraf_debt_amount__gt=0,
    ).select_related('banker').values(
        'banker__name', 'banker__id', 'currency'
    ).annotate(
        total_debt=Sum('saraf_debt_amount')
    ).order_by('banker__name', 'currency')

    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'expenses/expense_list.html', {
        'page_title':   'مصارف',
        'expenses':     page,
        'search':       search,
        'cat_filter':   cat_filter,
        'date_from':    date_from,
        'date_to':      date_to,
        'month_filter': month_filter,
        'totals_afn':   totals_afn,
        'totals_usd':   totals_usd,
        'total_count':  total_count,
        'cat_totals':   cat_totals,
        'categories':   categories,
        'saraf_debts':  saraf_debts,
        'current_jalali_year': current_jalali_year,
    })


# ══════════════════════════════════════════════════════════════
# EXPENSE CREATE
# ══════════════════════════════════════════════════════════════

@login_required
def expense_create(request):
    form = ExpenseForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            with db_transaction.atomic():
                expense = form.save(commit=False)
                expense.created_by = request.user
                expense.status     = Expense.Status.APPROVED

                currency       = form.cleaned_data['currency']
                amount         = form.cleaned_data['amount']
                payment_method = form.cleaned_data['payment_method']

                # ── FIX: store amount_afn only for AFN expenses ──
                if currency == 'AFN':
                    expense.amount_afn    = amount
                    expense.exchange_rate = Decimal('1')
                else:
                    expense.amount_afn    = Decimal('0')
                    expense.exchange_rate = Decimal('1')

                if payment_method == 'saraf':
                    banker     = form.cleaned_data['banker']
                    saraf_paid = form.cleaned_data.get('saraf_paid_amount') or Decimal('0')
                    saraf_debt = amount - saraf_paid

                    expense.saraf_paid_amount = saraf_paid
                    expense.saraf_debt_amount = saraf_debt
                    expense.saraf_settled     = (saraf_debt <= 0)
                    expense.save()

                    from apps.banker.services import BankerService
                    if amount > 0:
                        BankerService.apply_expense_payment(
                            banker=banker,
                            amount=amount,
                            currency=currency,
                            exchange_rate=Decimal('1'),
                            expense=expense,
                            transaction_date=expense.expense_date,
                            user=request.user,
                        )
                else:
                    expense.banker            = None
                    expense.saraf_paid_amount = Decimal('0')
                    expense.saraf_debt_amount = Decimal('0')
                    expense.saraf_settled     = True
                    expense.save()

                sym = '$' if currency == 'USD' else '؋'
                messages.success(
                    request,
                    f'مصرف «{expense.title}» به مبلغ {amount:,.2f} {sym} ثبت شد.'
                )
                if request.POST.get('save_and_new'):
                    return redirect('expenses:expense_create')
                return redirect('expenses:expense_list')

        except Exception as e:
            messages.error(request, str(e))

    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'expenses/expense_form.html', {
        'page_title':     'ثبت مصرف جدید',
        'form':           form,
        'action':         'ثبت',
        'default_currency': BusinessSettings.get_solo().default_currency,  # ← NEW
        'current_jalali_year': current_jalali_year,
    })


# ══════════════════════════════════════════════════════════════
# EXPENSE EDIT
# ══════════════════════════════════════════════════════════════

@login_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk, is_deleted=False)
    form = ExpenseForm(request.POST or None, instance=expense)
    if request.method == 'POST' and form.is_valid():
        try:
            with db_transaction.atomic():
                updated        = form.save(commit=False)
                currency       = form.cleaned_data['currency']
                amount         = form.cleaned_data['amount']
                payment_method = form.cleaned_data['payment_method']

                # ── FIX: store amount_afn only for AFN expenses ──
                if currency == 'AFN':
                    updated.amount_afn    = amount
                    updated.exchange_rate = Decimal('1')
                else:
                    updated.amount_afn    = Decimal('0')
                    updated.exchange_rate = Decimal('1')

                if payment_method == 'saraf':
                    banker     = form.cleaned_data['banker']
                    saraf_paid = form.cleaned_data.get('saraf_paid_amount') or Decimal('0')
                    saraf_debt = amount - saraf_paid
                    updated.saraf_paid_amount = saraf_paid
                    updated.saraf_debt_amount = saraf_debt
                    updated.saraf_settled     = (saraf_debt <= 0)
                else:
                    updated.banker            = None
                    updated.saraf_paid_amount = Decimal('0')
                    updated.saraf_debt_amount = Decimal('0')
                    updated.saraf_settled     = True

                updated.save()
                messages.success(request, f'مصرف «{expense.title}» ویرایش شد.')
                return redirect('expenses:expense_list')

        except Exception as e:
            messages.error(request, str(e))

    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'expenses/expense_form.html', {
        'page_title': 'ویرایش مصرف',
        'form':       form,
        'action':     'ویرایش',
        'object':     expense,
        'current_jalali_year': current_jalali_year,
    })


# ══════════════════════════════════════════════════════════════
# EXPENSE DELETE
# ══════════════════════════════════════════════════════════════

@login_required
@require_POST
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk, is_deleted=False)
    title = expense.title
    expense.is_deleted = True
    expense.deleted_at = timezone.now()
    expense.save(update_fields=['is_deleted', 'deleted_at'])
    messages.success(request, f'مصرف «{title}» حذف شد.')
    return redirect('expenses:expense_list')


# ══════════════════════════════════════════════════════════════
# SARAF DEBT SETTLEMENT
# ══════════════════════════════════════════════════════════════

@login_required
@require_POST
def settle_saraf_debt(request, pk):
    """Pay off outstanding saraf debt for an expense."""
    expense = get_object_or_404(
        Expense, pk=pk, is_deleted=False,
        payment_method='saraf', saraf_settled=False
    )

    pay_amount = Decimal(request.POST.get('pay_amount', '0') or '0')
    if pay_amount <= 0:
        messages.error(request, 'مبلغ پرداخت باید بیشتر از صفر باشد.')
        return redirect('expenses:expense_list')

    if pay_amount > expense.saraf_debt_amount:
        pay_amount = expense.saraf_debt_amount

    try:
        with db_transaction.atomic():
            from apps.banker.services import BankerService
            BankerService.record_transaction(
                banker=expense.banker,
                tx_type='given',
                amount=pay_amount,
                currency=expense.currency,
                exchange_rate=expense.exchange_rate,
                transaction_date=timezone.now().date(),
                notes=f'تسویه بدهی مصرف: {expense.title}',
                reference=str(expense.pk),
                user=request.user,
            )

            expense.saraf_debt_amount -= pay_amount
            expense.saraf_paid_amount += pay_amount
            if expense.saraf_debt_amount <= 0:
                expense.saraf_debt_amount = Decimal('0')
                expense.saraf_settled     = True
            expense.save(update_fields=[
                'saraf_debt_amount', 'saraf_paid_amount',
                'saraf_settled', 'updated_at'
            ])

        sym = '$' if expense.currency == 'USD' else '؋'
        messages.success(
            request,
            f'{pay_amount:,.2f} {sym} بدهی مصرف «{expense.title}» '
            f'به صراف «{expense.banker.name}» پرداخت شد.'
        )
    except Exception as e:
        messages.error(request, str(e))

    return redirect('expenses:expense_list')


# ══════════════════════════════════════════════════════════════
# EXPENSE REPORT (Jalali year/month grouping)
# ══════════════════════════════════════════════════════════════

JALALI_MONTH_NAMES = [
    '', 'حمل', 'ثور', 'جوزا', 'سرطان', 'اسد', 'سنبله',
    'میزان', 'عقرب', 'قوس', 'جدی', 'دلو', 'حوت'
]


@login_required
def expense_report(request):
    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    year_param = request.GET.get('year')
    try:
        year = int(year_param) if year_param else current_jalali_year
    except (ValueError, TypeError):
        year = current_jalali_year

    # ── Bucket every approved expense by its JALALI year/month ──
    # The DB only stores Gregorian dates, so grouping is done here in
    # Python by converting each expense_date via the existing
    # to_jalali_str() helper. This naturally works correctly on every
    # previously-stored record too — old Gregorian dates convert to
    # their correct Jalali year/month exactly the same way, no
    # migration or backfill needed.
    monthly_totals = {
        m: {'total': Decimal('0'), 'total_usd': Decimal('0')}
        for m in range(1, 13)
    }
    category_totals_map = {}

    expenses_qs = Expense.objects.filter(
        is_deleted=False,
        status='approved',
    ).select_related('category')

    for expense in expenses_qs:
        j_year, j_month, _ = (int(p) for p in to_jalali_str(expense.expense_date).split('/'))
        if j_year != year:
            continue

        bucket = monthly_totals[j_month]
        bucket['total'] += expense.amount_afn
        if expense.currency == 'USD':
            bucket['total_usd'] += expense.amount

        cat_name = expense.category.name if expense.category else None
        cat_key = cat_name or '__none__'
        if cat_key not in category_totals_map:
            category_totals_map[cat_key] = {
                'category__name': cat_name,
                'total':          Decimal('0'),
                'total_usd':      Decimal('0'),
                'count':          0,
            }
        cat_bucket = category_totals_map[cat_key]
        cat_bucket['total'] += expense.amount_afn
        if expense.currency == 'USD':
            cat_bucket['total_usd'] += expense.amount
        cat_bucket['count'] += 1

    monthly_data = []
    for m in range(1, 13):
        date_from_str, date_to_str = jalali_month_range_str(year, m)
        monthly_data.append({
            'month':      m,
            'month_name': JALALI_MONTH_NAMES[m],
            'total':      monthly_totals[m]['total'],
            'total_usd':  monthly_totals[m]['total_usd'],
            'date_from':  date_from_str,
            'date_to':    date_to_str,
        })

    category_totals = sorted(
        category_totals_map.values(),
        key=lambda c: c['total'],
        reverse=True,
    )

    year_total = sum(m['total'] for m in monthly_data)
    year_total_usd = sum(m['total_usd'] for m in monthly_data)

    # ── Available years: derive Jalali years from the earliest/latest
    #    stored expense_date, so old records (any Gregorian date) are
    #    always covered without needing per-row iteration. ──
    date_bounds = Expense.objects.filter(is_deleted=False).aggregate(
        min_date=Min('expense_date'), max_date=Max('expense_date')
    )
    available_years = []
    if date_bounds['min_date'] and date_bounds['max_date']:
        min_j_year = int(to_jalali_str(date_bounds['min_date']).split('/')[0])
        max_j_year = int(to_jalali_str(date_bounds['max_date']).split('/')[0])
        available_years = list(range(min_j_year, max_j_year + 1))
    if year not in available_years:
        available_years.append(year)
    available_years = sorted(set(available_years), reverse=True)

    return render(request, 'expenses/expense_report.html', {
        'page_title':       'گزارش مصارف',
        'monthly_data':     monthly_data,
        'category_totals':  category_totals,
        'year':             year,
        'year_total':       year_total,
        'year_total_usd':   year_total_usd,
        'available_years':  available_years,
        'monthly_json':     str([float(m['total']) for m in monthly_data]),
        'monthly_labels':   str([m['month_name'] for m in monthly_data]),
        'monthly_json_usd': str([float(m['total_usd']) for m in monthly_data]),
    })


# ══════════════════════════════════════════════════════════════
# CATEGORY VIEWS
# ══════════════════════════════════════════════════════════════

@login_required
def category_list(request):
    categories = ExpenseCategory.objects.filter(
        is_deleted=False
    ).annotate(
        expense_count=Count('expenses'),
        total_amount=Sum('expenses__amount_afn'),
    ).order_by('name')

    return render(request, 'expenses/category_list.html', {
        'page_title': 'دسته‌بندی مصارف',
        'categories': categories,
    })


@login_required
def category_create(request):
    form = ExpenseCategoryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'دسته‌بندی ثبت شد.')
        return redirect('expenses:category_list')
    return render(request, 'expenses/category_form.html', {
        'page_title': 'دسته‌بندی جدید',
        'form':       form,
        'action':     'ثبت',
    })


@login_required
def category_edit(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk, is_deleted=False)
    form = ExpenseCategoryForm(request.POST or None, instance=category)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'دسته‌بندی ویرایش شد.')
        return redirect('expenses:category_list')
    return render(request, 'expenses/category_form.html', {
        'page_title': 'ویرایش دسته‌بندی',
        'form':       form,
        'action':     'ویرایش',
        'object':     category,
    })