"""
Banker System Views
"""
import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.http import JsonResponse
from django.core.exceptions import ValidationError

from .models import Banker, BankerTransaction
from .forms import BankerForm, BankerTransactionForm, BankerTransferForm
from .services import BankerService
from apps.core.jalali import to_jalali_str, jalali_str_to_gregorian


# ══════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════

@login_required
def banker_dashboard(request):
    stats = BankerService.get_dashboard_stats()
    bankers = Banker.objects.filter(is_deleted=False).order_by('name')
    recent_txs = BankerTransaction.objects.filter(
        is_deleted=False
    ).select_related('banker', 'created_by').order_by(
        '-transaction_date', '-created_at'
    )[:10]

    base_qs = BankerTransaction.objects.filter(is_deleted=False)

    def currency_totals(code):
        given = base_qs.filter(
            tx_type='given', currency=code
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        received = base_qs.filter(
            tx_type='received', currency=code
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        return given, received, given - received

    total_given_usd, total_received_usd, net_balance_usd = currency_totals('USD')
    total_given_eur, total_received_eur, net_balance_eur = currency_totals('EUR')
    total_given_irr, total_received_irr, net_balance_irr = currency_totals('IRR')

    bankers_with_usd = bankers.exclude(balance_usd=0)
    bankers_with_eur = bankers.exclude(balance_eur=0)
    bankers_with_irr = bankers.exclude(balance_irr=0)

    return render(request, 'banker/dashboard.html', {
        'page_title': 'صراف سیستم',
        **stats,
        'bankers': bankers,
        'recent_txs': recent_txs,
        'total_given_usd': total_given_usd,
        'total_received_usd': total_received_usd,
        'net_balance_usd': net_balance_usd,
        'bankers_with_usd': bankers_with_usd,
        'total_given_eur': total_given_eur,
        'total_received_eur': total_received_eur,
        'net_balance_eur': net_balance_eur,
        'bankers_with_eur': bankers_with_eur,
        'total_given_irr': total_given_irr,
        'total_received_irr': total_received_irr,
        'net_balance_irr': net_balance_irr,
        'bankers_with_irr': bankers_with_irr,
    })

# ══════════════════════════════════════════════════════════════
# BANKER CRUD
# ══════════════════════════════════════════════════════════════

@login_required
def banker_list(request):
    search = request.GET.get('q', '').strip()
    qs = Banker.objects.filter(is_deleted=False)
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(phone__icontains=search)
        )
    qs = qs.order_by('name')
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))

    totals = Banker.objects.filter(is_deleted=False).aggregate(
        total_afn=Sum('balance_afn'),
        total_usd=Sum('balance_usd'),
    )

    return render(request, 'banker/banker_list.html', {
        'page_title': 'لیست صرافان',
        'bankers': page,
        'search': search,
        'total': paginator.count,
        'totals': totals,
    })


@login_required
def banker_create(request):
    form = BankerForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        banker = form.save()
        messages.success(request, f'صراف «{banker.name}» ثبت شد.')
        if request.POST.get('save_and_new'):
            return redirect('banker:banker_create')
        return redirect('banker:banker_detail', pk=banker.pk)
    return render(request, 'banker/banker_form.html', {
        'page_title': 'صراف جدید',
        'form': form,
        'action': 'ثبت',
    })


@login_required
def banker_edit(request, pk):
    banker = get_object_or_404(Banker, pk=pk, is_deleted=False)
    form = BankerForm(request.POST or None, instance=banker)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'صراف «{banker.name}» ویرایش شد.')
        return redirect('banker:banker_detail', pk=banker.pk)
    return render(request, 'banker/banker_form.html', {
        'page_title': 'ویرایش صراف',
        'form': form,
        'action': 'ویرایش',
        'object': banker,
    })


@login_required
def banker_detail(request, pk):
    banker = get_object_or_404(Banker, pk=pk, is_deleted=False)
    txs = BankerTransaction.objects.filter(
        banker=banker, is_deleted=False
    ).select_related('created_by').order_by(
        '-transaction_date', '-created_at'
    )
    paginator = Paginator(txs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'banker/banker_detail.html', {
        'page_title': banker.name,
        'banker': banker,
        'transactions': page,
        'total': paginator.count,
    })


@login_required
@require_POST
def banker_toggle_active(request, pk):
    banker = get_object_or_404(Banker, pk=pk, is_deleted=False)
    banker.is_active = not banker.is_active
    banker.save(update_fields=['is_active', 'updated_at'])
    status = 'فعال' if banker.is_active else 'غیرفعال'
    messages.success(request, f'صراف «{banker.name}» {status} شد.')
    return redirect('banker:banker_list')


# ══════════════════════════════════════════════════════════════
# TRANSACTIONS
# ══════════════════════════════════════════════════════════════

@login_required
def transaction_create(request):
    banker_pk = request.GET.get('banker', None)
    form = BankerTransactionForm(
        request.POST or None,
        banker_pk=banker_pk,
    )

    if request.method == 'POST' and form.is_valid():
        cd = form.cleaned_data
        try:
            tx = BankerService.record_transaction(
                banker=cd['banker'],
                tx_type=cd['tx_type'],
                amount=cd['amount'],
                currency=cd['currency'],
                exchange_rate=cd.get('exchange_rate', Decimal('1')) or Decimal('1'),
                transaction_date=cd['transaction_date'],
                notes=cd.get('notes', ''),
                reference=cd.get('reference', ''),
                user=request.user,
            )
            direction = 'داده شده به' if cd['tx_type'] == 'given' else 'دریافت شده از'
            messages.success(
                request,
                f'{cd["amount"]:,.4f} {cd["currency"]} '
                f'{direction} صراف «{cd["banker"].name}» ثبت شد.'
            )
            return redirect('banker:banker_detail', pk=cd['banker'].pk)
        except Exception as e:
            messages.error(request, str(e))

    from apps.settings_app.models import BusinessSettings
    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])
    return render(request, 'banker/transaction_create.html', {
        'page_title': 'ثبت تراکنش صراف',
        'form': form,
        'default_currency': BusinessSettings.get_solo().default_currency,
        'current_jalali_year': current_jalali_year,
    })


@login_required
def banker_transfer(request):
    from_pk = request.GET.get('from')
    initial = {}
    if from_pk:
        try:
            initial['from_banker'] = Banker.objects.get(pk=from_pk, is_deleted=False)
        except Banker.DoesNotExist:
            pass

    form = BankerTransferForm(request.POST or None, initial=initial)

    if request.method == 'POST' and form.is_valid():
        cd = form.cleaned_data
        try:
            tx_out, tx_in = BankerService.transfer_between_bankers(
                from_banker=cd['from_banker'],
                to_banker=cd['to_banker'],
                amount=cd['amount'],
                currency=cd['currency'],
                transaction_date=cd['transaction_date'],
                notes=cd.get('notes', ''),
                reference=cd.get('reference', ''),
                user=request.user,
            )
            messages.success(
                request,
                f'{cd["amount"]:,.4f} {cd["currency"]} از صراف «{cd["from_banker"].name}» '
                f'به صراف «{cd["to_banker"].name}» منتقل شد.'
            )
            return redirect('banker:banker_detail', pk=cd['from_banker'].pk)
        except ValidationError as e:
            messages.error(request, e.messages[0] if hasattr(e, 'messages') else str(e))
        except Exception as e:
            messages.error(request, str(e))

    from apps.settings_app.models import BusinessSettings
    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])
    return render(request, 'banker/transaction_transfer.html', {
        'page_title': 'انتقال بین صرافان',
        'form': form,
        'default_currency': BusinessSettings.get_solo().default_currency,
        'current_jalali_year': current_jalali_year,
    })


@login_required
@require_POST
def transaction_delete(request, pk):
    tx = get_object_or_404(BankerTransaction, pk=pk, is_deleted=False)
    banker_pk = tx.banker.pk
    try:
        BankerService.delete_transaction(tx, user=request.user)
        messages.success(
            request,
            f'تراکنش {tx.amount:,.4f} {tx.currency} حذف و موجودی اصلاح شد.'
        )
    except Exception as e:
        messages.error(request, str(e))
    return redirect('banker:banker_detail', pk=banker_pk)


@login_required
@require_POST
def recalculate_balance(request, pk):
    banker = get_object_or_404(Banker, pk=pk, is_deleted=False)
    BankerService.recalculate_balance(banker)
    messages.success(
        request,
        f'موجودی صراف «{banker.name}» از صفر محاسبه شد.'
    )
    return redirect('banker:banker_detail', pk=pk)


# ══════════════════════════════════════════════════════════════
# LEDGER
# ══════════════════════════════════════════════════════════════

@login_required
def ledger(request, pk):
    banker = get_object_or_404(Banker, pk=pk, is_deleted=False)
    date_from = request.GET.get('date_from', '')  # Jalali string typed by user
    date_to   = request.GET.get('date_to', '')     # Jalali string typed by user

    # Convert Jalali filter inputs to Gregorian before handing them to the
    # service, which only understands plain Gregorian DateField comparisons.
    # If conversion fails (invalid/partial typing), that filter is skipped.
    date_from_greg = None
    if date_from:
        try:
            date_from_greg = jalali_str_to_gregorian(date_from)
        except ValueError:
            pass
    date_to_greg = None
    if date_to:
        try:
            date_to_greg = jalali_str_to_gregorian(date_to)
        except ValueError:
            pass

    data = BankerService.get_ledger(banker, date_from_greg, date_to_greg)

    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'banker/ledger.html', {
        'page_title': f'دفتر صراف — {banker.name}',
        'banker': banker,
        'date_from': date_from,
        'date_to': date_to,
        'current_jalali_year': current_jalali_year,
        **data,
    })


@login_required
def ledger_print(request, pk):
    banker = get_object_or_404(Banker, pk=pk, is_deleted=False)
    date_from = request.GET.get('date_from', '')  # Jalali string typed by user
    date_to   = request.GET.get('date_to', '')     # Jalali string typed by user

    date_from_greg = None
    if date_from:
        try:
            date_from_greg = jalali_str_to_gregorian(date_from)
        except ValueError:
            pass
    date_to_greg = None
    if date_to:
        try:
            date_to_greg = jalali_str_to_gregorian(date_to)
        except ValueError:
            pass

    data = BankerService.get_ledger(banker, date_from_greg, date_to_greg)

    return render(request, 'banker/print_ledger.html', {
        'banker': banker,
        'date_from': date_from,
        'date_to': date_to,
        **data,
    })


# ══════════════════════════════════════════════════════════════
# REPORTS
# ══════════════════════════════════════════════════════════════

@login_required
def report(request):
    date_from  = request.GET.get('date_from', '')  # Jalali string typed by user
    date_to    = request.GET.get('date_to', '')     # Jalali string typed by user
    banker_id  = request.GET.get('banker', '')
    currency_f = request.GET.get('currency', '')

    # Convert Jalali filter inputs to Gregorian before handing them to the
    # service, which only understands plain Gregorian DateField comparisons.
    # If conversion fails (invalid/partial typing), that filter is skipped —
    # same approach already used in ledger()/ledger_print() above.
    date_from_greg = None
    if date_from:
        try:
            date_from_greg = jalali_str_to_gregorian(date_from)
        except ValueError:
            pass
    date_to_greg = None
    if date_to:
        try:
            date_to_greg = jalali_str_to_gregorian(date_to)
        except ValueError:
            pass

    data = BankerService.get_report(
        date_from=date_from_greg,
        date_to=date_to_greg,
        banker_id=banker_id or None,
        currency=currency_f or None,
    )

    bankers = Banker.objects.filter(is_deleted=False).order_by('name')
    paginator = Paginator(data['transactions'], 30)
    page = paginator.get_page(request.GET.get('page'))

    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'banker/report.html', {
        'page_title': 'گزارش صراف',
        'transactions': page,
        'totals': data['totals'],
        'bankers': bankers,
        'date_from': date_from,
        'date_to': date_to,
        'banker_id': banker_id,
        'currency_f': currency_f,
        'total_count': paginator.count,
        'current_jalali_year': current_jalali_year,
    })


# ══════════════════════════════════════════════════════════════
# AJAX
# ══════════════════════════════════════════════════════════════

@login_required
def get_banker_balance(request):
    pk = request.GET.get('pk')
    try:
        banker = Banker.objects.get(pk=pk, is_deleted=False)
        return JsonResponse({
            'success': True,
            'name': banker.name,
            'balance_afn': float(banker.balance_afn),
            'balance_usd': float(banker.balance_usd),
        })
    except Banker.DoesNotExist:
        return JsonResponse({'success': False})