"""
Purchase Service Layer
Creates purchase invoices, FIFO batches, and updates supplier/banker accounts.
"""
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.warehouse.services import FIFOService
from apps.warehouse.models import Warehouse, StockBatch
from apps.suppliers.models import Supplier
from apps.inventory.models import Product
from .models import PurchaseInvoice, PurchaseItem


class PurchaseService:

    @staticmethod
    @transaction.atomic
    def create_purchase(
        supplier: Supplier,
        warehouse: Warehouse,
        items: list,
        purchase_date,
        paid_amount: Decimal = Decimal('0'),
        payment_method: str = 'cash',
        currency: str = 'AFN',
        banker=None,
        supplier_invoice_number: str = '',
        notes: str = '',
        user=None
    ) -> PurchaseInvoice:
        if not items:
            raise ValidationError('فاکتور خرید باید حداقل یک ردیف داشته باشد.')

        if currency not in dict(PurchaseInvoice.Currency.choices):
            raise ValidationError('واحد پول نامعتبر است.')

        if payment_method not in dict(PurchaseInvoice.PaymentMethod.choices):
            raise ValidationError('روش پرداخت نامعتبر است.')

        if payment_method == PurchaseInvoice.PaymentMethod.SARAF and not banker:
            raise ValidationError('برای پرداخت از طریق صراف، صراف را انتخاب کنید.')

        subtotal = Decimal('0')
        total_discount = Decimal('0')

        for item_data in items:
            qty      = item_data['quantity']
            cost     = item_data['unit_cost']
            disc     = item_data.get('discount_percent', Decimal('0'))
            gross    = qty * cost
            disc_amt = (gross * disc / 100).quantize(Decimal('0.01'))
            subtotal       += gross
            total_discount += disc_amt

        total_amount = subtotal - total_discount

        if payment_method == PurchaseInvoice.PaymentMethod.SARAF:
            # ── FIX: previously forced effective_paid = total_amount no matter
            # what the user entered as paid_amount, so a partial saraf payment
            # (e.g. 2000 of 4000) was silently treated as fully paid and the
            # whole 4000 was pulled from the saraf balance. Now it respects the
            # amount actually entered, same as any other payment method. ──
            effective_paid      = min(paid_amount, total_amount)
            effective_remaining = total_amount - effective_paid
            effective_status    = (
                PurchaseInvoice.Status.PAID if effective_remaining <= 0
                else PurchaseInvoice.Status.PARTIAL
            )
        else:
            effective_paid      = paid_amount
            effective_remaining = total_amount - paid_amount
            effective_status    = PurchaseInvoice.Status.UNPAID

        invoice = PurchaseInvoice.objects.create(
            supplier=supplier,
            warehouse=warehouse,
            purchase_date=purchase_date,
            supplier_invoice_number=supplier_invoice_number,
            subtotal=subtotal,
            discount_amount=total_discount,
            total_amount=total_amount,
            paid_amount=effective_paid,
            remaining_amount=effective_remaining,
            currency=currency,
            payment_method=payment_method,
            banker=banker if payment_method == PurchaseInvoice.PaymentMethod.SARAF else None,
            notes=notes,
            created_by=user,
            status=effective_status,
        )

        for item_data in items:
            product  = item_data['product']
            qty      = item_data['quantity']
            cost     = item_data['unit_cost']
            disc_pct = item_data.get('discount_percent', Decimal('0'))
            expiry   = item_data.get('expiry_date')

            gross    = qty * cost
            disc_amt = (gross * disc_pct / 100).quantize(Decimal('0.01'))
            net      = gross - disc_amt

            net_unit_cost = cost - (cost * disc_pct / 100)

            if currency == 'USD':
                unit_cost_usd = net_unit_cost
                unit_cost_afn = Decimal('0')
                exchange_rate = Decimal('1')
            else:
                unit_cost_usd = Decimal('0')
                unit_cost_afn = net_unit_cost
                exchange_rate = Decimal('1')

            batch = FIFOService.receive_stock(
                product=product,
                warehouse=warehouse,
                quantity=qty,
                unit_cost=unit_cost_afn,
                unit_cost_usd=unit_cost_usd,
                exchange_rate=exchange_rate,
                expiry_date=expiry,
                purchase_reference=invoice.invoice_number,
                supplier_name=supplier.name,
                notes=f'فاکتور خرید {invoice.invoice_number}',
                user=user,
            )

            PurchaseItem.objects.create(
                invoice=invoice,
                product=product,
                batch=batch,
                quantity=qty,
                unit_cost=cost,
                discount_percent=disc_pct,
                discount_amount=disc_amt,
                line_total=net,
                expiry_date=expiry,
            )

        from apps.suppliers.services.accounting import SupplierAccountingService
        SupplierAccountingService.apply_purchase(
            supplier=supplier,
            purchase_invoice=invoice,
            paid_amount=effective_paid,
            payment_method=payment_method,
            user=user,
        )

        if payment_method == PurchaseInvoice.PaymentMethod.SARAF:
            from apps.banker.services import BankerService
            BankerService.apply_purchase_payment(
                banker=banker,
                amount=effective_paid,   # ── FIX: deduct only what was actually paid, not the full invoice total ──
                currency=currency,
                purchase_invoice=invoice,
                transaction_date=purchase_date,
                user=user,
            )
        elif payment_method == PurchaseInvoice.PaymentMethod.DAKKAN and effective_paid > 0:
            from apps.capital.models import ShopIncomeTransfer
            ShopIncomeTransfer.objects.create(
                banker=None,
                purchase_invoice=invoice,
                amount=effective_paid,
                currency=currency,
                transfer_date=purchase_date,
                notes=f'پرداخت فاکتور خرید {invoice.invoice_number} — {supplier.name}',
                created_by=user,
            )

        try:
            from apps.activity_logs.services import ActivityLogService
            ActivityLogService.log_purchase_created(invoice, user=user)
        except Exception:
            pass

        return invoice

    @staticmethod
    @transaction.atomic
    def cancel_purchase(invoice: PurchaseInvoice, user=None):
        if invoice.is_deleted:
            raise ValidationError('این فاکتور قبلاً حذف شده است.')

        for item in invoice.items.all():
            if item.batch:
                batch = item.batch
                consumed = batch.initial_quantity - batch.remaining_quantity
                if consumed > 0:
                    raise ValidationError(
                        f'محصول «{item.product.name}» از این فاکتور '
                        f'در فروش استفاده شده و قابل حذف نیست.'
                    )
                product = item.product
                product.current_stock -= batch.remaining_quantity
                if product.current_stock < 0:
                    product.current_stock = Decimal('0')
                product.save(update_fields=['current_stock', 'updated_at'])

                batch.is_deleted = True
                batch.deleted_at = timezone.now()
                batch.remaining_quantity = Decimal('0')
                batch.save(update_fields=[
                    'is_deleted', 'deleted_at', 'remaining_quantity'
                ])

        try:
            from apps.suppliers.services.accounting import SupplierAccountingService
            SupplierAccountingService.reverse_purchase(
                supplier=invoice.supplier,
                purchase_invoice=invoice,
                user=user,
            )
            # ── FIX: reverse_purchase() unwinds a PAYMENT transaction by
            # crediting it into advance_balance (correct when update_purchase
            # immediately re-applies a new purchase, but wrong for a plain
            # cancellation with nothing to re-apply it to — it was showing up
            # as a phantom supplier advance). Recalculating from the
            # non-reversed ledger gives the true debt/advance state, same fix
            # already used in update_purchase(). ──
            SupplierAccountingService.recalculate_supplier_balance(invoice.supplier)
        except Exception:
            supplier = invoice.supplier
            supplier.total_debt -= invoice.total_amount
            if supplier.total_debt < 0:
                supplier.total_debt = Decimal('0')
            supplier.save(update_fields=['total_debt', 'updated_at'])

        if invoice.payment_method == PurchaseInvoice.PaymentMethod.SARAF \
                and invoice.banker and invoice.paid_amount > 0:
            from apps.banker.services import BankerService
            BankerService.reverse_purchase_payment(
                banker=invoice.banker,
                amount=invoice.paid_amount,   # ── FIX: reverse what was actually paid, not the invoice total ──
                currency=invoice.currency,
                purchase_invoice=invoice,
                user=user,
            )
        elif invoice.payment_method == PurchaseInvoice.PaymentMethod.DAKKAN:
            from apps.capital.models import ShopIncomeTransfer
            ShopIncomeTransfer.objects.filter(purchase_invoice=invoice).delete()

        invoice.is_deleted = True
        invoice.deleted_at = timezone.now()
        invoice.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

        try:
            from apps.activity_logs.services import ActivityLogService
            ActivityLogService.log(
                action='cancel',
                module='purchases',
                description=(
                    f'فاکتور خرید {invoice.invoice_number} '
                    f'لغو شد و موجودی برگشت داده شد.'
                ),
                user=user,
                model_name='PurchaseInvoice',
                object_id=str(invoice.pk),
            )
        except Exception:
            pass

    @staticmethod
    @transaction.atomic
    def add_payment(
        invoice: PurchaseInvoice,
        amount: Decimal,
        payment_method: str,
        payment_date,
        notes: str = '',
        user=None
    ):
        from apps.suppliers.services.accounting import SupplierAccountingService
        from apps.purchases.models import PurchaseInvoice as PI

        if amount <= 0:
            raise ValidationError('مبلغ پرداخت باید بیشتر از صفر باشد.')
        if amount > invoice.remaining_amount:
            raise ValidationError(
                f'مبلغ ({amount:,.0f}) بیشتر از مانده فاکتور '
                f'({invoice.remaining_amount:,.0f}) است.'
            )

        invoice.paid_amount      += amount
        invoice.remaining_amount  = invoice.total_amount - invoice.paid_amount
        if invoice.remaining_amount <= 0:
            invoice.status = PI.Status.PAID
            invoice.remaining_amount = Decimal('0')
        else:
            invoice.status = PI.Status.PARTIAL
        invoice.save(update_fields=[
            'paid_amount', 'remaining_amount', 'status', 'updated_at'
        ])

        SupplierAccountingService.apply_payment(
            supplier=invoice.supplier,
            amount=amount,
            payment_method=payment_method,
            payment_date=payment_date,
            notes=f'پرداخت فاکتور خرید {invoice.invoice_number}',
            invoice=invoice,
            user=user,
        )

        if payment_method == PurchaseInvoice.PaymentMethod.DAKKAN:
            from apps.capital.models import ShopIncomeTransfer
            ShopIncomeTransfer.objects.create(
                banker=None,
                purchase_invoice=invoice,
                amount=amount,
                currency=invoice.currency,
                transfer_date=payment_date,
                notes=f'پرداخت فاکتور خرید {invoice.invoice_number} — {invoice.supplier.name}',
                created_by=user,
            )

    @staticmethod
    @transaction.atomic
    def update_purchase(
        invoice: PurchaseInvoice,
        supplier: Supplier,
        warehouse: Warehouse,
        items: list,
        purchase_date,
        paid_amount: Decimal = Decimal('0'),
        payment_method: str = 'cash',
        currency: str = 'AFN',
        banker=None,
        supplier_invoice_number: str = '',
        notes: str = '',
        user=None
    ) -> PurchaseInvoice:
        if invoice.is_deleted:
            raise ValidationError('این فاکتور حذف شده و قابل ویرایش نیست.')

        if not items:
            raise ValidationError('فاکتور خرید باید حداقل یک ردیف داشته باشد.')

        if currency not in dict(PurchaseInvoice.Currency.choices):
            raise ValidationError('واحد پول نامعتبر است.')

        if payment_method not in dict(PurchaseInvoice.PaymentMethod.choices):
            raise ValidationError('روش پرداخت نامعتبر است.')

        if payment_method == PurchaseInvoice.PaymentMethod.SARAF and not banker:
            raise ValidationError('برای پرداخت از طریق صراف، صراف را انتخاب کنید.')

        old_items = list(invoice.items.select_related('product', 'batch').all())
        for item in old_items:
            if item.batch:
                consumed = item.batch.initial_quantity - item.batch.remaining_quantity
                if consumed > 0:
                    raise ValidationError(
                        f'محصول «{item.product.name}» از این فاکتور '
                        f'در فروش استفاده شده و فاکتور قابل ویرایش نیست.'
                    )

        # Step 1: Remove old stock batches
        for item in old_items:
            if item.batch:
                batch = item.batch
                product = item.product
                product.current_stock -= batch.remaining_quantity
                if product.current_stock < 0:
                    product.current_stock = Decimal('0')
                product.save(update_fields=['current_stock', 'updated_at'])

                batch.is_deleted = True
                batch.deleted_at = timezone.now()
                batch.remaining_quantity = Decimal('0')
                batch.save(update_fields=[
                    'is_deleted', 'deleted_at', 'remaining_quantity'
                ])

        # Step 2: Reverse old supplier accounting, then recalculate balance
        # from the full transaction ledger to eliminate any advance/debt
        # stacking artifacts caused by the reversal unwinding PAYMENT and
        # ADVANCE_USE transactions into advance_balance.
        from apps.suppliers.services.accounting import SupplierAccountingService
        try:
            SupplierAccountingService.reverse_purchase(
                supplier=invoice.supplier,
                purchase_invoice=invoice,
                user=user,
            )
        except Exception:
            old_supplier = invoice.supplier
            old_supplier.total_debt -= invoice.total_amount
            if old_supplier.total_debt < 0:
                old_supplier.total_debt = Decimal('0')
            old_supplier.save(update_fields=['total_debt', 'updated_at'])

        # Recalculate supplier balance by replaying only non-reversed
        # transactions — gives a perfectly clean slate before apply_purchase.
        SupplierAccountingService.recalculate_supplier_balance(invoice.supplier)

        # Step 3: Reverse old banker/dakkan if applicable
        if invoice.payment_method == PurchaseInvoice.PaymentMethod.SARAF \
                and invoice.banker and invoice.total_amount > 0:
            from apps.banker.services import BankerService
            BankerService.reverse_purchase_payment(
                banker=invoice.banker,
                amount=invoice.total_amount,
                currency=invoice.currency,
                purchase_invoice=invoice,
                user=user,
            )
        elif invoice.payment_method == PurchaseInvoice.PaymentMethod.DAKKAN:
            from apps.capital.models import ShopIncomeTransfer
            ShopIncomeTransfer.objects.filter(purchase_invoice=invoice).delete()

        # Step 4: Delete old invoice items
        invoice.items.all().delete()

        # Step 5: Recalculate new totals
        subtotal = Decimal('0')
        total_discount = Decimal('0')

        for item_data in items:
            qty      = item_data['quantity']
            cost     = item_data['unit_cost']
            disc     = item_data.get('discount_percent', Decimal('0'))
            gross    = qty * cost
            disc_amt = (gross * disc / 100).quantize(Decimal('0.01'))
            subtotal       += gross
            total_discount += disc_amt

        total_amount = subtotal - total_discount

        if payment_method == PurchaseInvoice.PaymentMethod.SARAF:
            effective_paid      = total_amount
            effective_remaining = Decimal('0')
            effective_status    = PurchaseInvoice.Status.PAID
        else:
            effective_paid      = paid_amount
            effective_remaining = total_amount - paid_amount
            effective_status    = PurchaseInvoice.Status.UNPAID

        # Step 6: Update invoice header
        invoice.supplier               = supplier
        invoice.warehouse              = warehouse
        invoice.purchase_date          = purchase_date
        invoice.supplier_invoice_number = supplier_invoice_number
        invoice.subtotal               = subtotal
        invoice.discount_amount        = total_discount
        invoice.total_amount           = total_amount
        invoice.paid_amount            = effective_paid
        invoice.remaining_amount       = effective_remaining
        invoice.currency               = currency
        invoice.payment_method         = payment_method
        invoice.banker                 = banker if payment_method == PurchaseInvoice.PaymentMethod.SARAF else None
        invoice.notes                  = notes
        invoice.status                 = effective_status
        invoice.save()

        # Step 7: Create new stock batches
        for item_data in items:
            product  = item_data['product']
            qty      = item_data['quantity']
            cost     = item_data['unit_cost']
            disc_pct = item_data.get('discount_percent', Decimal('0'))
            expiry   = item_data.get('expiry_date')

            gross    = qty * cost
            disc_amt = (gross * disc_pct / 100).quantize(Decimal('0.01'))
            net      = gross - disc_amt

            net_unit_cost = cost - (cost * disc_pct / 100)

            if currency == 'USD':
                # Pure USD purchase — store price in USD column only.
                # AFN column stays 0 (no exchange rate, no conversion).
                unit_cost_usd = net_unit_cost
                unit_cost_afn = Decimal('0')
                exchange_rate = Decimal('1')
            else:
                # Pure AFN purchase — store price in AFN column only.
                unit_cost_usd = Decimal('0')
                unit_cost_afn = net_unit_cost
                exchange_rate = Decimal('1')

            batch = FIFOService.receive_stock(
                product=product,
                warehouse=warehouse,
                quantity=qty,
                unit_cost=unit_cost_afn,
                unit_cost_usd=unit_cost_usd,
                exchange_rate=exchange_rate,
                expiry_date=expiry,
                purchase_reference=invoice.invoice_number,
                supplier_name=supplier.name,
                notes=f'فاکتور خرید {invoice.invoice_number} (ویرایش شده)',
                user=user,
            )

            PurchaseItem.objects.create(
                invoice=invoice,
                product=product,
                batch=batch,
                quantity=qty,
                unit_cost=cost,
                discount_percent=disc_pct,
                discount_amount=disc_amt,
                line_total=net,
                expiry_date=expiry,
            )

        # Step 8: Apply new supplier accounting
        SupplierAccountingService.apply_purchase(
            supplier=supplier,
            purchase_invoice=invoice,
            paid_amount=effective_paid,
            payment_method=payment_method,
            user=user,
        )

        # Step 9: Apply new banker/dakkan if applicable
        if payment_method == PurchaseInvoice.PaymentMethod.SARAF:
            from apps.banker.services import BankerService
            BankerService.apply_purchase_payment(
                banker=banker,
                amount=total_amount,
                currency=currency,
                purchase_invoice=invoice,
                transaction_date=purchase_date,
                user=user,
            )
        elif payment_method == PurchaseInvoice.PaymentMethod.DAKKAN and effective_paid > 0:
            from apps.capital.models import ShopIncomeTransfer
            ShopIncomeTransfer.objects.create(
                banker=None,
                purchase_invoice=invoice,
                amount=effective_paid,
                currency=currency,
                transfer_date=purchase_date,
                notes=f'پرداخت فاکتور خرید {invoice.invoice_number} — {supplier.name}',
                created_by=user,
            )

        try:
            from apps.activity_logs.services import ActivityLogService
            ActivityLogService.log(
                action='update',
                module='purchases',
                description=f'فاکتور خرید {invoice.invoice_number} ویرایش شد.',
                user=user,
                model_name='PurchaseInvoice',
                object_id=str(invoice.pk),
            )
        except Exception:
            pass

        return invoice