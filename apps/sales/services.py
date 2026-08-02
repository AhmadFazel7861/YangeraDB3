"""
Sales Service Layer — invoice creation, FIFO consumption, debt tracking.
Now supports backorders: a sale can exceed current stock; the shortfall
is recorded as a Backorder and auto-fulfilled later when stock arrives.
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.warehouse.services import FIFOService
from apps.warehouse.models import Warehouse, BatchMovement
from apps.inventory.models import Product
from .models import Invoice, InvoiceItem, Payment


def _apply_advance_to_old_invoices(customer, amount, currency, payment_method,
                                    payment_date, exclude_invoice, user):
    unpaid = Invoice.objects.filter(
        customer=customer,
        is_deleted=False,
        currency=currency,
        status__in=[Invoice.Status.CONFIRMED, Invoice.Status.PARTIAL],
        remaining_amount__gt=0,
    ).exclude(pk=exclude_invoice.pk).order_by('invoice_date', 'created_at')

    remaining = amount
    for inv in unpaid:
        if remaining <= 0:
            break
        to_apply = min(remaining, inv.remaining_amount)
        if to_apply <= 0:
            continue

        Payment.objects.create(
            invoice=inv,
            amount=to_apply,
            payment_method=payment_method,
            payment_date=payment_date,
            notes=f'کسر از پیش‌پرداخت — {customer.name}',
            received_by=user,
        )

        inv.paid_amount += to_apply
        inv.remaining_amount = inv.total_amount - inv.paid_amount
        if inv.remaining_amount <= 0:
            inv.status = Invoice.Status.PAID
            inv.remaining_amount = Decimal('0')
        else:
            inv.status = Invoice.Status.PARTIAL
        inv.save(update_fields=['paid_amount', 'remaining_amount', 'status', 'updated_at'])

        remaining -= to_apply


class SalesService:

    @staticmethod
    @transaction.atomic
    def create_invoice(
        customer,
        warehouse: Warehouse,
        items: list,
        invoice_date,
        paid_amount: Decimal = Decimal('0'),
        payment_method: str = 'cash',
        currency: str = 'AFN',
        banker=None,
        notes: str = '',
        user=None,
        create_pending: bool = True,
    ) -> Invoice:
        if not items:
            raise ValidationError('فاکتور باید حداقل یک ردیف داشته باشد.')

        if currency not in dict(Invoice.Currency.choices):
            raise ValidationError('واحد پول نامعتبر است.')

        if payment_method not in dict(Payment.PaymentMethod.choices):
            raise ValidationError('روش پرداخت نامعتبر است.')

        if payment_method == Payment.PaymentMethod.SARAF and not banker:
            raise ValidationError('برای پرداخت از طریق صراف، صراف را انتخاب کنید.')

        subtotal = Decimal('0')
        total_discount = Decimal('0')
        for item_data in items:
            qty      = item_data['quantity']
            price    = item_data['unit_price']
            disc_pct = item_data.get('discount_percent', Decimal('0'))
            gross    = qty * price
            disc_amt = (gross * disc_pct / 100).quantize(Decimal('0.01'))
            subtotal       += gross
            total_discount += disc_amt

        total_amount  = subtotal - total_discount

        # ── FIX: previous_debt must reflect the customer's debt in the SAME
        # currency as this invoice. Previously this always called
        # get_customer_debt() (AFN-only), so USD invoices showed 0 even when
        # the customer had a real USD debt. ──
        if currency == Invoice.Currency.USD:
            previous_debt = SalesService.get_customer_debt_usd(customer)
        else:
            previous_debt = SalesService.get_customer_debt(customer)

        SalesService.check_credit_limit(
            customer=customer,
            currency=currency,
            sale_total=total_amount,
            paid_amount=paid_amount,
        )

        invoice_paid = min(paid_amount, total_amount)
        advance_overpayment = paid_amount - invoice_paid

        invoice = Invoice.objects.create(
            customer=customer,
            warehouse=warehouse,
            invoice_date=invoice_date,
            subtotal=subtotal,
            discount_amount=total_discount,
            total_amount=total_amount,
            paid_amount=invoice_paid,
            remaining_amount=total_amount - invoice_paid,
            previous_debt=previous_debt,
            currency=currency,
            banker=banker if payment_method == Payment.PaymentMethod.SARAF else None,
            notes=notes,
            created_by=user,
            status=Invoice.Status.CONFIRMED,
        )

        total_cost = Decimal('0')
        for item_data in items:
            product  = item_data['product']
            qty      = item_data['quantity']
            price    = item_data['unit_price']
            disc_pct = item_data.get('discount_percent', Decimal('0'))

            gross    = qty * price
            disc_amt = (gross * disc_pct / 100).quantize(Decimal('0.01'))
            line_net = gross - disc_amt

            fifo_result = FIFOService.consume_stock(
                product=product,
                warehouse=warehouse,
                quantity=qty,
                movement_type=BatchMovement.MovementType.SALE,
                reference=invoice.invoice_number,
                user=user,
                allow_backorder=True,
            )

            total_cost += fifo_result['total_cost']

            item = InvoiceItem.objects.create(
                invoice=invoice,
                product=product,
                quantity=qty,
                unit_price=price,
                discount_percent=disc_pct,
                discount_amount=disc_amt,
                line_total=line_net,
                unit_cost_fifo=fifo_result['average_cost'],
                total_cost_fifo=fifo_result['total_cost'],
            )

            if fifo_result['shortfall'] > 0:
                try:
                    from apps.warehouse.models import Backorder
                    Backorder.objects.create(
                        invoice=invoice,
                        invoice_item=item,
                        customer=customer,
                        warehouse=warehouse,
                        product=product,
                        quantity=fifo_result['shortfall'],
                        created_reference=invoice.invoice_number,
                    )
                except Exception:
                    pass

        invoice.total_cost = total_cost
        invoice.save(update_fields=['total_cost', 'updated_at'])

        if create_pending:
            try:
                from apps.warehouse.models import PendingDelivery
                for item in invoice.items.select_related('product'):
                    PendingDelivery.objects.create(
                        invoice=invoice,
                        invoice_item=item,
                        customer=customer,
                        warehouse=warehouse,
                        product=item.product,
                        quantity=item.quantity,
                        quantity_delivered=Decimal('0'),
                        status=PendingDelivery.Status.PENDING,
                        invoice_date=invoice.invoice_date,
                    )
            except Exception:
                pass

        from apps.customers.services.accounting import CustomerAccountingService

        if advance_overpayment > 0:
            CustomerAccountingService.apply_payment(
                customer=customer,
                amount=advance_overpayment,
                payment_method=payment_method,
                currency=currency,
                exchange_rate=Decimal('1'),
                payment_date=invoice_date,
                notes=f'پیش‌پرداخت اضافه — فاکتور {invoice.invoice_number}',
                invoice=None,
                user=user,
            )

            _apply_advance_to_old_invoices(
                customer=customer,
                amount=advance_overpayment,
                currency=currency,
                payment_method=payment_method,
                payment_date=invoice_date,
                exclude_invoice=invoice,
                user=user,
            )

        CustomerAccountingService.apply_invoice(
            customer=customer,
            invoice=invoice,
            paid_amount=invoice_paid,
            payment_method=payment_method,
            user=user,
        )

        if payment_method == Payment.PaymentMethod.SARAF and paid_amount > 0:
            from apps.banker.services import BankerService
            BankerService.apply_sale_payment(
                banker=banker,
                amount=paid_amount,
                currency=currency,
                sale_invoice=invoice,
                transaction_date=invoice_date,
                user=user,
            )

        try:
            from apps.activity_logs.services import ActivityLogService
            ActivityLogService.log_invoice_created(invoice, user=user)
        except Exception:
            pass

        return invoice

    @staticmethod
    @transaction.atomic
    def add_payment(
        invoice,
        amount: Decimal,
        payment_method: str,
        payment_date,
        currency: str = None,
        exchange_rate: Decimal = Decimal('1'),
        notes: str = '',
        user=None
    ):
        from apps.customers.services.accounting import CustomerAccountingService

        if currency is None:
            currency = getattr(invoice, 'currency', 'AFN')

        if amount <= 0:
            raise ValidationError('مبلغ پرداخت باید بیشتر از صفر باشد.')

        max_payable = invoice.remaining_amount
        if amount > max_payable:
            raise ValidationError(
                f'مبلغ ({amount:,.2f}) بیشتر از مانده فاکتور '
                f'({max_payable:,.2f}) است.'
            )

        payment = Payment.objects.create(
            invoice=invoice,
            amount=amount,
            payment_method=payment_method,
            payment_date=payment_date,
            notes=notes,
            received_by=user,
        )

        invoice.paid_amount      += amount
        invoice.remaining_amount  = invoice.total_amount - invoice.paid_amount
        if invoice.remaining_amount <= 0:
            invoice.status = Invoice.Status.PAID
            invoice.remaining_amount = Decimal('0')
        else:
            invoice.status = Invoice.Status.PARTIAL
        invoice.save(update_fields=[
            'paid_amount', 'remaining_amount', 'status', 'updated_at'
        ])

        CustomerAccountingService.apply_payment(
            customer=invoice.customer,
            amount=amount,
            payment_method=payment_method,
            currency=currency,
            exchange_rate=exchange_rate,
            payment_date=payment_date,
            notes=f'پرداخت فاکتور {invoice.invoice_number}',
            invoice=invoice,
            user=user,
        )

        if payment_method == Payment.PaymentMethod.SARAF and invoice.banker:
            from apps.banker.services import BankerService
            BankerService.apply_sale_payment(
                banker=invoice.banker,
                amount=amount,
                currency=currency,
                sale_invoice=invoice,
                transaction_date=payment_date,
                user=user,
            )

        return payment

    @staticmethod
    def get_customer_debt(customer) -> Decimal:
        # customer.total_debt is the single source of truth for the
        # customer's current AFN debt. It is initialized once from
        # opening_balance (see CustomerAccountingService.initialize_opening_balance)
        # and kept live-updated by CustomerAccountingService on every
        # invoice, payment, advance-use, reversal, and recalculation.
        #
        # Previously this method re-derived debt as:
        #     sum(open invoices' remaining_amount) + customer.opening_balance
        # which double-counted the opening debt whenever it was reduced by a
        # direct payment (i.e. a payment not tied to any invoice, e.g. from
        # the customer page) — opening_balance never changes after the
        # customer is created, so it kept being re-added in full even after
        # being paid down. Reading the live field instead fixes that.
        return customer.total_debt

    @staticmethod
    def get_customer_debt_usd(customer) -> Decimal:
        # See get_customer_debt() above — same fix, USD bucket.
        return customer.total_debt_usd

    @staticmethod
    def check_credit_limit(customer, currency, sale_total, paid_amount):
        if currency == Invoice.Currency.USD:
            current_debt = SalesService.get_customer_debt_usd(customer)
            limit = customer.credit_limit_usd
            symbol = '$'
        else:
            current_debt = SalesService.get_customer_debt(customer)
            limit = customer.credit_limit
            symbol = '؋'

        if limit <= 0:
            return

        projected_debt = current_debt + sale_total - paid_amount
        if projected_debt > limit:
            raise ValidationError(
                f'این فروش از حد اعتبار مشتری «{customer.name}» بیشتر است. '
                f'حد اعتبار: {limit:,.2f} {symbol} | '
                f'بدهی فعلی: {current_debt:,.2f} {symbol} | '
                f'بدهی پس از این فروش: {projected_debt:,.2f} {symbol}'
            )

    @staticmethod
    @transaction.atomic
    def cancel_invoice(invoice: Invoice, user=None):
        if invoice.status == Invoice.Status.CANCELLED:
            raise ValidationError('این فاکتور قبلاً لغو شده است.')

        from apps.warehouse.models import StockBatch, BatchMovement as BM

        for item in invoice.items.all():
            product        = item.product
            qty_to_restore = item.quantity

            movements = BM.objects.filter(
                batch__product=product,
                batch__warehouse=invoice.warehouse,
                movement_type=BM.MovementType.SALE,
                reference=invoice.invoice_number,
            ).select_related('batch')

            restored = Decimal('0')
            for movement in movements:
                batch = movement.batch
                restore_qty = min(movement.quantity, qty_to_restore - restored)
                if restore_qty <= 0:
                    continue
                batch.remaining_quantity += restore_qty
                if batch.remaining_quantity > batch.initial_quantity:
                    batch.remaining_quantity = batch.initial_quantity
                batch.is_deleted = False
                batch.save(update_fields=['remaining_quantity', 'is_deleted'])
                restored += restore_qty

            product.current_stock += item.quantity
            product.save(update_fields=['current_stock', 'updated_at'])

        try:
            from apps.warehouse.models import Backorder
            Backorder.objects.filter(
                invoice=invoice,
                status=Backorder.Status.OPEN,
            ).update(status=Backorder.Status.CANCELLED)
        except Exception:
            pass

        try:
            from apps.customers.services.accounting import CustomerAccountingService
            CustomerAccountingService.reverse_invoice(
                customer=invoice.customer,
                invoice=invoice,
                user=user,
            )
            # reverse_invoice() reverses a PAYMENT by crediting it to
            # advance_balance (correct for edit_invoice, where a new invoice
            # follows immediately and can reuse that advance). On a plain
            # cancellation there's no follow-up invoice, so that credit was
            # showing up as a phantom advance instead of just disappearing.
            # Recalculating from the non-reversed transaction ledger gives
            # the true debt/advance state — same fix edit_invoice already uses.
            CustomerAccountingService.recalculate_customer_balance(invoice.customer)
        except Exception:
            customer = invoice.customer
            customer.total_debt -= invoice.remaining_amount
            if customer.total_debt < 0:
                customer.total_debt = Decimal('0')
            customer.save(update_fields=['total_debt', 'updated_at'])

        if invoice.banker and invoice.paid_amount > 0:
            try:
                from apps.banker.services import BankerService
                BankerService.reverse_sale_payment(
                    banker=invoice.banker,
                    amount=invoice.paid_amount,
                    currency=invoice.currency,
                    sale_invoice=invoice,
                    user=user,
                )
            except Exception:
                pass

        try:
            from apps.warehouse.models import PendingDelivery
            PendingDelivery.objects.filter(
                invoice=invoice,
                status=PendingDelivery.Status.PENDING,
            ).update(status=PendingDelivery.Status.CANCELLED)
        except Exception:
            pass

        try:
            from apps.warehouse.models import PendingDelivery
            PendingDelivery.objects.filter(
                invoice=invoice,
                status=PendingDelivery.Status.PENDING,
            ).update(
                status=PendingDelivery.Status.CANCELLED,
                notes='فاکتور لغو شد',
            )
        except Exception:
            pass

        invoice.status     = Invoice.Status.CANCELLED
        invoice.is_deleted = True
        invoice.deleted_at = timezone.now()
        invoice.save(update_fields=['status', 'is_deleted', 'deleted_at', 'updated_at'])

        try:
            from apps.activity_logs.services import ActivityLogService
            ActivityLogService.log_invoice_cancelled(invoice, user=user)
        except Exception:
            pass

    @staticmethod
    @transaction.atomic
    def edit_invoice(invoice: Invoice, customer, warehouse, items, invoice_date,
                     paid_amount, payment_method, currency='AFN', banker=None,
                     notes='', user=None):
        from apps.warehouse.models import BatchMovement as BM
        from apps.customers.services.accounting import CustomerAccountingService
        from apps.customers.models import CustomerTransaction, Customer as CustomerModel

        if not items:
            raise ValidationError('فاکتور باید حداقل یک ردیف داشته باشد.')

        if currency not in dict(Invoice.Currency.choices):
            raise ValidationError('واحد پول نامعتبر است.')

        if payment_method not in dict(Payment.PaymentMethod.choices):
            raise ValidationError('روش پرداخت نامعتبر است.')

        if payment_method == Payment.PaymentMethod.SARAF and not banker:
            raise ValidationError('برای پرداخت از طریق صراف، صراف را انتخاب کنید.')

        # Step 1: Restore stock from old items
        for item in invoice.items.all():
            product        = item.product
            qty_to_restore = item.quantity

            movements = BM.objects.filter(
                batch__product=product,
                batch__warehouse=invoice.warehouse,
                movement_type=BM.MovementType.SALE,
                reference=invoice.invoice_number,
            ).select_related('batch')

            restored = Decimal('0')
            for movement in movements:
                batch = movement.batch
                restore_qty = min(movement.quantity, qty_to_restore - restored)
                if restore_qty <= 0:
                    continue
                batch.remaining_quantity += restore_qty
                if batch.remaining_quantity > batch.initial_quantity:
                    batch.remaining_quantity = batch.initial_quantity
                batch.is_deleted = False
                batch.save(update_fields=['remaining_quantity', 'is_deleted'])
                restored += restore_qty

            product.current_stock += item.quantity
            product.save(update_fields=['current_stock', 'updated_at'])

        # Cancel old open backorders
        try:
            from apps.warehouse.models import Backorder
            Backorder.objects.filter(
                invoice=invoice,
                status=Backorder.Status.OPEN,
            ).update(status=Backorder.Status.CANCELLED)
        except Exception:
            pass

        # ── Delete old sales.Payment rows ──
        invoice.payments.all().delete()

        # ── Reverse orphaned advance_add transactions (invoice=None) that were
        # created as overpayment advances alongside this invoice.
        # reverse_invoice() only handles invoice-linked transactions, so these
        # must be reversed separately before calling it.
        linked_invoice_tx = CustomerTransaction.objects.filter(
            invoice=invoice,
            tx_type=CustomerTransaction.TxType.INVOICE,
            is_reversed=False,
        ).order_by('created_at').first()

        if linked_invoice_tx:
            orphan_advance_adds = CustomerTransaction.objects.filter(
                customer=invoice.customer,
                tx_type=CustomerTransaction.TxType.ADVANCE_ADD,
                invoice=None,
                is_reversed=False,
                created_at__gte=linked_invoice_tx.created_at,
            )
            cust_locked = CustomerModel.objects.select_for_update().get(
                pk=invoice.customer.pk
            )
            for adv_tx in orphan_advance_adds:
                amt = adv_tx.amount
                cur = adv_tx.currency
                if cur == 'USD':
                    cust_locked.advance_balance_usd = max(
                        Decimal('0'),
                        cust_locked.advance_balance_usd - amt
                    )
                else:
                    cust_locked.advance_balance = max(
                        Decimal('0'),
                        cust_locked.advance_balance - amt
                    )
                reversal = CustomerTransaction.objects.create(
                    customer=cust_locked,
                    tx_type=CustomerTransaction.TxType.REVERSAL,
                    currency=cur,
                    exchange_rate=adv_tx.exchange_rate,
                    amount=amt,
                    amount_afn=adv_tx.amount_afn,
                    debt_before=cust_locked.total_debt,
                    debt_after=cust_locked.total_debt,
                    advance_before=cust_locked.advance_balance,
                    advance_after=cust_locked.advance_balance,
                    debt_before_usd=cust_locked.total_debt_usd,
                    debt_after_usd=cust_locked.total_debt_usd,
                    advance_before_usd=cust_locked.advance_balance_usd,
                    advance_after_usd=cust_locked.advance_balance_usd,
                    invoice=None,
                    transaction_date=timezone.now().date(),
                    notes=f'برگشت پیش‌پرداخت اضافه — ویرایش فاکتور {invoice.invoice_number}',
                    created_by=user,
                )
                adv_tx.is_reversed = True
                adv_tx.reversed_by = reversal
                adv_tx.save(update_fields=['is_reversed', 'reversed_by'])
            cust_locked.save(update_fields=[
                'advance_balance', 'advance_balance_usd', 'updated_at'
            ])

        # ── Reverse old customer accounting (invoice-linked transactions).
        # After reverse_invoice(), PAYMENT reversals put cash into advance_balance
        # and ADVANCE_USE reversals restore both advance AND debt — leaving the
        # customer object in an intermediate state that does NOT match the true
        # ledger (all those reversals are marked is_reversed=True so they are
        # excluded from recalculation).
        # The safest way to get a clean slate before apply_invoice() is to:
        #   1. Call reverse_invoice() to mark all old txs as reversed.
        #   2. Immediately recalculate the customer balance by replaying only
        #      the non-reversed transactions — this gives the exact correct
        #      advance/debt values with no artifacts.
        try:
            CustomerAccountingService.reverse_invoice(
                customer=invoice.customer,
                invoice=invoice,
                user=user,
            )
        except Exception:
            cust = invoice.customer
            cust.total_debt -= invoice.remaining_amount
            if cust.total_debt < 0:
                cust.total_debt = Decimal('0')
            cust.save(update_fields=['total_debt', 'updated_at'])

        # Recalculate from the full transaction ledger so the customer balance
        # reflects only real, non-reversed history — no double-counting possible.
        CustomerAccountingService.recalculate_customer_balance(invoice.customer)

        # Reverse old banker if applicable
        if invoice.banker and invoice.paid_amount > 0:
            try:
                from apps.banker.services import BankerService
                BankerService.reverse_sale_payment(
                    banker=invoice.banker,
                    amount=invoice.paid_amount,
                    currency=invoice.currency,
                    sale_invoice=invoice,
                    user=user,
                )
            except Exception:
                pass

        # Step 2: Delete old items
        invoice.items.all().delete()

        # Step 3: Recalculate totals
        subtotal = Decimal('0')
        total_discount = Decimal('0')
        for item_data in items:
            qty      = item_data['quantity']
            price    = item_data['unit_price']
            disc_pct = item_data.get('discount_percent', Decimal('0'))
            gross    = qty * price
            disc_amt = (gross * disc_pct / 100).quantize(Decimal('0.01'))
            subtotal       += gross
            total_discount += disc_amt

        total_amount = subtotal - total_discount

        # ── FIX: same currency-aware previous_debt calculation as create_invoice.
        # edit_invoice previously never set previous_debt at all (always left at
        # whatever it was before, or 0 on creation), so this fills it in correctly
        # based on the (possibly new) invoice currency. ──
        if currency == Invoice.Currency.USD:
            previous_debt = SalesService.get_customer_debt_usd(customer)
        else:
            previous_debt = SalesService.get_customer_debt(customer)

        SalesService.check_credit_limit(
            customer=customer,
            currency=currency,
            sale_total=total_amount,
            paid_amount=paid_amount,
        )

        invoice_paid        = min(paid_amount, total_amount)
        advance_overpayment = paid_amount - invoice_paid

        # Step 4: Update invoice header — reset paid to 0, apply_invoice sets it
        invoice.customer         = customer
        invoice.warehouse        = warehouse
        invoice.invoice_date     = invoice_date
        invoice.subtotal         = subtotal
        invoice.discount_amount  = total_discount
        invoice.total_amount     = total_amount
        invoice.paid_amount      = Decimal('0')
        invoice.remaining_amount = total_amount
        invoice.previous_debt    = previous_debt
        invoice.currency         = currency
        invoice.banker           = banker if payment_method == Payment.PaymentMethod.SARAF else None
        invoice.notes            = notes
        invoice.status           = Invoice.Status.CONFIRMED
        invoice.is_deleted       = False
        invoice.deleted_at       = None
        invoice.save()

        # Step 5: Consume stock with new items
        total_cost = Decimal('0')
        for item_data in items:
            product  = item_data['product']
            qty      = item_data['quantity']
            price    = item_data['unit_price']
            disc_pct = item_data.get('discount_percent', Decimal('0'))

            gross    = qty * price
            disc_amt = (gross * disc_pct / 100).quantize(Decimal('0.01'))
            line_net = gross - disc_amt

            fifo_result = FIFOService.consume_stock(
                product=product,
                warehouse=warehouse,
                quantity=qty,
                movement_type=BatchMovement.MovementType.SALE,
                reference=invoice.invoice_number,
                user=user,
                allow_backorder=True,
            )

            total_cost += fifo_result['total_cost']

            item = InvoiceItem.objects.create(
                invoice=invoice,
                product=product,
                quantity=qty,
                unit_price=price,
                discount_percent=disc_pct,
                discount_amount=disc_amt,
                line_total=line_net,
                unit_cost_fifo=fifo_result['average_cost'],
                total_cost_fifo=fifo_result['total_cost'],
            )

            if fifo_result['shortfall'] > 0:
                try:
                    from apps.warehouse.models import Backorder
                    Backorder.objects.create(
                        invoice=invoice,
                        invoice_item=item,
                        customer=customer,
                        warehouse=warehouse,
                        product=product,
                        quantity=fifo_result['shortfall'],
                        created_reference=invoice.invoice_number,
                    )
                except Exception:
                    pass

        invoice.total_cost = total_cost
        invoice.save(update_fields=['total_cost', 'updated_at'])

        # Step 6: Credit advance overpayment FIRST, then apply invoice
        if advance_overpayment > 0:
            CustomerAccountingService.apply_payment(
                customer=customer,
                amount=advance_overpayment,
                payment_method=payment_method,
                currency=currency,
                exchange_rate=Decimal('1'),
                payment_date=invoice_date,
                notes=f'پیش‌پرداخت اضافه — فاکتور {invoice.invoice_number}',
                invoice=None,
                user=user,
            )
            _apply_advance_to_old_invoices(
                customer=customer,
                amount=advance_overpayment,
                currency=currency,
                payment_method=payment_method,
                payment_date=invoice_date,
                exclude_invoice=invoice,
                user=user,
            )

        CustomerAccountingService.apply_invoice(
            customer=customer,
            invoice=invoice,
            paid_amount=invoice_paid,
            payment_method=payment_method,
            user=user,
        )

        # Step 7: Apply new banker if applicable
        if payment_method == Payment.PaymentMethod.SARAF and paid_amount > 0:
            from apps.banker.services import BankerService
            BankerService.apply_sale_payment(
                banker=banker,
                amount=paid_amount,
                currency=currency,
                sale_invoice=invoice,
                transaction_date=invoice_date,
                user=user,
            )