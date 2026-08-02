"""Supplier Views — Phase 6"""
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.http import JsonResponse

from .models import Supplier, SupplierTransaction, SupplierPayment
from .forms import SupplierForm, SupplierPaymentForm
from .services.accounting import SupplierAccountingService


@login_required
def supplier_list(request):
    search = request.GET.get('q', '').strip()
    qs = Supplier.objects.filter(is_deleted=False).order_by('name')
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
    return render(request, 'suppliers/supplier_list.html', {
        'page_title': 'تامین‌کنندگان',
        'suppliers': page,
        'search': search,
        'total': paginator.count,
        'total_debt': totals['total_debt'] or 0,
        'total_advance': totals['total_advance'] or 0,
    })


@login_required
def supplier_create(request):
    form = SupplierForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        supplier = form.save()
        SupplierAccountingService.initialize_opening_balance(
            supplier, user=request.user
        )
        messages.success(request, f'تامین‌کننده «{supplier.name}» ثبت شد.')
        if request.POST.get('save_and_new'):
            return redirect('suppliers:supplier_create')
        return redirect('suppliers:supplier_detail', pk=supplier.pk)
    return render(request, 'suppliers/supplier_form.html', {
        'page_title': 'تامین‌کننده جدید',
        'form': form, 'action': 'ثبت',
    })


@login_required
def supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, is_deleted=False)

    # Capture old opening balances BEFORE the form overwrites them
    old_afn = supplier.opening_balance
    old_usd = supplier.opening_balance_usd

    form = SupplierForm(request.POST or None, instance=supplier)
    if request.method == 'POST' and form.is_valid():
        supplier = form.save()
        SupplierAccountingService.update_opening_balance(
            supplier=supplier,
            old_afn=old_afn,
            old_usd=old_usd,
            user=request.user,
        )
        messages.success(request, f'تامین‌کننده «{supplier.name}» ویرایش شد.')
        return redirect('suppliers:supplier_detail', pk=supplier.pk)
    return render(request, 'suppliers/supplier_form.html', {
        'page_title': 'ویرایش تامین‌کننده',
        'form': form, 'action': 'ویرایش', 'object': supplier,
    })


@login_required
def supplier_detail(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, is_deleted=False)

    from apps.banker.models import Banker
    bankers = Banker.objects.filter(is_active=True, is_deleted=False).order_by('name')

    payment_form = SupplierPaymentForm(bankers=bankers)

    if request.method == 'POST' and 'make_payment' in request.POST:
        payment_form = SupplierPaymentForm(request.POST, bankers=bankers)
        if payment_form.is_valid():
            cd = payment_form.cleaned_data
            try:
                banker = None
                if cd['payment_method'] == 'saraf' and cd.get('banker_id'):
                    banker = Banker.objects.get(
                        pk=cd['banker_id'], is_active=True, is_deleted=False
                    )

                SupplierAccountingService.apply_payment(
                    supplier=supplier,
                    amount=cd['amount'],
                    payment_method=cd['payment_method'],
                    currency=cd['currency'],
                    payment_date=cd['payment_date'],
                    notes=cd.get('notes', ''),
                    user=request.user,
                )

                # صراف: when we pay supplier via صراف,
                # we're using our banker balance → deduct from banker
                if banker:
                    from apps.banker.services import BankerService
                    BankerService.apply_purchase_payment(
                        banker=banker,
                        amount=cd['amount'],
                        currency=cd['currency'],
                        purchase_invoice=type('obj', (object,), {
                            'invoice_number': f'پرداخت به تامین‌کننده — {supplier.name}'
                        })(),
                        transaction_date=cd['payment_date'],
                        user=request.user,
                    )

                # دخل دکان: deduct from shop cash balance
                if cd['payment_method'] == 'dakkan':
                    from apps.capital.models import ShopIncomeTransfer
                    ShopIncomeTransfer.objects.create(
                        banker=None,
                        amount=cd['amount'],
                        currency=cd['currency'],
                        transfer_date=cd['payment_date'],
                        notes=(
                            cd.get('notes') or
                            f'پرداخت به تامین‌کننده «{supplier.name}» از دخل دکان'
                        ),
                        created_by=request.user,
                    )

                sym = '$' if cd['currency'] == 'USD' else '؋'
                messages.success(
                    request,
                    f'{cd["amount"]:,.2f} {sym} به تامین‌کننده «{supplier.name}» پرداخت شد.'
                )
                return redirect('suppliers:supplier_detail', pk=pk)
            except Exception as e:
                messages.error(request, str(e))

    recent_txs = SupplierTransaction.objects.filter(
        supplier=supplier
    ).select_related('purchase_invoice').order_by('-transaction_date', '-created_at')[:15]

    from apps.purchases.models import PurchaseInvoice
    invoices = PurchaseInvoice.objects.filter(
        supplier=supplier, is_deleted=False
    ).order_by('-purchase_date')[:10]

    supplier.refresh_from_db()

    from apps.core.jalali import to_jalali_str
    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'suppliers/supplier_detail.html', {
        'page_title': supplier.name,
        'supplier': supplier,
        'recent_txs': recent_txs,
        'invoices': invoices,
        'payment_form': payment_form,
        'bankers': bankers,
        'current_jalali_year': current_jalali_year,
    })


@login_required
def supplier_statement(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, is_deleted=False)
    date_from = request.GET.get('date_from', '')  # Jalali string typed by user
    date_to   = request.GET.get('date_to', '')     # Jalali string typed by user

    txs = SupplierTransaction.objects.filter(
        supplier=supplier
    ).select_related('purchase_invoice').order_by(
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

    total_debit_afn = sum(
        t.amount for t in txs
        if t.tx_type in ['purchase', 'opening_debt'] and t.currency == 'AFN'
    )
    total_credit_afn = sum(
        t.amount for t in txs
        if t.tx_type in ['payment', 'advance_use'] and t.currency == 'AFN'
    )
    total_debit_usd = sum(
        t.amount for t in txs
        if t.tx_type in ['purchase', 'opening_debt'] and t.currency == 'USD'
    )
    total_credit_usd = sum(
        t.amount for t in txs
        if t.tx_type in ['payment', 'advance_use'] and t.currency == 'USD'
    )

    from apps.core.jalali import to_jalali_str
    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'suppliers/supplier_statement.html', {
        'page_title': f'کارنامه — {supplier.name}',
        'supplier': supplier,
        'transactions': txs,
        'total_debit_afn': total_debit_afn,
        'total_credit_afn': total_credit_afn,
        'total_debit_usd': total_debit_usd,
        'total_credit_usd': total_credit_usd,
        'date_from': date_from,
        'date_to': date_to,
        'current_jalali_year': current_jalali_year,
    })


@login_required
def supplier_debts(request):
    show_all = request.GET.get('show_all', '')
    qs = Supplier.objects.filter(
        is_active=True, is_deleted=False
    ).order_by('-total_debt')

    if not show_all:
        qs = qs.filter(Q(total_debt__gt=0) | Q(total_debt_usd__gt=0))

    totals = qs.aggregate(
        total_debt=Sum('total_debt'),
        total_debt_usd=Sum('total_debt_usd'),
    )

    return render(request, 'suppliers/supplier_debts.html', {
        'page_title': 'بدهی‌های ما به تامین‌کنندگان',
        'suppliers': qs,
        'total_debt': totals['total_debt'] or 0,
        'total_debt_usd': totals['total_debt_usd'] or 0,
        'show_all': show_all,
    })


@login_required
@require_POST
def reverse_transaction(request, tx_pk):
    tx = get_object_or_404(SupplierTransaction, pk=tx_pk, is_reversed=False)
    try:
        SupplierAccountingService.reverse_transaction(
            tx, notes=request.POST.get('notes', ''), user=request.user
        )
        messages.success(request, 'تراکنش برگشت داده شد.')
    except Exception as e:
        messages.error(request, str(e))
    return redirect('suppliers:supplier_detail', pk=tx.supplier.pk)


@login_required
@require_POST
def supplier_delete(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, is_deleted=False)
    from apps.purchases.models import PurchaseInvoice
    if PurchaseInvoice.objects.filter(supplier=supplier, is_deleted=False).exists():
        messages.error(request, 'این تامین‌کننده دارای فاکتور است و قابل حذف نیست.')
        return redirect('suppliers:supplier_list')

    # Restore دخل دکان capital: delete all ShopIncomeTransfer records
    # linked to this supplier's purchase invoices (both deleted and active),
    # so the shop cash balance is automatically restored.
    from apps.capital.models import ShopIncomeTransfer
    ShopIncomeTransfer.objects.filter(
        purchase_invoice__supplier=supplier
    ).delete()

    name = supplier.name
    supplier.is_deleted = True
    supplier.deleted_at = timezone.now()
    supplier.save(update_fields=['is_deleted', 'deleted_at'])
    messages.success(request, f'تامین‌کننده «{name}» حذف شد و مبالغ دخل دکان بازگردانده شد.')
    return redirect('suppliers:supplier_list')


@login_required
def supplier_search_ajax(request):
    q = request.GET.get('q', '').strip()
    suppliers = Supplier.objects.filter(
        is_active=True, is_deleted=False,
        name__icontains=q
    ).values('id', 'name', 'phone', 'total_debt')[:10]
    return JsonResponse({
        'results': [
            {
                'id': str(s['id']),
                'name': s['name'],
                'phone': s['phone'],
                'debt': float(s['total_debt'] or 0),
            }
            for s in suppliers
        ]
    })


@login_required
@require_POST
def mutual_offset(request, pk):
    """
    Offset mutual debt between a supplier and its linked customer account.
    Also walks through open invoices on BOTH sides to mark them paid down,
    so individual purchase/sale invoices reflect the offset correctly.
    """
    supplier = get_object_or_404(Supplier, pk=pk, is_deleted=False)

    if not supplier.customer:
        messages.error(request, 'این تامین‌کننده حساب مشتری مرتبط ندارد.')
        return redirect('suppliers:supplier_detail', pk=pk)

    currency = request.POST.get('currency', 'AFN')
    try:
        amount = Decimal(request.POST.get('amount', '0') or '0')
    except Exception:
        amount = Decimal('0')

    if amount <= 0:
        messages.error(request, 'مبلغ تهاتر باید بیشتر از صفر باشد.')
        return redirect('suppliers:supplier_detail', pk=pk)

    customer = supplier.customer

    if currency == 'USD':
        supplier_debt = supplier.total_debt_usd
        customer_debt = customer.total_debt_usd
    else:
        supplier_debt = supplier.total_debt
        customer_debt = customer.total_debt

    max_offset = min(supplier_debt, customer_debt)
    if amount > max_offset:
        sym = '$' if currency == 'USD' else '؋'
        messages.error(
            request,
            f'حداکثر مبلغ قابل تهاتر {max_offset:,.2f} {sym} است '
            f'(کمترین مقدار از بدهی ما و بدهی آن‌ها به ما).'
        )
        return redirect('suppliers:supplier_detail', pk=pk)

    try:
        from apps.suppliers.services.accounting import SupplierAccountingService
        from apps.customers.services.accounting import CustomerAccountingService

        offset_date = timezone.now().date()

        # Reduce our debt to supplier — also clears their open purchase invoices
        SupplierAccountingService.apply_payment(
            supplier=supplier,
            amount=amount,
            payment_method='offset',
            currency=currency,
            payment_date=offset_date,
            notes=f'تهاتر حساب مشترک با مشتری «{customer.name}»',
            user=request.user,
        )
        SupplierAccountingService.apply_payment_to_open_invoices(
            supplier=supplier,
            amount=amount,
            currency=currency,
            date=offset_date,
            user=request.user,
        )

        # Reduce their debt to us — also clears their open sales invoices
        CustomerAccountingService.apply_payment(
            customer=customer,
            amount=amount,
            payment_method='offset',
            currency=currency,
            payment_date=offset_date,
            notes=f'تهاتر حساب مشترک با تامین‌کننده «{supplier.name}»',
            user=request.user,
        )
        CustomerAccountingService.apply_payment_to_open_invoices(
            customer=customer,
            amount=amount,
            currency=currency,
            date=offset_date,
            user=request.user,
        )

        sym = '$' if currency == 'USD' else '؋'
        messages.success(
            request,
            f'{amount:,.2f} {sym} بین حساب تامین‌کننده و مشتری تهاتر شد '
            f'و فاکتورهای باز نیز به‌روزرسانی شدند.'
        )
    except Exception as e:
        messages.error(request, str(e))

    return redirect('suppliers:supplier_detail', pk=pk)