"""
Sales Views — Phase 4
"""
import json
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import connection

from apps.banker.models import Banker
from apps.settings_app.models import BusinessSettings
from apps.core.jalali import to_jalali_str, jalali_str_to_gregorian

from .models import Invoice, InvoiceItem, Payment
from .forms import PaymentForm
from .services import SalesService
from apps.customers.models import Customer
from apps.warehouse.models import Warehouse
from apps.inventory.models import Product
from apps.warehouse.services import FIFOService


def _safe_rollback():
    """Roll back the current DB transaction if it is in a broken state."""
    try:
        if connection.needs_rollback:
            connection.rollback()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# INVOICE LIST
# ══════════════════════════════════════════════════════════════

@login_required
def invoice_list(request):
    search = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')  # Jalali string typed by user, e.g. 1405/04/01
    date_to = request.GET.get('date_to', '')       # Jalali string typed by user

    qs = Invoice.objects.filter(
        is_deleted=False
    ).select_related('customer', 'warehouse', 'created_by').prefetch_related('items__product__unit')

    if search:
        qs = qs.filter(
            Q(invoice_number__icontains=search) |
            Q(customer__name__icontains=search)
        )
    if status_filter:
        qs = qs.filter(status=status_filter)

    # Convert Jalali filter inputs to Gregorian before filtering the DB.
    # If conversion fails (invalid/partial typing), that filter is simply skipped.
    if date_from:
        try:
            qs = qs.filter(invoice_date__gte=jalali_str_to_gregorian(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            qs = qs.filter(invoice_date__lte=jalali_str_to_gregorian(date_to))
        except ValueError:
            pass

    afn_qs = qs.filter(currency='AFN')
    usd_qs = qs.filter(currency='USD')

    totals_afn = afn_qs.aggregate(
        total_sales=Sum('total_amount'),
        total_paid=Sum('paid_amount'),
        total_remaining=Sum('remaining_amount'),
        total_cost=Sum('total_cost'),
    )
    totals_usd = usd_qs.aggregate(
        total_sales=Sum('total_amount'),
        total_paid=Sum('paid_amount'),
        total_remaining=Sum('remaining_amount'),
        total_cost=Sum('total_cost'),
    )

    paginator = Paginator(qs.order_by('-invoice_date', '-created_at'), 25)
    page = paginator.get_page(request.GET.get('page'))

    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'sales/invoice_list.html', {
        'page_title': 'فاکتورهای فروش',
        'invoices': page,
        'search': search,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': Invoice.Status.choices,
        'totals_afn': totals_afn,
        'totals_usd': totals_usd,
        'total_count': paginator.count,
        'current_jalali_year': current_jalali_year,
    })


# ══════════════════════════════════════════════════════════════
# CREATE INVOICE
# ══════════════════════════════════════════════════════════════

@login_required
def invoice_create(request):
    customers         = Customer.objects.filter(is_active=True, is_deleted=False).order_by('name')
    warehouses        = Warehouse.objects.filter(is_active=True, is_deleted=False)
    products          = Product.objects.filter(
                            is_active=True, is_deleted=False
                        ).select_related('unit', 'category').order_by('name')
    bankers           = Banker.objects.filter(is_active=True, is_deleted=False).order_by('name')
    default_warehouse = Warehouse.get_default()

    if request.method == 'POST':
        try:
            customer_id      = request.POST.get('customer_id')
            warehouse_id     = request.POST.get('warehouse_id')
            invoice_date_raw = request.POST.get('invoice_date')  # Jalali string, e.g. 1405/04/11
            paid_amount      = Decimal(request.POST.get('paid_amount', '0') or '0')
            payment_method   = request.POST.get('payment_method', 'cash')
            currency         = request.POST.get('currency', 'AFN')
            banker_id        = request.POST.get('banker_id')
            notes            = request.POST.get('notes', '')
            items_json       = request.POST.get('items_json', '[]')
            items_data       = json.loads(items_json)
            delivery_choice  = request.POST.get('delivery_choice', 'pending')
            create_pending   = (delivery_choice == 'pending')

            # ── Validate required fields before touching the DB ──
            if not customer_id:
                raise ValueError('مشتری را انتخاب کنید.')
            if not warehouse_id:
                raise ValueError('انبار را انتخاب کنید.')
            if not invoice_date_raw:
                raise ValueError('تاریخ فاکتور را وارد کنید.')
            if not items_data:
                raise ValueError('فاکتور باید حداقل یک ردیف داشته باشد.')

            # Convert the Jalali date typed by the user into Gregorian for storage.
            # DB keeps storing standard Gregorian dates — nothing else changes.
            invoice_date = jalali_str_to_gregorian(invoice_date_raw)

            customer  = Customer.objects.get(pk=customer_id, is_deleted=False)
            warehouse = Warehouse.objects.get(pk=warehouse_id, is_deleted=False)

            banker = None
            if payment_method == Payment.PaymentMethod.SARAF:
                if not banker_id:
                    raise ValueError('برای پرداخت از طریق صراف، صراف را انتخاب کنید.')
                banker = Banker.objects.get(pk=banker_id, is_deleted=False, is_active=True)

            items = []
            for item in items_data:
                product = Product.objects.get(pk=item['product_id'], is_deleted=False)
                items.append({
                    'product':          product,
                    'quantity':         Decimal(str(item['quantity'])),
                    'unit_price':       Decimal(str(item['unit_price'])),
                    'discount_percent': Decimal(str(item.get('discount_percent', '0'))),
                })

            invoice = SalesService.create_invoice(
                customer=customer,
                warehouse=warehouse,
                items=items,
                invoice_date=invoice_date,
                paid_amount=paid_amount,
                payment_method=payment_method,
                currency=currency,
                banker=banker,
                notes=notes,
                user=request.user,
                create_pending=create_pending,
            )
            messages.success(request, f'فاکتور {invoice.invoice_number} با موفقیت ثبت شد.')
            return redirect('sales:invoice_detail', pk=invoice.pk)

        except Exception as e:
            _safe_rollback()
            messages.error(request, str(e))

    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'sales/invoice_create.html', {
        'page_title':          'فاکتور فروش جدید',
        'customers':           customers,
        'warehouses':          warehouses,
        'products':            products,
        'bankers':             bankers,
        'default_warehouse':   default_warehouse,
        'today':               timezone.now().date(),
        'today_jalali':        to_jalali_str(timezone.now().date()),
        'current_jalali_year': current_jalali_year,
        'payment_methods':     Payment.PaymentMethod.choices,
        'currency_choices':    Invoice.Currency.choices,
        'default_currency':    BusinessSettings.get_solo().default_currency,
    })


# ══════════════════════════════════════════════════════════════
# INVOICE DETAIL
# ══════════════════════════════════════════════════════════════

@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related(
            'customer', 'warehouse', 'created_by', 'banker'
        ).prefetch_related('items__product__unit', 'payments'),
        pk=pk,
        is_deleted=False
    )

    bankers = Banker.objects.filter(is_active=True, is_deleted=False).order_by('name')

    payment_form = PaymentForm(
        invoice=invoice,
        initial={
            'payment_date': timezone.now().date(),
            'amount': invoice.remaining_amount,
            'currency': invoice.currency,
        }
    )

    if request.method == 'POST' and 'add_payment' in request.POST:
        payment_form = PaymentForm(request.POST, invoice=invoice)
        if payment_form.is_valid():
            cd = payment_form.cleaned_data
            try:
                banker = None
                banker_id = request.POST.get('banker_id')
                if cd['payment_method'] == 'saraf':
                    if not banker_id:
                        raise ValueError('برای پرداخت از طریق صراف، صراف را انتخاب کنید.')
                    banker = Banker.objects.get(
                        pk=banker_id, is_active=True, is_deleted=False
                    )

                SalesService.add_payment(
                    invoice=invoice,
                    amount=cd['amount'],
                    payment_method=cd['payment_method'],
                    payment_date=cd['payment_date'],
                    currency=cd['currency'],
                    exchange_rate=cd.get('exchange_rate') or Decimal('1'),
                    notes=cd.get('notes', ''),
                    user=request.user,
                )

                if banker:
                    from apps.banker.services import BankerService
                    BankerService.apply_sale_payment(
                        banker=banker,
                        amount=cd['amount'],
                        currency=cd['currency'],
                        sale_invoice=invoice,
                        transaction_date=cd['payment_date'],
                        user=request.user,
                    )

                messages.success(request, 'پرداخت با موفقیت ثبت شد.')
                return redirect('sales:invoice_detail', pk=pk)
            except Exception as e:
                _safe_rollback()
                messages.error(request, str(e))

    return render(request, 'sales/invoice_detail.html', {
        'page_title': f'فاکتور {invoice.invoice_number}',
        'invoice': invoice,
        'payment_form': payment_form,
        'bankers': bankers,
    })


# ══════════════════════════════════════════════════════════════
# INVOICE PRINT
# ══════════════════════════════════════════════════════════════

@login_required
def invoice_print(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer', 'warehouse', 'created_by')
                       .prefetch_related('items__product'),
        pk=pk
    )

    # ── FIX: live "previous debt" instead of the frozen invoice.previous_debt ──
    #
    # invoice.previous_debt is a snapshot captured once, at invoice-creation
    # time. It is intentionally left untouched here because the invoice
    # detail page uses that exact frozen value for its historical warning
    # ("بدهی قبلی مشتری در زمان صدور فاکتور") — that warning is supposed to
    # describe what the customer owed *at that moment*, and must not change
    # later.
    #
    # The print page is different: its "حساب سابقه" / "مبلغ قابل پرداخت" /
    # "الباقی" figures are meant to describe what the customer currently
    # owes. If a later payment (e.g. made from the customer page) gets
    # split between this invoice and older debt, the frozen snapshot goes
    # stale and the print page keeps showing an inflated amount forever.
    # So for print purposes only, we compute the customer's live balance.
    customer = invoice.customer
    if invoice.currency == Invoice.Currency.USD:
        live_customer_balance = customer.total_debt_usd - customer.advance_balance_usd
    else:
        live_customer_balance = customer.total_debt - customer.advance_balance

    # Subtract this invoice's own remaining amount so it isn't double-counted
    # (it's already included once inside customer.total_debt, and again as
    # this invoice's own "الباقی" row).
    current_previous_debt = live_customer_balance - invoice.remaining_amount

    return render(request, 'sales/invoice_print.html', {
        'invoice': invoice,
        'is_usd': invoice.currency == 'USD',
        'current_previous_debt': current_previous_debt,
    })


# ══════════════════════════════════════════════════════════════
# CANCEL INVOICE
# ══════════════════════════════════════════════════════════════

@login_required
@require_POST
def invoice_cancel(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, is_deleted=False)
    try:
        SalesService.cancel_invoice(invoice, user=request.user)
        messages.success(
            request,
            f'فاکتور {invoice.invoice_number} لغو شد و موجودی برگشت داده شد.'
        )
    except Exception as e:
        _safe_rollback()
        messages.error(request, str(e))
    return redirect('sales:invoice_list')


# ══════════════════════════════════════════════════════════════
# EDIT INVOICE
# ══════════════════════════════════════════════════════════════

@login_required
def invoice_edit(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer', 'warehouse', 'banker')
                       .prefetch_related('items__product__unit'),
        pk=pk, is_deleted=False
    )

    if invoice.status == Invoice.Status.CANCELLED:
        messages.error(request, 'فاکتور لغو شده قابل ویرایش نیست.')
        return redirect('sales:invoice_list')

    customers  = Customer.objects.filter(is_active=True, is_deleted=False).order_by('name')
    warehouses = Warehouse.objects.filter(is_active=True, is_deleted=False)
    products   = Product.objects.filter(
                     is_active=True, is_deleted=False
                 ).select_related('unit', 'category').order_by('name')
    bankers    = Banker.objects.filter(is_active=True, is_deleted=False).order_by('name')

    existing_items = []
    for item in invoice.items.all():
        existing_items.append({
            'product_id':       str(item.product.pk),
            'product_name':     item.product.name,
            'unit':             item.product.unit.abbreviation if item.product.unit else '',
            'quantity':         float(item.quantity),
            'unit_price':       float(item.unit_price),
            'discount_percent': float(item.discount_percent),
            'line_total':       float(item.line_total),
        })

    if request.method == 'POST':
        try:
            customer_id       = request.POST.get('customer_id')
            warehouse_id      = request.POST.get('warehouse_id')
            invoice_date_raw  = request.POST.get('invoice_date')  # Jalali string
            paid_amount       = Decimal(request.POST.get('paid_amount', '0') or '0')
            payment_method    = request.POST.get('payment_method', 'cash')
            currency          = request.POST.get('currency', 'AFN')
            banker_id         = request.POST.get('banker_id')
            notes             = request.POST.get('notes', '')
            items_json        = request.POST.get('items_json', '[]')
            items_data        = json.loads(items_json)

            if not customer_id:
                raise ValueError('مشتری را انتخاب کنید.')
            if not warehouse_id:
                raise ValueError('انبار را انتخاب کنید.')
            if not invoice_date_raw:
                raise ValueError('تاریخ فاکتور را وارد کنید.')
            if not items_data:
                raise ValueError('فاکتور باید حداقل یک ردیف داشته باشد.')

            invoice_date = jalali_str_to_gregorian(invoice_date_raw)

            customer  = Customer.objects.get(pk=customer_id, is_deleted=False)
            warehouse = Warehouse.objects.get(pk=warehouse_id, is_deleted=False)

            banker = None
            if payment_method == Payment.PaymentMethod.SARAF:
                if not banker_id:
                    raise ValueError('برای پرداخت از طریق صراف، صراف را انتخاب کنید.')
                banker = Banker.objects.get(pk=banker_id, is_deleted=False, is_active=True)

            items = []
            for item in items_data:
                product = Product.objects.get(pk=item['product_id'], is_deleted=False)
                items.append({
                    'product':          product,
                    'quantity':         Decimal(str(item['quantity'])),
                    'unit_price':       Decimal(str(item['unit_price'])),
                    'discount_percent': Decimal(str(item.get('discount_percent', '0'))),
                })

            SalesService.edit_invoice(
                invoice=invoice,
                customer=customer,
                warehouse=warehouse,
                items=items,
                invoice_date=invoice_date,
                paid_amount=paid_amount,
                payment_method=payment_method,
                currency=currency,
                banker=banker,
                notes=notes,
                user=request.user,
            )
            messages.success(request, f'فاکتور {invoice.invoice_number} با موفقیت ویرایش شد.')
            return redirect('sales:invoice_detail', pk=invoice.pk)

        except Exception as e:
            _safe_rollback()
            messages.error(request, str(e))

    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'sales/invoice_edit.html', {
        'page_title':          f'ویرایش فاکتور {invoice.invoice_number}',
        'invoice':             invoice,
        'customers':           customers,
        'warehouses':          warehouses,
        'products':            products,
        'bankers':             bankers,
        'existing_items_json': json.dumps(existing_items),
        'payment_methods':     Payment.PaymentMethod.choices,
        'currency_choices':    Invoice.Currency.choices,
        'invoice_date_jalali': to_jalali_str(invoice.invoice_date),
        'current_jalali_year': current_jalali_year,
    })


# ══════════════════════════════════════════════════════════════
# AJAX ENDPOINTS
# ══════════════════════════════════════════════════════════════

@login_required
def get_product_price(request):
    """AJAX: Get product sale price and stock info."""
    product_id   = request.GET.get('product_id')
    warehouse_id = request.GET.get('warehouse_id')
    try:
        product = Product.objects.select_related('unit').get(
            pk=product_id, is_deleted=False
        )
        data = {
            'success':       True,
            'name':          product.name,
            'sale_price':    float(product.sale_price),
            'current_stock': float(product.current_stock),
            'unit':          product.unit.abbreviation if product.unit else '',
        }
        if warehouse_id:
            from apps.warehouse.models import StockBatch
            from django.db.models import Sum
            wh_stock = StockBatch.objects.filter(
                product=product,
                warehouse_id=warehouse_id,
                remaining_quantity__gt=0,
                is_deleted=False,
            ).aggregate(total=Sum('remaining_quantity'))['total'] or 0
            data['warehouse_stock'] = float(wh_stock)
        return JsonResponse(data)
    except Product.DoesNotExist:
        return JsonResponse({'success': False})

@login_required
def get_warehouse_stock(request):
    """AJAX: Get per-product stock quantities for a single warehouse.

    Returns a map of {product_id: remaining_quantity} covering only
    batches in the given warehouse. Products with no batches there are
    simply absent from the map (front-end treats missing = 0).
    """
    warehouse_id = request.GET.get('warehouse_id')
    if not warehouse_id:
        return JsonResponse({'success': False})

    from apps.warehouse.models import StockBatch
    from django.db.models import Sum

    rows = StockBatch.objects.filter(
        warehouse_id=warehouse_id,
        remaining_quantity__gt=0,
        is_deleted=False,
    ).values('product_id').annotate(total=Sum('remaining_quantity'))

    stock_map = {str(row['product_id']): float(row['total']) for row in rows}

    return JsonResponse({'success': True, 'stock': stock_map})

@login_required
def get_customer_info(request):
    """AJAX: Get customer debt info."""
    customer_id = request.GET.get('customer_id')
    try:
        customer = Customer.objects.get(pk=customer_id, is_deleted=False)
        debt     = SalesService.get_customer_debt(customer)
        debt_usd = SalesService.get_customer_debt_usd(customer)
        return JsonResponse({
            'success':           True,
            'name':              customer.name,
            'phone':             customer.phone,
            'debt':              float(debt),
            'debt_usd':          float(debt_usd),
            'credit_limit':      float(customer.credit_limit),
            'credit_limit_usd':  float(customer.credit_limit_usd),
        })
    except Customer.DoesNotExist:
        return JsonResponse({'success': False})