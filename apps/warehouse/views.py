"""
Warehouse Views — Phase 3 + Pending Delivery
"""
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, F, ExpressionWrapper, DecimalField
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Warehouse, StockBatch, BatchMovement, PendingDelivery
from .forms import WarehouseForm, StockReceiveForm
from .services import FIFOService, WarehouseValuationService
from apps.inventory.models import Product


# ══════════════════════════════════════════════════════════════
# WAREHOUSE VIEWS
# ══════════════════════════════════════════════════════════════

@login_required
def warehouse_list(request):
    warehouses = Warehouse.objects.filter(
        is_deleted=False
    ).order_by('-is_default', 'name')

    return render(request, 'warehouse/warehouse_list.html', {
        'page_title': 'انبارها',
        'warehouses': warehouses,
    })


@login_required
def warehouse_create(request):
    form = WarehouseForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'انبار با موفقیت ثبت شد.')
        return redirect('warehouse:warehouse_list')
    return render(request, 'warehouse/warehouse_form.html', {
        'page_title': 'انبار جدید',
        'form': form,
        'action': 'ثبت',
    })


@login_required
def warehouse_edit(request, pk):
    warehouse = get_object_or_404(Warehouse, pk=pk, is_deleted=False)
    form = WarehouseForm(request.POST or None, instance=warehouse)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'انبار ویرایش شد.')
        return redirect('warehouse:warehouse_list')
    return render(request, 'warehouse/warehouse_form.html', {
        'page_title': 'ویرایش انبار',
        'form': form,
        'action': 'ویرایش',
        'object': warehouse,
    })


@login_required
@require_POST
def warehouse_delete(request, pk):
    warehouse = get_object_or_404(Warehouse, pk=pk, is_deleted=False)

    if warehouse.is_default:
        messages.error(request, 'انبار پیشفرض را نمی‌توان حذف کرد.')
        return redirect('warehouse:warehouse_list')

    has_stock = StockBatch.objects.filter(
        warehouse=warehouse,
        remaining_quantity__gt=0,
        is_deleted=False,
    ).exists()
    if has_stock:
        messages.error(
            request,
            f'انبار «{warehouse.name}» دارای موجودی فعال است و قابل حذف نیست.'
        )
        return redirect('warehouse:warehouse_list')

    warehouse.is_deleted = True
    warehouse.save(update_fields=['is_deleted'])
    messages.success(request, f'انبار «{warehouse.name}» حذف شد.')
    return redirect('warehouse:warehouse_list')


@login_required
def warehouse_detail(request, pk):
    warehouse = get_object_or_404(Warehouse, pk=pk, is_deleted=False)

    search = request.GET.get('q', '').strip()
    tab    = request.GET.get('tab', 'stock')   # 'stock' or 'pending'

    # ── Stock batches (existing) ──
    batches = StockBatch.objects.filter(
        warehouse=warehouse,
        remaining_quantity__gt=0,
        is_deleted=False,
    ).select_related('product', 'product__unit', 'product__category')

    if search and tab == 'stock':
        batches = batches.filter(
            Q(product__name__icontains=search) |
            Q(batch_number__icontains=search)
        )

    batches = batches.order_by('product__name', 'created_at')
    paginator = Paginator(batches, 25)
    batches_page = paginator.get_page(request.GET.get('page'))

    # ── Pending deliveries ──
    pending_qs = PendingDelivery.objects.filter(
        warehouse=warehouse,
        status=PendingDelivery.Status.PENDING,
    ).select_related('customer', 'product', 'product__unit', 'invoice')

    if search and tab == 'pending':
        pending_qs = pending_qs.filter(
            Q(customer__name__icontains=search) |
            Q(product__name__icontains=search) |
            Q(invoice__invoice_number__icontains=search)
        )

    pending_qs = pending_qs.order_by('invoice_date', 'customer__name')
    pending_paginator = Paginator(pending_qs, 25)
    pending_page = pending_paginator.get_page(request.GET.get('ppage'))

    # ── Valuation ──
    valuation = WarehouseValuationService.get_total_valuation(warehouse)
    # Add USD value
    valuation['total_value_usd'] = warehouse.total_value_usd

    # ── Pending counts for badge ──
    pending_count = PendingDelivery.objects.filter(
        warehouse=warehouse,
        status=PendingDelivery.Status.PENDING,
    ).count()

    return render(request, 'warehouse/warehouse_detail.html', {
        'page_title': warehouse.name,
        'warehouse': warehouse,
        'batches': batches_page,
        'pending_deliveries': pending_page,
        'pending_count': pending_count,
        'search': search,
        'tab': tab,
        'valuation': valuation,
        'total': paginator.count,
        'pending_total': pending_paginator.count,
    })


# ══════════════════════════════════════════════════════════════
# PENDING DELIVERY — EXIT (خروج)
# ══════════════════════════════════════════════════════════════

@login_required
@require_POST
def delivery_exit(request, delivery_pk):
    """Mark a pending delivery as delivered (customer collected goods)."""
    delivery = get_object_or_404(
        PendingDelivery,
        pk=delivery_pk,
        status=PendingDelivery.Status.PENDING,
    )
    notes = request.POST.get('notes', '')

    delivery.status             = PendingDelivery.Status.DELIVERED
    delivery.quantity_delivered = delivery.quantity
    delivery.delivered_at       = timezone.now()
    delivery.delivered_by       = request.user
    delivery.notes              = notes
    delivery.save(update_fields=[
        'status', 'quantity_delivered', 'delivered_at', 'delivered_by', 'notes', 'updated_at'
    ])

    messages.success(
        request,
        f'تحویل {delivery.quantity} {delivery.product.unit.abbreviation if delivery.product.unit else ""} '
        f'«{delivery.product.name}» به مشتری «{delivery.customer.name}» ثبت شد.'
    )
    return redirect(
        f"{request.META.get('HTTP_REFERER', '')}".split('?')[0]
        + f'?tab=pending'
        or f'/warehouse/{delivery.warehouse.pk}/?tab=pending'
    )


@login_required
@require_POST
def delivery_cancel(request, delivery_pk):
    """Cancel a pending delivery (e.g. invoice was cancelled)."""
    delivery = get_object_or_404(
        PendingDelivery,
        pk=delivery_pk,
        status=PendingDelivery.Status.PENDING,
    )
    delivery.status = PendingDelivery.Status.CANCELLED
    delivery.notes  = request.POST.get('notes', 'لغو شد')
    delivery.save(update_fields=['status', 'notes', 'updated_at'])

    messages.success(request, 'تحویل لغو شد.')
    return redirect('warehouse:warehouse_detail', pk=delivery.warehouse.pk)


@login_required
def delivery_history(request, pk):
    """View delivered/cancelled items for a warehouse."""
    warehouse = get_object_or_404(Warehouse, pk=pk, is_deleted=False)

    status_filter = request.GET.get('status', 'delivered')
    search        = request.GET.get('q', '').strip()

    qs = PendingDelivery.objects.filter(
        warehouse=warehouse,
        status=status_filter,
    ).select_related('customer', 'product', 'product__unit', 'invoice', 'delivered_by')

    if search:
        qs = qs.filter(
            Q(customer__name__icontains=search) |
            Q(product__name__icontains=search) |
            Q(invoice__invoice_number__icontains=search)
        )

    qs = qs.order_by('-delivered_at', '-created_at')
    paginator = Paginator(qs, 25)
    page      = paginator.get_page(request.GET.get('page'))

    return render(request, 'warehouse/delivery_history.html', {
        'page_title': f'تاریخچه تحویل — {warehouse.name}',
        'warehouse': warehouse,
        'deliveries': page,
        'search': search,
        'status_filter': status_filter,
        'total': paginator.count,
    })


# ══════════════════════════════════════════════════════════════
# STOCK RECEIVE
# ══════════════════════════════════════════════════════════════

@login_required
def stock_receive(request):
    form = StockReceiveForm(request.POST or None)

    if request.method == 'GET':
        default_wh = Warehouse.get_default()
        if default_wh:
            form.fields['warehouse'].initial = default_wh

    if request.method == 'POST' and form.is_valid():
        cd = form.cleaned_data
        try:
            batch = FIFOService.receive_stock(
                product=cd['product'],
                warehouse=cd['warehouse'],
                quantity=cd['quantity'],
                unit_cost=cd['unit_cost'],
                unit_cost_usd=cd.get('unit_cost_usd') or Decimal('0'),
                expiry_date=cd.get('expiry_date'),
                manufactured_date=cd.get('manufactured_date'),
                purchase_reference=cd.get('purchase_reference', ''),
                supplier_name=cd.get('supplier_name', ''),
                notes=cd.get('notes', ''),
                user=request.user,
            )
            messages.success(
                request,
                f'موجودی دریافت شد. بچ: {batch.batch_number} | '
                f'مقدار: {batch.initial_quantity} | '
                f'قیمت: {batch.unit_cost:,.0f} ؋'
            )
            return redirect('warehouse:warehouse_detail', pk=cd['warehouse'].pk)
        except Exception as e:
            messages.error(request, str(e))

    from apps.core.jalali import to_jalali_str
    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'warehouse/stock_receive.html', {
        'page_title': 'دریافت موجودی به انبار',
        'form': form,
        'current_jalali_year': current_jalali_year,
    })


# ══════════════════════════════════════════════════════════════
# BATCH VIEWS
# ══════════════════════════════════════════════════════════════

@login_required
def batch_list(request):
    search           = request.GET.get('q', '').strip()
    warehouse_filter = request.GET.get('warehouse', '')
    expiry_filter    = request.GET.get('expiry', '')

    qs = StockBatch.objects.filter(
        remaining_quantity__gt=0,
        is_deleted=False,
    ).select_related('product', 'product__unit', 'product__category', 'warehouse')

    if search:
        qs = qs.filter(
            Q(product__name__icontains=search) |
            Q(batch_number__icontains=search) |
            Q(supplier_name__icontains=search)
        )
    if warehouse_filter:
        qs = qs.filter(warehouse_id=warehouse_filter)

    if expiry_filter == 'expiring':
        from datetime import timedelta
        cutoff = timezone.now().date() + timedelta(days=30)
        qs = qs.filter(
            expiry_date__isnull=False,
            expiry_date__lte=cutoff,
            expiry_date__gte=timezone.now().date(),
        )
    elif expiry_filter == 'expired':
        qs = qs.filter(
            expiry_date__isnull=False,
            expiry_date__lt=timezone.now().date(),
        )

    qs = qs.order_by('product__name', 'created_at')
    paginator = Paginator(qs, 25)
    page      = paginator.get_page(request.GET.get('page'))

    warehouses = Warehouse.objects.filter(is_active=True, is_deleted=False)

    return render(request, 'warehouse/batch_list.html', {
        'page_title': 'بچ‌های موجودی',
        'batches': page,
        'warehouses': warehouses,
        'search': search,
        'warehouse_filter': warehouse_filter,
        'expiry_filter': expiry_filter,
        'total': paginator.count,
    })

# ══════════════════════════════════════════════════════════════
# BATCH EDIT / DELETE
# ══════════════════════════════════════════════════════════════

@login_required
def batch_edit(request, pk):
    """
    Edit a StockBatch — only safe fields:
    remaining_quantity, unit_cost, unit_cost_usd, expiry_date, notes.
    If remaining_quantity changes, product.current_stock is adjusted.
    """
    batch = get_object_or_404(StockBatch, pk=pk, is_deleted=False)
    warehouse = batch.warehouse

    if request.method == 'POST':
        try:
            new_remaining  = Decimal(request.POST.get('remaining_quantity', str(batch.remaining_quantity)))
            new_cost       = Decimal(request.POST.get('unit_cost', str(batch.unit_cost)))
            new_cost_usd   = Decimal(request.POST.get('unit_cost_usd', '0') or '0')
            new_expiry_raw = request.POST.get('expiry_date', '') or None  # Jalali string, e.g. 1405/04/11
            new_notes      = request.POST.get('notes', '')

            if new_remaining < 0:
                raise ValueError('مقدار باقی‌مانده نمی‌تواند منفی باشد.')
            if new_remaining > batch.initial_quantity:
                raise ValueError(
                    f'مقدار باقی‌مانده ({new_remaining}) نمی‌تواند بیشتر از '
                    f'مقدار اولیه ({batch.initial_quantity}) باشد.'
                )
            if new_cost < 0:
                raise ValueError('قیمت خرید نمی‌تواند منفی باشد.')

            from django.db import transaction as db_transaction
            with db_transaction.atomic():
                qty_diff = new_remaining - batch.remaining_quantity

                batch.remaining_quantity = new_remaining
                batch.unit_cost          = new_cost
                batch.unit_cost_usd      = new_cost_usd
                batch.notes              = new_notes
                if new_expiry_raw:
                    from apps.core.jalali import jalali_str_to_gregorian
                    batch.expiry_date = jalali_str_to_gregorian(new_expiry_raw)
                else:
                    batch.expiry_date = None

                # Remove the remaining_lte_initial constraint check issue
                # by saving with update_fields
                batch.save(update_fields=[
                    'remaining_quantity', 'unit_cost', 'unit_cost_usd',
                    'expiry_date', 'notes', 'updated_at'
                ])

                # Sync product.current_stock
                if qty_diff != 0:
                    product = batch.product
                    product.current_stock = max(
                        Decimal('0'),
                        product.current_stock + qty_diff
                    )
                    product.save(update_fields=['current_stock', 'updated_at'])

                # Log adjustment movement
                if qty_diff != 0:
                    BatchMovement.objects.create(
                        batch=batch,
                        movement_type=BatchMovement.MovementType.ADJUSTMENT,
                        quantity=abs(qty_diff),
                        unit_cost_at_time=new_cost,
                        reference=f'ویرایش دستی بچ — {batch.batch_number}',
                        created_by=request.user,
                    )

            messages.success(
                request,
                f'بچ {batch.batch_number} با موفقیت ویرایش شد.'
            )
            return redirect('warehouse:warehouse_detail', pk=warehouse.pk)

        except (ValueError, Exception) as e:
            messages.error(request, str(e))

    from apps.core.jalali import to_jalali_str
    current_jalali_year = int(to_jalali_str(timezone.now().date()).split('/')[0])

    return render(request, 'warehouse/batch_edit.html', {
        'page_title': f'ویرایش بچ {batch.batch_number}',
        'batch': batch,
        'warehouse': warehouse,
        'current_jalali_year': current_jalali_year,
    })


@login_required
@require_POST
def batch_delete(request, pk):
    """
    Soft-delete a StockBatch.
    Blocked if the batch has any SALE movements (stock was sold from it).
    Subtracts remaining_quantity from product.current_stock.
    """
    batch = get_object_or_404(StockBatch, pk=pk, is_deleted=False)
    warehouse = batch.warehouse

    # Block if any sale movements exist on this batch
    has_sales = BatchMovement.objects.filter(
        batch=batch,
        movement_type=BatchMovement.MovementType.SALE,
    ).exists()

    if has_sales:
        messages.error(
            request,
            f'بچ {batch.batch_number} دارای حرکت فروش است و قابل حذف نیست. '
            f'در صورت نیاز مقدار را ویرایش کنید.'
        )
        return redirect('warehouse:warehouse_detail', pk=warehouse.pk)

    from django.db import transaction as db_transaction
    with db_transaction.atomic():
        qty_to_remove = batch.remaining_quantity

        batch.is_deleted = True
        batch.remaining_quantity = Decimal('0')
        batch.save(update_fields=['is_deleted', 'remaining_quantity', 'updated_at'])

        if qty_to_remove > 0:
            product = batch.product
            product.current_stock = max(
                Decimal('0'),
                product.current_stock - qty_to_remove
            )
            product.save(update_fields=['current_stock', 'updated_at'])

        BatchMovement.objects.create(
            batch=batch,
            movement_type=BatchMovement.MovementType.ADJUSTMENT,
            quantity=qty_to_remove,
            unit_cost_at_time=batch.unit_cost,
            reference=f'حذف دستی بچ — {batch.batch_number}',
            created_by=request.user,
        )

    messages.success(
        request,
        f'بچ {batch.batch_number} حذف شد و {qty_to_remove} واحد از موجودی کسر شد.'
    )
    return redirect('warehouse:warehouse_detail', pk=warehouse.pk)


# ══════════════════════════════════════════════════════════════
# VALUATION REPORT
# ══════════════════════════════════════════════════════════════

@login_required
def valuation_report(request):
    warehouse_filter = request.GET.get('warehouse', '')

    warehouse = None
    if warehouse_filter:
        warehouse = get_object_or_404(Warehouse, pk=warehouse_filter)

    product_valuations = WarehouseValuationService.get_product_valuation(warehouse)
    total    = WarehouseValuationService.get_total_valuation(warehouse)
    expiring = WarehouseValuationService.get_expiring_batches(30)
    expired  = WarehouseValuationService.get_expired_batches()

    warehouses = Warehouse.objects.filter(is_active=True, is_deleted=False)

    return render(request, 'warehouse/valuation.html', {
        'page_title': 'ارزیابی موجودی انبار',
        'product_valuations': product_valuations,
        'total': total,
        'expiring': expiring,
        'expired': expired,
        'warehouses': warehouses,
        'warehouse_filter': warehouse_filter,
        'selected_warehouse': warehouse,
    })


@login_required
def fifo_preview(request):
    from django.http import JsonResponse
    product_id   = request.GET.get('product_id')
    warehouse_id = request.GET.get('warehouse_id')
    quantity     = request.GET.get('quantity', '0')

    try:
        product   = Product.objects.get(pk=product_id, is_deleted=False)
        warehouse = Warehouse.objects.get(pk=warehouse_id, is_deleted=False)
        qty       = Decimal(quantity)
        preview   = FIFOService.get_fifo_cost_preview(product, warehouse, qty)
        return JsonResponse({
            'success': True,
            'can_fulfill': preview['can_fulfill'],
            'total_cost': float(preview['total_cost']),
            'average_cost': float(preview['average_cost']),
            'shortfall': float(preview['shortfall']),
            'layers': [
                {
                    'batch_number': l['batch_number'],
                    'quantity': float(l['quantity']),
                    'unit_cost': float(l['unit_cost']),
                    'total': float(l['total']),
                }
                for l in preview['layers']
            ],
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})