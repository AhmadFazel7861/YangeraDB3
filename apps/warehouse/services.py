"""
FIFO Warehouse Service — the core accounting engine.
Now supports backorders: selling more than is currently in stock,
and auto-fulfilling those backorders when new stock is received.
"""
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError

from apps.inventory.models import Product, StockHistory
from .models import Warehouse, StockBatch, BatchMovement, Backorder


class FIFOService:

    @staticmethod
    @transaction.atomic
    def receive_stock(
        product: Product,
        warehouse: Warehouse,
        quantity: Decimal,
        unit_cost: Decimal,
        unit_cost_usd: Decimal = Decimal('0'),
        exchange_rate: Decimal = Decimal('1'),
        expiry_date=None,
        manufactured_date=None,
        purchase_reference: str = '',
        supplier_name: str = '',
        notes: str = '',
        user=None
    ) -> StockBatch:
        if quantity <= 0:
            raise ValidationError('مقدار باید بیشتر از صفر باشد.')
        if unit_cost < 0:
            raise ValidationError('قیمت خرید نمی‌تواند منفی باشد.')

        batch = StockBatch.objects.create(
            warehouse=warehouse,
            product=product,
            initial_quantity=quantity,
            remaining_quantity=quantity,
            unit_cost=unit_cost,
            unit_cost_usd=unit_cost_usd,
            exchange_rate=exchange_rate,
            expiry_date=expiry_date,
            manufactured_date=manufactured_date,
            purchase_reference=purchase_reference,
            supplier_name=supplier_name,
            notes=notes,
            received_by=user,
        )

        product_locked = Product.objects.select_for_update().get(pk=product.pk)
        stock_before = product_locked.current_stock
        product_locked.current_stock += quantity
        product_locked.save(update_fields=['current_stock', 'updated_at'])

        StockHistory.objects.create(
            product=product,
            movement_type=StockHistory.MovementType.PURCHASE,
            quantity=quantity,
            quantity_before=stock_before,
            quantity_after=product_locked.current_stock,
            unit_cost=unit_cost,
            reference=purchase_reference or batch.batch_number,
            notes=notes,
            created_by=user,
        )

        # ── Fulfill open backorders for this product/warehouse FIRST ──
        # Oldest backorder gets priority (FIFO). This consumes from the
        # batch we just created and pulls the equivalent quantity back
        # out of current_stock, since that stock is already "owned" by
        # the customer who bought it earlier — it must not become
        # generally available again.
        FIFOService._fulfill_backorders(product, warehouse, batch, user=user)

        return batch

    @staticmethod
    @transaction.atomic
    def _fulfill_backorders(product, warehouse, batch, user=None):
        """
        Consumes the freshly received batch against any OPEN backorders
        for this product/warehouse, oldest first. Also retroactively
        corrects the FIFO cost on the original InvoiceItem/Invoice for
        the portion that gets fulfilled now.
        """
        open_backorders = Backorder.objects.select_for_update().filter(
            product=product,
            warehouse=warehouse,
            status=Backorder.Status.OPEN,
            is_deleted=False,
        ).order_by('created_at')

        batch = StockBatch.objects.select_for_update().get(pk=batch.pk)

        for bo in open_backorders:
            if batch.remaining_quantity <= 0:
                break
            outstanding = bo.quantity_remaining
            if outstanding <= 0:
                continue

            take = min(outstanding, batch.remaining_quantity)

            # ── FIX: use USD cost if this batch was purchased in USD ──
            is_usd_batch = batch.unit_cost_usd > 0
            effective_cost = batch.unit_cost_usd if is_usd_batch else batch.unit_cost
            cost_for_this = take * effective_cost

            # Pull stock out of the batch and out of current_stock —
            # this stock belongs to the earlier sale, not new availability.
            batch.remaining_quantity -= take
            batch.save(update_fields=['remaining_quantity', 'updated_at'])

            product_locked = Product.objects.select_for_update().get(pk=product.pk)
            product_locked.current_stock -= take
            if product_locked.current_stock < 0:
                product_locked.current_stock = Decimal('0')
            product_locked.save(update_fields=['current_stock', 'updated_at'])

            BatchMovement.objects.create(
                batch=batch,
                movement_type=BatchMovement.MovementType.SALE,
                quantity=take,
                unit_cost_at_time=effective_cost,
                reference=bo.created_reference or (
                    bo.invoice.invoice_number if bo.invoice_id else ''
                ),
                created_by=user,
            )

            bo.quantity_fulfilled += take
            bo.total_cost_fulfilled += cost_for_this
            if bo.quantity_remaining <= 0:
                bo.status = Backorder.Status.FULFILLED
            bo.save(update_fields=[
                'quantity_fulfilled', 'total_cost_fulfilled', 'status', 'updated_at'
            ])

            # Retroactively correct the cost on the original invoice item
            try:
                item = bo.invoice_item
                item.total_cost_fifo = (item.total_cost_fifo or Decimal('0')) + cost_for_this
                if item.quantity:
                    item.unit_cost_fifo = item.total_cost_fifo / item.quantity
                item.save(update_fields=['total_cost_fifo', 'unit_cost_fifo'])

                invoice = item.invoice
                invoice.total_cost = (invoice.total_cost or Decimal('0')) + cost_for_this
                invoice.save(update_fields=['total_cost', 'updated_at'])
            except Exception:
                pass  # never block stock receiving due to cost back-fill issues

    @staticmethod
    @transaction.atomic
    def consume_stock(
        product: Product,
        warehouse: Warehouse,
        quantity: Decimal,
        movement_type: str = BatchMovement.MovementType.SALE,
        reference: str = '',
        user=None,
        allow_backorder: bool = False,
    ) -> dict:
        """
        Consumes stock FIFO-style.

        If allow_backorder=False (default — used for non-sale movements
        like adjustments/transfers/damage), behavior is unchanged: raises
        ValidationError if stock is insufficient.

        If allow_backorder=True (used for sales), consumes whatever is
        actually available now (possibly 0) and returns the unfulfilled
        amount as 'shortfall' instead of raising. The caller (SalesService)
        is responsible for creating a Backorder record for the shortfall.
        """
        if quantity <= 0:
            raise ValidationError('مقدار باید بیشتر از صفر باشد.')

        available_batches = StockBatch.objects.select_for_update().filter(
            product=product,
            warehouse=warehouse,
            remaining_quantity__gt=0,
            is_deleted=False,
        ).order_by('created_at')

        total_available = sum(b.remaining_quantity for b in available_batches)

        if total_available < quantity and not allow_backorder:
            raise ValidationError(
                f'موجودی کافی نیست. موجودی انبار: {total_available} | '
                f'درخواست شده: {quantity}'
            )

        # Consume whatever is actually available (may be less than requested
        # when allow_backorder=True and stock is insufficient/zero).
        qty_to_consume_now = min(quantity, total_available)
        shortfall = quantity - qty_to_consume_now

        remaining_to_consume = qty_to_consume_now
        batches_consumed = []
        total_cost = Decimal('0')

        for batch in available_batches:
            if remaining_to_consume <= 0:
                break

            take_from_batch = min(batch.remaining_quantity, remaining_to_consume)

            # ── FIX: use USD cost if this batch was purchased in USD ──
            is_usd_batch = batch.unit_cost_usd > 0
            effective_cost = batch.unit_cost_usd if is_usd_batch else batch.unit_cost
            cost_for_this  = take_from_batch * effective_cost

            batch.remaining_quantity -= take_from_batch
            batch.save(update_fields=['remaining_quantity', 'updated_at'])

            BatchMovement.objects.create(
                batch=batch,
                movement_type=movement_type,
                quantity=take_from_batch,
                unit_cost_at_time=effective_cost,
                reference=reference,
                created_by=user,
            )

            batches_consumed.append({
                'batch': batch,
                'quantity': take_from_batch,
                'unit_cost': effective_cost,
                'total_cost': cost_for_this,
            })

            total_cost           += cost_for_this
            remaining_to_consume -= take_from_batch

        product_locked = Product.objects.select_for_update().get(pk=product.pk)
        stock_before = product_locked.current_stock
        product_locked.current_stock -= qty_to_consume_now
        if product_locked.current_stock < 0:
            product_locked.current_stock = Decimal('0')
        product_locked.save(update_fields=['current_stock', 'updated_at'])

        if qty_to_consume_now > 0:
            StockHistory.objects.create(
                product=product,
                movement_type=(
                    StockHistory.MovementType.SALE
                    if movement_type == BatchMovement.MovementType.SALE
                    else StockHistory.MovementType.ADJUSTMENT
                ),
                quantity=-qty_to_consume_now,
                quantity_before=stock_before,
                quantity_after=product_locked.current_stock,
                unit_cost=total_cost / qty_to_consume_now if qty_to_consume_now else Decimal('0'),
                reference=reference,
                created_by=user,
            )

        avg_cost = total_cost / qty_to_consume_now if qty_to_consume_now else Decimal('0')

        return {
            'batches_consumed': batches_consumed,
            'total_cost': total_cost,
            'average_cost': avg_cost,
            'quantity_fulfilled': qty_to_consume_now,
            'shortfall': shortfall,
        }

    @staticmethod
    def get_fifo_cost_preview(
        product: Product,
        warehouse: Warehouse,
        quantity: Decimal
    ) -> dict:
        batches = StockBatch.objects.filter(
            product=product,
            warehouse=warehouse,
            remaining_quantity__gt=0,
            is_deleted=False,
        ).order_by('created_at')

        remaining  = quantity
        total_cost = Decimal('0')
        layers     = []

        for batch in batches:
            if remaining <= 0:
                break
            take = min(batch.remaining_quantity, remaining)
            # ── FIX: use USD cost if this batch was purchased in USD ──
            is_usd_batch = batch.unit_cost_usd > 0
            effective_cost = batch.unit_cost_usd if is_usd_batch else batch.unit_cost
            cost = take * effective_cost
            layers.append({
                'batch_number': batch.batch_number,
                'quantity': take,
                'unit_cost': effective_cost,
                'total': cost,
            })
            total_cost += cost
            remaining  -= take

        can_fulfill = remaining <= 0

        return {
            'can_fulfill': can_fulfill,
            'layers': layers,
            'total_cost': total_cost,
            'average_cost': total_cost / quantity if quantity and can_fulfill else Decimal('0'),
            'shortfall': remaining if remaining > 0 else Decimal('0'),
        }


class WarehouseValuationService:

    @staticmethod
    def get_total_valuation(warehouse=None):
        """
        AFN and USD calculated SEPARATELY.
        - AFN batches: unit_cost_usd = 0  → summed via unit_cost (افغانی)
        - USD batches: unit_cost_usd > 0  → summed via unit_cost_usd (دالر)
        AFN equivalent of USD batches is also stored in unit_cost,
        so total_value_all_afn gives the combined AFN value.
        """
        from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Count

        qs = StockBatch.objects.filter(
            remaining_quantity__gt=0,
            is_deleted=False,
        )
        if warehouse:
            qs = qs.filter(warehouse=warehouse)

        # AFN batches (bought in AFN)
        afn_qs     = qs.filter(unit_cost_usd=0)
        afn_result = afn_qs.aggregate(
            total_value=Sum(
                ExpressionWrapper(
                    F('remaining_quantity') * F('unit_cost'),
                    output_field=DecimalField(max_digits=20, decimal_places=2)
                )
            ),
            total_units=Sum('remaining_quantity'),
            total_batches=Count('id'),
        )

        # USD batches (bought in USD)
        usd_qs     = qs.filter(unit_cost_usd__gt=0)
        usd_result = usd_qs.aggregate(
            total_value_usd=Sum(
                ExpressionWrapper(
                    F('remaining_quantity') * F('unit_cost_usd'),
                    output_field=DecimalField(max_digits=20, decimal_places=4)
                )
            ),
            total_value_afn_equiv=Sum(
                ExpressionWrapper(
                    F('remaining_quantity') * F('unit_cost'),
                    output_field=DecimalField(max_digits=20, decimal_places=2)
                )
            ),
            total_units_usd=Sum('remaining_quantity'),
            total_batches_usd=Count('id'),
        )

        total_afn_value = (
            (afn_result['total_value']            or Decimal('0')) +
            (usd_result['total_value_afn_equiv']  or Decimal('0'))
        )

        return {
            # Pure AFN batches
            'total_value':         afn_result['total_value']       or Decimal('0'),
            'total_units':         afn_result['total_units']       or Decimal('0'),
            'total_batches':       afn_result['total_batches']     or 0,
            # Pure USD batches
            'total_value_usd':     usd_result['total_value_usd']   or Decimal('0'),
            'total_units_usd':     usd_result['total_units_usd']   or Decimal('0'),
            'total_batches_usd':   usd_result['total_batches_usd'] or 0,
            # Combined (all batches)
            'total_value_all_afn': total_afn_value,
            'total_batches_all':   (afn_result['total_batches']    or 0) +
                                   (usd_result['total_batches_usd'] or 0),
            'total_units_all':     (afn_result['total_units']      or Decimal('0')) +
                                   (usd_result['total_units_usd']  or Decimal('0')),
        }

    @staticmethod
    def get_product_valuation(warehouse=None):
        from django.db.models import (
            Sum, F, ExpressionWrapper, DecimalField, Count
        )

        qs = StockBatch.objects.filter(
            remaining_quantity__gt=0,
            is_deleted=False,
        )
        if warehouse:
            qs = qs.filter(warehouse=warehouse)

        return qs.values(
            'product__id',
            'product__name',
            'product__code',
            'product__unit__abbreviation',
            'product__category__name',
        ).annotate(
            total_quantity=Sum('remaining_quantity'),
            total_value=Sum(
                ExpressionWrapper(
                    F('remaining_quantity') * F('unit_cost'),
                    output_field=DecimalField(max_digits=20, decimal_places=2)
                )
            ),
            total_value_usd=Sum(
                ExpressionWrapper(
                    F('remaining_quantity') * F('unit_cost_usd'),
                    output_field=DecimalField(max_digits=20, decimal_places=4)
                )
            ),
            batch_count=Count('id'),
            avg_cost=ExpressionWrapper(
                Sum(
                    ExpressionWrapper(
                        F('remaining_quantity') * F('unit_cost'),
                        output_field=DecimalField(max_digits=20, decimal_places=2)
                    )
                ) / Sum('remaining_quantity'),
                output_field=DecimalField(max_digits=14, decimal_places=4)
            ),
            avg_cost_usd=ExpressionWrapper(
                Sum(
                    ExpressionWrapper(
                        F('remaining_quantity') * F('unit_cost_usd'),
                        output_field=DecimalField(max_digits=20, decimal_places=4)
                    )
                ) / Sum('remaining_quantity'),
                output_field=DecimalField(max_digits=14, decimal_places=4)
            ),
        ).order_by('-total_value')

    @staticmethod
    def get_expiring_batches(days=30):
        from django.utils import timezone
        from datetime import timedelta

        cutoff = timezone.now().date() + timedelta(days=days)
        return StockBatch.objects.filter(
            remaining_quantity__gt=0,
            is_deleted=False,
            expiry_date__isnull=False,
            expiry_date__lte=cutoff,
            expiry_date__gte=timezone.now().date(),
        ).select_related(
            'product', 'warehouse', 'product__unit'
        ).order_by('expiry_date')

    @staticmethod
    def get_expired_batches():
        from django.utils import timezone
        return StockBatch.objects.filter(
            remaining_quantity__gt=0,
            is_deleted=False,
            expiry_date__isnull=False,
            expiry_date__lt=timezone.now().date(),
        ).select_related(
            'product', 'warehouse', 'product__unit'
        ).order_by('expiry_date')


import django.db.models as models