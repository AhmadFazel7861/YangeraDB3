"""
Loans App Views
"""
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.banker.models import Banker
from apps.core.jalali import to_jalali_str
from .models import LoanPerson, LoanTransaction
from .forms import LoanPersonForm, GiveLoanForm, RepaymentForm
from .services import LoanService


def _active_bankers():
    return Banker.objects.filter(is_active=True, is_deleted=False).order_by('name')


# ─────────────────────────────────────────────────────────────────────────────
# Person list
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def person_list(request):
    search = request.GET.get('q', '').strip()
    qs = LoanPerson.objects.filter(is_deleted=False)
    if search:
        qs = qs.filter(
            Q(name__icontains=search) | Q(phone__icontains=search)
        )
    qs = qs.order_by('name')

    total_afn = sum(p.balance_afn for p in qs if p.balance_afn > 0)
    total_usd = sum(p.balance_usd for p in qs if p.balance_usd > 0)

    return render(request, 'loans/person_list.html', {
        'persons': qs,
        'search': search,
        'total': qs.count(),
        'total_outstanding_afn': total_afn,
        'total_outstanding_usd': total_usd,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Person create
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def person_create(request):
    form = LoanPersonForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        person = form.save()
        messages.success(request, f'شخص «{person.name}» با موفقیت ثبت شد.')
        return redirect('loans:person_detail', pk=person.pk)
    return render(request, 'loans/person_form.html', {
        'form': form,
        'title': 'شخص جدید',
        'is_create': True,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Person edit
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def person_edit(request, pk):
    person = get_object_or_404(LoanPerson, pk=pk, is_deleted=False)
    form = LoanPersonForm(request.POST or None, instance=person)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'مشخصات «{person.name}» ویرایش شد.')
        return redirect('loans:person_detail', pk=person.pk)
    return render(request, 'loans/person_form.html', {
        'form': form,
        'person': person,
        'title': f'ویرایش — {person.name}',
        'is_create': False,
    })

@login_required
def person_delete(request, pk):
    person = get_object_or_404(LoanPerson, pk=pk, is_deleted=False)

    if request.method == 'POST':
        # Block deletion if there's an outstanding balance, to avoid losing
        # track of money owed. Remove this check if you don't want it.
        if person.balance_afn != 0 or person.balance_usd != 0:
            messages.error(
                request,
                f'«{person.name}» مانده پرداخت‌نشده دارد و قابل حذف نیست. '
                'لطفاً ابتدا حساب را تسویه کنید.'
            )
            return redirect('loans:person_detail', pk=pk)

        person.is_deleted = True
        person.deleted_at = timezone.now()
        person.save(update_fields=['is_deleted', 'deleted_at'])
        messages.success(request, f'«{person.name}» با موفقیت حذف شد.')
        return redirect('loans:person_list')

    return redirect('loans:person_list')

# ─────────────────────────────────────────────────────────────────────────────
# Person detail — main hub: balances + history + both forms
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def person_detail(request, pk):
    person = get_object_or_404(LoanPerson, pk=pk, is_deleted=False)
    bankers = _active_bankers()

    give_form = GiveLoanForm(banker_queryset=bankers)
    rep_form  = RepaymentForm(banker_queryset=bankers)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'give_loan':
            give_form = GiveLoanForm(request.POST, banker_queryset=bankers)
            if give_form.is_valid():
                d = give_form.cleaned_data
                banker = None
                if d['payment_method'] == 'saraf' and d.get('banker_id'):
                    try:
                        banker = Banker.objects.get(pk=d['banker_id'], is_deleted=False)
                    except Banker.DoesNotExist:
                        messages.error(request, 'صراف انتخاب‌شده یافت نشد.')
                        return _render_detail(request, person, give_form, rep_form)
                try:
                    LoanService.give_loan(
                        person=person,
                        amount=d['amount'],
                        currency=d['currency'],
                        payment_method=d['payment_method'],
                        transaction_date=d['transaction_date'],
                        banker=banker,
                        notes=d.get('notes', ''),
                        user=request.user,
                    )
                    sym = '$' if d['currency'] == 'USD' else '؋'
                    messages.success(
                        request,
                        f'قرضه {d["amount"]:,.2f} {sym} به «{person.name}» ثبت شد.'
                    )
                    return redirect('loans:person_detail', pk=pk)
                except ValidationError as e:
                    messages.error(request, str(e.message))

        elif action == 'repayment':
            rep_form = RepaymentForm(request.POST, banker_queryset=bankers)
            if rep_form.is_valid():
                d = rep_form.cleaned_data
                banker = None
                if d['payment_method'] == 'saraf' and d.get('banker_id'):
                    try:
                        banker = Banker.objects.get(pk=d['banker_id'], is_deleted=False)
                    except Banker.DoesNotExist:
                        messages.error(request, 'صراف انتخاب‌شده یافت نشد.')
                        return _render_detail(request, person, give_form, rep_form)
                try:
                    LoanService.record_repayment(
                        person=person,
                        amount=d['amount'],
                        currency=d['currency'],
                        payment_method=d['payment_method'],
                        transaction_date=d['transaction_date'],
                        banker=banker,
                        notes=d.get('notes', ''),
                        user=request.user,
                    )
                    sym = '$' if d['currency'] == 'USD' else '؋'
                    messages.success(
                        request,
                        f'بازپرداخت {d["amount"]:,.2f} {sym} از «{person.name}» ثبت شد.'
                    )
                    return redirect('loans:person_detail', pk=pk)
                except ValidationError as e:
                    messages.error(request, str(e.message))

    return _render_detail(request, person, give_form, rep_form)


def _render_detail(request, person, give_form, rep_form):
    txs = LoanTransaction.objects.filter(
        person=person, is_deleted=False
    ).select_related('banker', 'reversed_by', 'created_by').order_by(
        '-transaction_date', '-created_at'
    )
    # current_jalali_year is needed by the Jalali date-picker JS in
    # loan_detail.html (same approach as the supplier payment page).
    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])
    return render(request, 'loans/person_detail.html', {
        'person': person,
        'transactions': txs,
        'give_form': give_form,
        'rep_form': rep_form,
        'current_jalali_year': current_jalali_year,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Reverse transaction
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def reverse_transaction(request, tx_pk):
    loan_tx = get_object_or_404(
        LoanTransaction, pk=tx_pk, is_deleted=False
    )
    if request.method == 'POST':
        notes = request.POST.get('notes', 'برگشت دستی')
        try:
            LoanService.reverse_transaction(
                loan_tx=loan_tx,
                notes=notes,
                user=request.user,
            )
            messages.success(request, 'تراکنش با موفقیت برگشت داده شد.')
        except ValidationError as e:
            messages.error(request, str(e.message))
    return redirect('loans:person_detail', pk=loan_tx.person.pk)