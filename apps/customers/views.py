"""
Customer Views — Phase 5 Enterprise
"""
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.http import JsonResponse
from django.db import transaction as db_transaction

from .models import Customer, CustomerTransaction, CustomerPayment
from .forms import CustomerForm, PaymentReceiveForm, AdvanceAddForm
from .services.accounting import CustomerAccountingService


def _apply_payment_to_invoices(customer, amount, payment_method, currency,
                                exchange_rate, payment_date, notes, user):
    """
    Apply a direct customer payment against outstanding invoices (oldest first).

    This creates sales.Payment records and updates Invoice paid/remaining/status
    fields — exactly what SalesService.add_payment does — so the sales section
    stays in sync when a payment is registered from the customer page.

    Returns the total amount actually applied to invoices (may be less than
    `amount` if total invoice debt is smaller).
    """
    from apps.sales.models import Invoice, Payment as SalesPayment

    # Only AFN invoices when paying in AFN; only USD invoices when paying in USD.
    # This mirrors the currency logic in CustomerAccountingService._apply_payment_to_balance.
    unpaid_invoices = Invoice.objects.filter(
        customer=customer,
        is_deleted=False,
        currency=currency,
        status__in=[Invoice.Status.CONFIRMED, Invoice.Status.PARTIAL],
        remaining_amount__gt=0,
    ).order_by('invoice_date', 'created_at')   # oldest first

    remaining = amount
    for invoice in unpaid_invoices:
        if remaining <= 0:
            break

        to_apply = min(remaining, invoice.remaining_amount)
        if to_apply <= 0:
            continue

        # Create the Payment record linked to this invoice
        SalesPayment.objects.create(
            invoice=invoice,
            amount=to_apply,
            payment_method=payment_method,
            payment_date=payment_date,
            notes=notes or f'دریافت مستقیم — {customer.name}',
            received_by=user,
        )

        # Update invoice financials
        invoice.paid_amount += to_apply
        invoice.remaining_amount = invoice.total_amount - invoice.paid_amount
        if invoice.remaining_amount <= 0:
            invoice.status = Invoice.Status.PAID
            invoice.remaining_amount = Decimal('0')
        else:
            invoice.status = Invoice.Status.PARTIAL
        invoice.save(update_fields=[
            'paid_amount', 'remaining_amount', 'status', 'updated_at'
        ])

        remaining -= to_apply

    return amount - remaining   # total applied to invoices


@login_required
def customer_list(request):
    search = request.GET.get('q', '').strip()
    qs = Customer.objects.filter(is_deleted=False).order_by('name')
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(phone__icontains=search) |
            Q(code__icontains=search)
        )

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))

    totals = qs.aggregate(
        total_debt=Sum('total_debt'),
        total_advance=Sum('advance_balance'),
    )

    return render(request, 'customers/customer_list.html', {
        'page_title': 'مشتریان',
        'customers': page,
        'search': search,
        'total': paginator.count,
        'total_debt': totals['total_debt'] or 0,
        'total_advance': totals['total_advance'] or 0,
    })


@login_required
def customer_create(request):
    form = CustomerForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        customer = form.save()
        CustomerAccountingService.initialize_opening_balance(
            customer, user=request.user
        )
        messages.success(request, f'مشتری «{customer.name}» ثبت شد.')
        if request.POST.get('save_and_new'):
            return redirect('customers:customer_create')
        return redirect('customers:customer_detail', pk=customer.pk)
    return render(request, 'customers/customer_form.html', {
        'page_title': 'مشتری جدید',
        'form': form,
        'action': 'ثبت',
    })


@login_required
def customer_edit(request, pk):
    customer = get_object_or_404(Customer, pk=pk, is_deleted=False)

    # Save old values before form binding
    old_opening_afn = customer.opening_balance
    old_opening_usd = customer.opening_balance_usd

    form = CustomerForm(request.POST or None, instance=customer)
    if request.method == 'POST':
        if form.is_valid():
            updated_customer = form.save()

            new_opening_afn = updated_customer.opening_balance
            new_opening_usd = updated_customer.opening_balance_usd

            # If opening balance changed, update the opening transaction
            # and recalculate total_debt so the detail page reflects correctly
            if new_opening_afn != old_opening_afn or new_opening_usd != old_opening_usd:
                _update_opening_balance(
                    updated_customer,
                    old_opening_afn, new_opening_afn,
                    old_opening_usd, new_opening_usd,
                )

            messages.success(request, f'مشتری «{updated_customer.name}» ویرایش شد.')
            return redirect('customers:customer_detail', pk=customer.pk)
        else:
            messages.error(request, f'خطا در فرم: {form.errors.as_text()}')

    return render(request, 'customers/customer_form.html', {
        'page_title': 'ویرایش مشتری',
        'form': form,
        'action': 'ویرایش',
        'object': customer,
    })


def _update_opening_balance(customer, old_afn, new_afn, old_usd, new_usd):
    """
    When opening balance is corrected on edit:
    1. Update the OPENING_DEBT CustomerTransaction amount
    2. Adjust total_debt / total_debt_usd by the difference
    """
    from decimal import Decimal
    from .models import CustomerTransaction

    diff_afn = (new_afn or Decimal('0')) - (old_afn or Decimal('0'))
    diff_usd = (new_usd or Decimal('0')) - (old_usd or Decimal('0'))

    # Update the opening transaction record if it exists
    if diff_afn != 0:
        opening_tx_afn = CustomerTransaction.objects.filter(
            customer=customer,
            tx_type=CustomerTransaction.TxType.OPENING_DEBT,
            currency='AFN',
        ).first()
        if opening_tx_afn:
            opening_tx_afn.amount = new_afn or Decimal('0')
            opening_tx_afn.save(update_fields=['amount'])

    if diff_usd != 0:
        opening_tx_usd = CustomerTransaction.objects.filter(
            customer=customer,
            tx_type=CustomerTransaction.TxType.OPENING_DEBT,
            currency='USD',
        ).first()
        if opening_tx_usd:
            opening_tx_usd.amount = new_usd or Decimal('0')
            opening_tx_usd.save(update_fields=['amount'])

    # Adjust the running balance fields by the difference
    update_fields = []
    if diff_afn != 0:
        customer.total_debt = max(Decimal('0'), (customer.total_debt or Decimal('0')) + diff_afn)
        update_fields.append('total_debt')
    if diff_usd != 0:
        customer.total_debt_usd = max(Decimal('0'), (customer.total_debt_usd or Decimal('0')) + diff_usd)
        update_fields.append('total_debt_usd')

    if update_fields:
        customer.save(update_fields=update_fields)


@login_required
def customer_detail(request, pk):
    customer = get_object_or_404(
        Customer.objects.prefetch_related('transactions', 'direct_payments'),
        pk=pk, is_deleted=False
    )

    from apps.banker.models import Banker
    bankers = Banker.objects.filter(is_active=True, is_deleted=False).order_by('name')

    payment_form = PaymentReceiveForm(bankers=bankers)
    advance_form = AdvanceAddForm(bankers=bankers)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'receive_payment':
            payment_form = PaymentReceiveForm(request.POST, bankers=bankers)
            if payment_form.is_valid():
                cd = payment_form.cleaned_data
                try:
                    with db_transaction.atomic():
                        banker = None
                        if cd['payment_method'] == 'saraf' and cd.get('banker_id'):
                            banker = Banker.objects.get(
                                pk=cd['banker_id'], is_active=True, is_deleted=False
                            )

                        # ── NEW: Apply payment to outstanding invoices first ──
                        # This creates sales.Payment records and updates invoice
                        # paid_amount / remaining_amount / status so the sales
                        # section stays in sync.
                        _apply_payment_to_invoices(
                            customer=customer,
                            amount=cd['amount'],
                            payment_method=cd['payment_method'],
                            currency=cd['currency'],
                            exchange_rate=cd.get('exchange_rate') or Decimal('1'),
                            payment_date=cd['payment_date'],
                            notes=cd.get('notes', ''),
                            user=request.user,
                        )

                        # ── EXISTING: Update customer ledger (CustomerTransaction +
                        # CustomerPayment + customer balance fields) ──
                        CustomerAccountingService.apply_payment(
                            customer=customer,
                            amount=cd['amount'],
                            payment_method=cd['payment_method'],
                            currency=cd['currency'],
                            exchange_rate=cd.get('exchange_rate') or Decimal('1'),
                            payment_date=cd['payment_date'],
                            notes=cd.get('notes', ''),
                            user=request.user,
                        )

                        # ── EXISTING: Credit banker if payment via saraf ──
                        if banker:
                            from apps.banker.services import BankerService
                            BankerService.apply_sale_payment(
                                banker=banker,
                                amount=cd['amount'],
                                currency=cd['currency'],
                                sale_invoice=type('obj', (object,), {
                                    'invoice_number': f'دریافت مستقیم — {customer.name}'
                                })(),
                                transaction_date=cd['payment_date'],
                                user=request.user,
                            )

                    sym = '$' if cd['currency'] == 'USD' else '؋'
                    messages.success(
                        request,
                        f'{cd["amount"]:,.2f} {sym} از مشتری «{customer.name}» دریافت شد.'
                    )
                    return redirect('customers:customer_detail', pk=pk)
                except Exception as e:
                    messages.error(request, str(e))

        elif action == 'add_advance':
            advance_form = AdvanceAddForm(request.POST, bankers=bankers)
            if advance_form.is_valid():
                cd = advance_form.cleaned_data
                try:
                    banker = None
                    if cd['payment_method'] == 'saraf' and cd.get('banker_id'):
                        banker = Banker.objects.get(
                            pk=cd['banker_id'], is_active=True, is_deleted=False
                        )

                    CustomerAccountingService.add_advance(
                        customer=customer,
                        amount=cd['amount'],
                        payment_method=cd['payment_method'],
                        currency=cd['currency'],
                        exchange_rate=cd.get('exchange_rate') or Decimal('1'),
                        payment_date=cd['payment_date'],
                        notes=cd.get('notes', ''),
                        user=request.user,
                    )

                    if banker:
                        from apps.banker.services import BankerService
                        BankerService.apply_sale_payment(
                            banker=banker,
                            amount=cd['amount'],
                            currency=cd['currency'],
                            sale_invoice=type('obj', (object,), {
                                'invoice_number': f'پیش‌پرداخت — {customer.name}'
                            })(),
                            transaction_date=cd['payment_date'],
                            user=request.user,
                        )

                    sym = '$' if cd['currency'] == 'USD' else '؋'
                    messages.success(
                        request,
                        f'پیش‌پرداخت {cd["amount"]:,.2f} {sym} برای «{customer.name}» ثبت شد.'
                    )
                    return redirect('customers:customer_detail', pk=pk)
                except Exception as e:
                    messages.error(request, str(e))

    recent_txs = CustomerTransaction.objects.filter(
        customer=customer
    ).select_related('invoice').order_by('-transaction_date', '-created_at')[:15]

    from apps.sales.models import Invoice
    invoices = Invoice.objects.filter(
        customer=customer, is_deleted=False
    ).order_by('-invoice_date')[:10]

    customer.refresh_from_db()

    from apps.core.jalali import to_jalali_str
    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'customers/customer_detail.html', {
        'page_title': customer.name,
        'customer': customer,
        'recent_txs': recent_txs,
        'invoices': invoices,
        'payment_form': payment_form,
        'advance_form': advance_form,
        'bankers': bankers,
        'current_jalali_year': current_jalali_year,
    })


@login_required
def customer_statement(request, pk):
    customer = get_object_or_404(Customer, pk=pk, is_deleted=False)

    date_from = request.GET.get('date_from', '')  # Jalali string typed by user
    date_to   = request.GET.get('date_to', '')     # Jalali string typed by user

    txs = CustomerTransaction.objects.filter(
        customer=customer
    ).select_related('invoice', 'created_by').order_by(
        'transaction_date', 'created_at'
    )

    from apps.core.jalali import jalali_str_to_gregorian
    if date_from:
        try:
            txs = txs.filter(transaction_date__gte=jalali_str_to_gregorian(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            txs = txs.filter(transaction_date__lte=jalali_str_to_gregorian(date_to))
        except ValueError:
            pass

    debit_types = [
        CustomerTransaction.TxType.INVOICE,
        CustomerTransaction.TxType.OPENING_DEBT,
    ]
    credit_types = [
        CustomerTransaction.TxType.PAYMENT,
        CustomerTransaction.TxType.ADVANCE_ADD,
        CustomerTransaction.TxType.ADVANCE_USE,
        CustomerTransaction.TxType.DEBT_WRITE_OFF,
    ]

    # ── split totals by currency (AFN vs USD) ──
    # Reversed transactions (is_reversed=True) no longer represent real
    # debt/credit — e.g. a cancelled invoice's original debit is excluded,
    # matching how customer.total_debt / total_debt_usd are actually
    # maintained (CustomerAccountingService excludes reversed txs too).
    # The transaction ROWS themselves (txs, used in the table below) are
    # left untouched so the full audit trail — including reversed entries
    # shown grayed out — still displays correctly.
    total_debit_afn = sum(
        t.amount for t in txs
        if t.tx_type in debit_types
        and t.currency == CustomerTransaction.Currency.AFN
        and not t.is_reversed
    )
    total_debit_usd = sum(
        t.amount for t in txs
        if t.tx_type in debit_types
        and t.currency == CustomerTransaction.Currency.USD
        and not t.is_reversed
    )
    total_credit_afn = sum(
        t.amount for t in txs
        if t.tx_type in credit_types
        and t.currency == CustomerTransaction.Currency.AFN
        and not t.is_reversed
    )
    total_credit_usd = sum(
        t.amount for t in txs
        if t.tx_type in credit_types
        and t.currency == CustomerTransaction.Currency.USD
        and not t.is_reversed
    )

    from apps.core.jalali import to_jalali_str
    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'customers/customer_statement.html', {
        'page_title': f'کارنامه — {customer.name}',
        'customer': customer,
        'transactions': txs,
        'total_debit': total_debit_afn,
        'total_credit': total_credit_afn,
        'total_debit_usd': total_debit_usd,
        'total_credit_usd': total_credit_usd,
        'date_from': date_from,
        'date_to': date_to,
        'current_jalali_year': current_jalali_year,
    })


@login_required
def customer_debts(request):
    from django.db.models import Q, F

    show_all = request.GET.get('show_all', '')
    qs = Customer.objects.filter(
        is_active=True, is_deleted=False
    ).annotate(
        # Net balance = gross debt minus any advance on file, same currency.
        # This matches customer.net_balance / net_balance_usd exactly (the
        # figures shown on the customer detail page), so this report never
        # disagrees with the per-customer view even if a customer happens to
        # carry both debt and an advance in the same currency at once.
        net_debt=F('total_debt') - F('advance_balance'),
        net_debt_usd=F('total_debt_usd') - F('advance_balance_usd'),
    ).order_by('-net_debt')

    if not show_all:
        qs = qs.filter(Q(net_debt__gt=0) | Q(net_debt_usd__gt=0))

    totals = qs.aggregate(
        total_debt=Sum('net_debt'),
        total_advance=Sum('advance_balance'),
        total_debt_usd=Sum('net_debt_usd'),
    )

    return render(request, 'customers/customer_debts.html', {
        'page_title': 'گزارش بدهی مشتریان',
        'customers': qs,
        'total_debt': totals['total_debt'] or 0,
        'total_advance': totals['total_advance'] or 0,
        'total_debt_usd': totals['total_debt_usd'] or 0,
        'show_all': show_all,
    })


@login_required
@require_POST
def reverse_transaction(request, tx_pk):
    tx = get_object_or_404(
        CustomerTransaction,
        pk=tx_pk,
        is_reversed=False
    )
    notes = request.POST.get('notes', '')
    try:
        CustomerAccountingService.reverse_transaction(tx, notes=notes, user=request.user)
        messages.success(request, 'تراکنش برگشت داده شد و موجودی مشتری به‌روزرسانی شد.')
    except Exception as e:
        messages.error(request, str(e))
    return redirect('customers:customer_detail', pk=tx.customer.pk)


@login_required
@require_POST
def customer_delete(request, pk):
    customer = get_object_or_404(Customer, pk=pk, is_deleted=False)
    from apps.sales.models import Invoice
    if Invoice.objects.filter(customer=customer, is_deleted=False).exists():
        messages.error(request, 'این مشتری دارای فاکتور است و قابل حذف نیست.')
        return redirect('customers:customer_list')
    name = customer.name
    customer.is_deleted = True
    customer.deleted_at = timezone.now()
    customer.save(update_fields=['is_deleted', 'deleted_at'])
    messages.success(request, f'مشتری «{name}» حذف شد.')
    return redirect('customers:customer_list')


@login_required
def customer_search_ajax(request):
    q = request.GET.get('q', '').strip()
    customers = Customer.objects.filter(
        is_active=True, is_deleted=False,
        name__icontains=q
    ).values('id', 'name', 'phone', 'total_debt', 'advance_balance')[:10]
    results = []
    for c in customers:
        results.append({
            'id': str(c['id']),
            'name': c['name'],
            'phone': c['phone'],
            'debt': float(c['total_debt'] or 0),
            'advance': float(c['advance_balance'] or 0),
        })
    return JsonResponse({'results': results})