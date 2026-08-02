"""Purchase Views — Phase 6"""
import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import PurchaseInvoice, PurchaseItem
from .forms import PurchasePaymentForm
from .services import PurchaseService
from apps.suppliers.models import Supplier
from apps.warehouse.models import Warehouse
from apps.inventory.models import Product
from apps.banker.models import Banker
from apps.settings_app.models import BusinessSettings
from apps.core.jalali import to_jalali_str, jalali_str_to_gregorian


@login_required
def purchase_list(request):
    search = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')

    qs = PurchaseInvoice.objects.filter(
    is_deleted=False
    ).select_related('supplier', 'warehouse').prefetch_related('items__product__unit')

    if search:
        qs = qs.filter(
            Q(invoice_number__icontains=search) |
            Q(supplier__name__icontains=search) |
            Q(supplier_invoice_number__icontains=search)
        )
    if status_filter:
        qs = qs.filter(status=status_filter)

    afn_qs = qs.filter(currency='AFN')
    usd_qs = qs.filter(currency='USD')

    totals_afn = afn_qs.aggregate(
        total_purchases=Sum('total_amount'),
        total_paid=Sum('paid_amount'),
        total_remaining=Sum('remaining_amount'),
    )
    totals_usd = usd_qs.aggregate(
        total_purchases=Sum('total_amount'),
        total_paid=Sum('paid_amount'),
        total_remaining=Sum('remaining_amount'),
    )

    paginator = Paginator(qs.order_by('-purchase_date', '-created_at'), 25)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'purchases/purchase_list.html', {
        'page_title':     'فاکتورهای خرید',
        'invoices':       page,
        'search':         search,
        'status_filter':  status_filter,
        'status_choices': PurchaseInvoice.Status.choices,
        'totals_afn':     totals_afn,
        'totals_usd':     totals_usd,
        'total_count':    paginator.count,
    })


@login_required
def purchase_create(request):
    suppliers = Supplier.objects.filter(
        is_active=True, is_deleted=False
    ).order_by('name')
    warehouses = Warehouse.objects.filter(is_active=True, is_deleted=False)
    products = Product.objects.filter(
        is_active=True, is_deleted=False
    ).select_related('unit', 'category').order_by('name')
    bankers = Banker.objects.filter(is_active=True, is_deleted=False).order_by('name')
    default_warehouse = Warehouse.get_default()

    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    if request.method == 'POST':
        try:
            supplier_id       = request.POST.get('supplier_id')
            warehouse_id      = request.POST.get('warehouse_id')
            purchase_date_raw = request.POST.get('purchase_date', '').strip()
            paid_amount       = Decimal(request.POST.get('paid_amount', '0') or '0')
            payment_method    = request.POST.get('payment_method', 'cash')
            currency          = request.POST.get('currency', 'AFN')
            banker_id         = request.POST.get('banker_id')
            supplier_inv_num  = request.POST.get('supplier_invoice_number', '')
            notes             = request.POST.get('notes', '')
            items_json        = request.POST.get('items_json', '[]')
            items_data        = json.loads(items_json)

            purchase_date = jalali_str_to_gregorian(purchase_date_raw)

            if not items_data:
                raise ValueError('فاکتور خرید باید حداقل یک ردیف داشته باشد.')

            supplier  = Supplier.objects.get(pk=supplier_id, is_deleted=False)
            warehouse = Warehouse.objects.get(pk=warehouse_id, is_deleted=False)

            banker = None
            if payment_method == PurchaseInvoice.PaymentMethod.SARAF:
                if not banker_id:
                    raise ValueError('برای پرداخت از طریق صراف، صراف را انتخاب کنید.')
                banker = Banker.objects.get(pk=banker_id, is_deleted=False, is_active=True)

            items = []
            for item in items_data:
                product = Product.objects.get(pk=item['product_id'])
                expiry_raw = item.get('expiry_date') or ''
                expiry_date = jalali_str_to_gregorian(expiry_raw) if expiry_raw else None
                items.append({
                    'product':          product,
                    'quantity':         Decimal(str(item['quantity'])),
                    'unit_cost':        Decimal(str(item['unit_cost'])),
                    'discount_percent': Decimal(str(item.get('discount_percent', '0'))),
                    'expiry_date':      expiry_date,
                    'currency':         currency,
                })

            invoice = PurchaseService.create_purchase(
                supplier=supplier,
                warehouse=warehouse,
                items=items,
                purchase_date=purchase_date,
                paid_amount=paid_amount,
                payment_method=payment_method,
                currency=currency,
                banker=banker,
                supplier_invoice_number=supplier_inv_num,
                notes=notes,
                user=request.user,
            )
            messages.success(
                request,
                f'فاکتور خرید {invoice.invoice_number} با موفقیت ثبت شد.'
            )
            return redirect('purchases:purchase_detail', pk=invoice.pk)

        except Exception as e:
            messages.error(request, str(e))

    return render(request, 'purchases/purchase_create.html', {
        'page_title':          'فاکتور خرید جدید',
        'suppliers':           suppliers,
        'warehouses':          warehouses,
        'products':            products,
        'bankers':             bankers,
        'default_warehouse':   default_warehouse,
        'today':               timezone.now().date(),
        'today_jalali':        to_jalali_str(timezone.now().date()),
        'current_jalali_year': current_jalali_year,
        'payment_methods':     PurchaseInvoice.PaymentMethod.choices,
        'currency_choices':    PurchaseInvoice.Currency.choices,
        'default_currency':    BusinessSettings.get_solo().default_currency,
    })


@login_required
def purchase_edit(request, pk):
    invoice = get_object_or_404(
        PurchaseInvoice.objects.select_related(
            'supplier', 'warehouse', 'banker'
        ).prefetch_related('items__product__unit'),
        pk=pk, is_deleted=False
    )

    suppliers = Supplier.objects.filter(
        is_active=True, is_deleted=False
    ).order_by('name')
    warehouses = Warehouse.objects.filter(is_active=True, is_deleted=False)
    products = Product.objects.filter(
        is_active=True, is_deleted=False
    ).select_related('unit', 'category').order_by('name')
    bankers = Banker.objects.filter(is_active=True, is_deleted=False).order_by('name')

    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    if request.method == 'POST':
        try:
            supplier_id       = request.POST.get('supplier_id')
            warehouse_id      = request.POST.get('warehouse_id')
            purchase_date_raw = request.POST.get('purchase_date', '').strip()
            paid_amount       = Decimal(request.POST.get('paid_amount', '0') or '0')
            payment_method    = request.POST.get('payment_method', 'cash')
            currency          = request.POST.get('currency', 'AFN')
            banker_id         = request.POST.get('banker_id')
            supplier_inv_num  = request.POST.get('supplier_invoice_number', '')
            notes             = request.POST.get('notes', '')
            items_json        = request.POST.get('items_json', '[]')
            items_data        = json.loads(items_json)

            purchase_date = jalali_str_to_gregorian(purchase_date_raw)

            if not items_data:
                raise ValueError('فاکتور خرید باید حداقل یک ردیف داشته باشد.')

            supplier  = Supplier.objects.get(pk=supplier_id, is_deleted=False)
            warehouse = Warehouse.objects.get(pk=warehouse_id, is_deleted=False)

            banker = None
            if payment_method == PurchaseInvoice.PaymentMethod.SARAF:
                if not banker_id:
                    raise ValueError('برای پرداخت از طریق صراف، صراف را انتخاب کنید.')
                banker = Banker.objects.get(pk=banker_id, is_deleted=False, is_active=True)

            items = []
            for item in items_data:
                product = Product.objects.get(pk=item['product_id'])
                expiry_raw = item.get('expiry_date') or ''
                expiry_date = jalali_str_to_gregorian(expiry_raw) if expiry_raw else None
                items.append({
                    'product':          product,
                    'quantity':         Decimal(str(item['quantity'])),
                    'unit_cost':        Decimal(str(item['unit_cost'])),
                    'discount_percent': Decimal(str(item.get('discount_percent', '0'))),
                    'expiry_date':      expiry_date,
                    'currency':         currency,
                })

            invoice = PurchaseService.update_purchase(
                invoice=invoice,
                supplier=supplier,
                warehouse=warehouse,
                items=items,
                purchase_date=purchase_date,
                paid_amount=paid_amount,
                payment_method=payment_method,
                currency=currency,
                banker=banker,
                supplier_invoice_number=supplier_inv_num,
                notes=notes,
                user=request.user,
            )
            messages.success(
                request,
                f'فاکتور خرید {invoice.invoice_number} با موفقیت ویرایش شد.'
            )
            return redirect('purchases:purchase_detail', pk=invoice.pk)

        except Exception as e:
            messages.error(request, str(e))

    existing_items = []
    for item in invoice.items.select_related('product', 'product__unit').all():
        existing_items.append({
            'product_id':       str(item.product.pk),
            'product_name':     item.product.name,
            'unit':             item.product.unit.abbreviation if item.product.unit else '',
            'quantity':         float(item.quantity),
            'unit_cost':        float(item.unit_cost),
            'discount_percent': float(item.discount_percent),
            'expiry_date':      to_jalali_str(item.expiry_date) if item.expiry_date else None,
            'line_total':       float(item.line_total),
        })

    return render(request, 'purchases/purchase_edit.html', {
        'page_title':          f'ویرایش فاکتور خرید {invoice.invoice_number}',
        'invoice':             invoice,
        'suppliers':           suppliers,
        'warehouses':          warehouses,
        'products':            products,
        'bankers':             bankers,
        'today':               invoice.purchase_date,
        'current_jalali_year': current_jalali_year,
        'payment_methods':     PurchaseInvoice.PaymentMethod.choices,
        'currency_choices':    PurchaseInvoice.Currency.choices,
        'existing_items_json': json.dumps(existing_items),
    })


@login_required
def purchase_detail(request, pk):
    invoice = get_object_or_404(
        PurchaseInvoice.objects.select_related(
            'supplier', 'warehouse', 'created_by', 'banker'
        ).prefetch_related('items__product__unit'),
        pk=pk, is_deleted=False
    )

    bankers = Banker.objects.filter(is_active=True, is_deleted=False).order_by('name')

    payment_form = PurchasePaymentForm(
        bankers=bankers,
        invoice=invoice,
        initial={
            'payment_date': timezone.now().date(),
            'amount':       invoice.remaining_amount,
            'currency':     invoice.currency,
        }
    )

    if request.method == 'POST' and 'add_payment' in request.POST:
        payment_form = PurchasePaymentForm(
            request.POST, bankers=bankers, invoice=invoice
        )
        if payment_form.is_valid():
            cd = payment_form.cleaned_data
            try:
                banker = None
                if cd['payment_method'] == 'saraf' and cd.get('banker_id'):
                    banker = Banker.objects.get(
                        pk=cd['banker_id'], is_active=True, is_deleted=False
                    )

                PurchaseService.add_payment(
                    invoice=invoice,
                    amount=cd['amount'],
                    payment_method=cd['payment_method'],
                    payment_date=cd['payment_date'],
                    notes=cd.get('notes', ''),
                    user=request.user,
                )

                if banker:
                    from apps.banker.services import BankerService
                    BankerService.apply_purchase_payment(
                        banker=banker,
                        amount=cd['amount'],
                        currency=cd.get('currency', invoice.currency),
                        purchase_invoice=invoice,
                        transaction_date=cd['payment_date'],
                        user=request.user,
                    )

                messages.success(request, 'پرداخت ثبت شد.')
                return redirect('purchases:purchase_detail', pk=pk)
            except Exception as e:
                messages.error(request, str(e))

    return render(request, 'purchases/purchase_detail.html', {
        'page_title':   f'فاکتور خرید {invoice.invoice_number}',
        'invoice':      invoice,
        'payment_form': payment_form,
        'bankers':      bankers,
    })


@login_required
@require_POST
def purchase_delete(request, pk):
    invoice = get_object_or_404(PurchaseInvoice, pk=pk, is_deleted=False)
    try:
        PurchaseService.cancel_purchase(invoice, user=request.user)
        messages.success(
            request,
            f'فاکتور خرید {invoice.invoice_number} حذف شد و موجودی برگشت داده شد.'
        )
    except Exception as e:
        messages.error(request, str(e))
    return redirect('purchases:purchase_list')


@login_required
def purchase_print(request, pk):
    invoice = get_object_or_404(
        PurchaseInvoice.objects.select_related(
            'supplier', 'warehouse', 'banker'
        ).prefetch_related('items__product__unit'),
        pk=pk, is_deleted=False
    )
    currency_symbol = '$' if invoice.currency == 'USD' else '؋'
    return render(request, 'purchases/purchase_print.html', {
        'invoice': invoice,
        'currency_symbol': currency_symbol,
    })