"""
SupplierAccountingService — dual-currency engine.
AFN and USD balances tracked separately.
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.suppliers.models import Supplier, SupplierTransaction, SupplierPayment


class SupplierAccountingService:

    @staticmethod
    @transaction.atomic
    def apply_purchase(
        supplier: Supplier,
        purchase_invoice,
        paid_amount: Decimal = Decimal('0'),
        payment_method: str = 'cash',
        user=None
    ) -> dict:
        supplier = Supplier.objects.select_for_update().get(pk=supplier.pk)
        invoice_amount = purchase_invoice.total_amount
        inv_currency   = getattr(purchase_invoice, 'currency', 'AFN')

        debt_before        = supplier.total_debt
        advance_before     = supplier.advance_balance
        debt_before_usd    = supplier.total_debt_usd
        advance_before_usd = supplier.advance_balance_usd

        if inv_currency == 'USD':
            supplier.total_debt_usd += invoice_amount
            amount_afn = invoice_amount
        else:
            supplier.total_debt += invoice_amount
            amount_afn = invoice_amount

        SupplierTransaction.objects.create(
            supplier=supplier,
            tx_type=SupplierTransaction.TxType.PURCHASE,
            currency=inv_currency,
            amount=invoice_amount,
            amount_afn=amount_afn,
            debt_before=debt_before,
            debt_after=supplier.total_debt,
            advance_before=advance_before,
            advance_after=advance_before,
            debt_before_usd=debt_before_usd,
            debt_after_usd=supplier.total_debt_usd,
            advance_before_usd=advance_before_usd,
            advance_after_usd=advance_before_usd,
            purchase_invoice=purchase_invoice,
            transaction_date=purchase_invoice.purchase_date,
            notes=f'فاکتور خرید {purchase_invoice.invoice_number}',
            created_by=user,
        )

        advance_used = Decimal('0')
        if inv_currency == 'USD' and supplier.advance_balance_usd > 0:
            advance_used = min(supplier.advance_balance_usd, supplier.total_debt_usd)
            if advance_used > 0:
                adv_b = supplier.advance_balance_usd
                supplier.advance_balance_usd -= advance_used
                supplier.total_debt_usd      -= advance_used
                SupplierTransaction.objects.create(
                    supplier=supplier,
                    tx_type=SupplierTransaction.TxType.ADVANCE_USE,
                    currency='USD',
                    amount=advance_used,
                    amount_afn=advance_used,
                    debt_before=supplier.total_debt,
                    debt_after=supplier.total_debt,
                    advance_before=supplier.advance_balance,
                    advance_after=supplier.advance_balance,
                    debt_before_usd=supplier.total_debt_usd + advance_used,
                    debt_after_usd=supplier.total_debt_usd,
                    advance_before_usd=adv_b,
                    advance_after_usd=supplier.advance_balance_usd,
                    purchase_invoice=purchase_invoice,
                    transaction_date=purchase_invoice.purchase_date,
                    notes=f'کسر پیش‌پرداخت دالر فاکتور {purchase_invoice.invoice_number}',
                    created_by=user,
                )
        elif inv_currency == 'AFN' and supplier.advance_balance > 0:
            advance_used = min(supplier.advance_balance, supplier.total_debt)
            if advance_used > 0:
                adv_b = supplier.advance_balance
                supplier.advance_balance -= advance_used
                supplier.total_debt      -= advance_used
                SupplierTransaction.objects.create(
                    supplier=supplier,
                    tx_type=SupplierTransaction.TxType.ADVANCE_USE,
                    currency='AFN',
                    amount=advance_used,
                    amount_afn=advance_used,
                    debt_before=supplier.total_debt + advance_used,
                    debt_after=supplier.total_debt,
                    advance_before=adv_b,
                    advance_after=supplier.advance_balance,
                    debt_before_usd=supplier.total_debt_usd,
                    debt_after_usd=supplier.total_debt_usd,
                    advance_before_usd=supplier.advance_balance_usd,
                    advance_after_usd=supplier.advance_balance_usd,
                    purchase_invoice=purchase_invoice,
                    transaction_date=purchase_invoice.purchase_date,
                    notes=f'کسر پیش‌پرداخت افغانی فاکتور {purchase_invoice.invoice_number}',
                    created_by=user,
                )

        cash_applied = Decimal('0')
        new_advance  = Decimal('0')
        if paid_amount > 0:
            result = SupplierAccountingService._apply_payment_to_balance(
                supplier=supplier,
                amount=paid_amount,
                currency=inv_currency,
                payment_method=payment_method,
                invoice=purchase_invoice,
                date=purchase_invoice.purchase_date,
                notes=f'پرداخت فاکتور {purchase_invoice.invoice_number}',
                user=user,
            )
            cash_applied = result['applied_to_debt']
            new_advance  = result['new_advance']

        actual_paid = advance_used + cash_applied
        purchase_invoice.paid_amount      = actual_paid
        purchase_invoice.remaining_amount = max(Decimal('0'), invoice_amount - actual_paid)
        from apps.purchases.models import PurchaseInvoice
        if purchase_invoice.remaining_amount <= 0:
            purchase_invoice.status = PurchaseInvoice.Status.PAID
        elif actual_paid > 0:
            purchase_invoice.status = PurchaseInvoice.Status.PARTIAL
        else:
            purchase_invoice.status = PurchaseInvoice.Status.UNPAID
        purchase_invoice.save(update_fields=['paid_amount', 'remaining_amount', 'status', 'updated_at'])

        supplier.last_transaction_date = purchase_invoice.purchase_date
        supplier.save(update_fields=[
            'total_debt', 'advance_balance',
            'total_debt_usd', 'advance_balance_usd',
            'last_transaction_date', 'updated_at'
        ])

        return {
            'advance_used': advance_used,
            'cash_applied': cash_applied,
            'new_advance': new_advance,
            'remaining_debt': supplier.total_debt,
            'remaining_debt_usd': supplier.total_debt_usd,
        }

    @staticmethod
    @transaction.atomic
    def reverse_purchase(
        supplier: Supplier,
        purchase_invoice,
        user=None,
    ) -> None:
        supplier = Supplier.objects.select_for_update().get(pk=supplier.pk)

        txs = SupplierTransaction.objects.filter(
            purchase_invoice=purchase_invoice,
            is_reversed=False,
        ).exclude(
            tx_type=SupplierTransaction.TxType.REVERSAL,
        ).order_by('-created_at')

        for tx in txs:
            amount = tx.amount
            t      = tx.tx_type
            cur    = tx.currency

            debt_before        = supplier.total_debt
            advance_before     = supplier.advance_balance
            debt_before_usd    = supplier.total_debt_usd
            advance_before_usd = supplier.advance_balance_usd

            if cur == 'USD':
                if t == SupplierTransaction.TxType.PURCHASE:
                    supplier.total_debt_usd = max(Decimal('0'), supplier.total_debt_usd - amount)
                elif t == SupplierTransaction.TxType.ADVANCE_USE:
                    supplier.advance_balance_usd += amount
                    supplier.total_debt_usd      += amount
                elif t == SupplierTransaction.TxType.PAYMENT:
                    supplier.advance_balance_usd += amount
                elif t == SupplierTransaction.TxType.ADVANCE_ADD:
                    supplier.advance_balance_usd = max(Decimal('0'), supplier.advance_balance_usd - amount)
                else:
                    continue
            else:
                if t == SupplierTransaction.TxType.PURCHASE:
                    supplier.total_debt = max(Decimal('0'), supplier.total_debt - amount)
                elif t == SupplierTransaction.TxType.ADVANCE_USE:
                    supplier.advance_balance += amount
                    supplier.total_debt      += amount
                elif t == SupplierTransaction.TxType.PAYMENT:
                    supplier.advance_balance += amount
                elif t == SupplierTransaction.TxType.ADVANCE_ADD:
                    supplier.advance_balance = max(Decimal('0'), supplier.advance_balance - amount)
                else:
                    continue

            reversal = SupplierTransaction.objects.create(
                supplier=supplier,
                tx_type=SupplierTransaction.TxType.REVERSAL,
                currency=cur,
                amount=amount,
                amount_afn=tx.amount_afn,
                debt_before=debt_before,
                debt_after=supplier.total_debt,
                advance_before=advance_before,
                advance_after=supplier.advance_balance,
                debt_before_usd=debt_before_usd,
                debt_after_usd=supplier.total_debt_usd,
                advance_before_usd=advance_before_usd,
                advance_after_usd=supplier.advance_balance_usd,
                purchase_invoice=purchase_invoice,
                transaction_date=timezone.now().date(),
                notes=f'برگشت فاکتور خرید {purchase_invoice.invoice_number} — {tx.get_tx_type_display()}',
                created_by=user,
            )

            tx.is_reversed = True
            tx.reversed_by = reversal
            tx.save(update_fields=['is_reversed', 'reversed_by'])

        supplier.last_transaction_date = timezone.now().date()
        supplier.save(update_fields=[
            'total_debt', 'advance_balance',
            'total_debt_usd', 'advance_balance_usd',
            'last_transaction_date', 'updated_at',
        ])

    @staticmethod
    @transaction.atomic
    def apply_payment(
        supplier: Supplier,
        amount: Decimal,
        payment_method: str = 'cash',
        currency: str = 'AFN',
        payment_date=None,
        notes: str = '',
        invoice=None,
        user=None
    ) -> SupplierPayment:
        if amount <= 0:
            raise ValidationError('مبلغ پرداخت باید بیشتر از صفر باشد.')
        if payment_date is None:
            payment_date = timezone.now().date()

        supplier = Supplier.objects.select_for_update().get(pk=supplier.pk)

        result = SupplierAccountingService._apply_payment_to_balance(
            supplier=supplier,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            invoice=invoice,
            date=payment_date,
            notes=notes or f'پرداخت به تامین‌کننده — {payment_date}',
            user=user,
        )

        supplier.last_transaction_date = payment_date
        supplier.save(update_fields=[
            'total_debt', 'advance_balance',
            'total_debt_usd', 'advance_balance_usd',
            'last_transaction_date', 'updated_at'
        ])

        tx = SupplierTransaction.objects.filter(
            supplier=supplier,
            tx_type__in=[
                SupplierTransaction.TxType.PAYMENT,
                SupplierTransaction.TxType.ADVANCE_ADD,
            ],
            transaction_date=payment_date,
        ).order_by('-created_at').first()

        payment = SupplierPayment.objects.create(
            supplier=supplier,
            transaction=tx,
            amount=amount,
            payment_method=payment_method,
            currency=currency,
            payment_date=payment_date,
            notes=notes,
            paid_by=user,
        )
        return payment

    @staticmethod
    @transaction.atomic
    def reverse_transaction(
        transaction_obj: SupplierTransaction,
        notes: str = '',
        user=None
    ) -> SupplierTransaction:
        if transaction_obj.is_reversed:
            raise ValidationError('این تراکنش قبلاً برگشت داده شده است.')

        supplier = Supplier.objects.select_for_update().get(pk=transaction_obj.supplier.pk)
        amount = transaction_obj.amount
        t      = transaction_obj.tx_type
        cur    = transaction_obj.currency

        debt_before        = supplier.total_debt
        advance_before     = supplier.advance_balance
        debt_before_usd    = supplier.total_debt_usd
        advance_before_usd = supplier.advance_balance_usd

        if cur == 'USD':
            if t == SupplierTransaction.TxType.PURCHASE:
                supplier.total_debt_usd = max(Decimal('0'), supplier.total_debt_usd - amount)
            elif t == SupplierTransaction.TxType.PAYMENT:
                supplier.total_debt_usd += amount
            elif t == SupplierTransaction.TxType.ADVANCE_ADD:
                supplier.advance_balance_usd = max(Decimal('0'), supplier.advance_balance_usd - amount)
            elif t == SupplierTransaction.TxType.ADVANCE_USE:
                supplier.advance_balance_usd += amount
                supplier.total_debt_usd      += amount
        else:
            if t == SupplierTransaction.TxType.PURCHASE:
                supplier.total_debt = max(Decimal('0'), supplier.total_debt - amount)
            elif t == SupplierTransaction.TxType.PAYMENT:
                supplier.total_debt += amount
            elif t == SupplierTransaction.TxType.ADVANCE_ADD:
                supplier.advance_balance = max(Decimal('0'), supplier.advance_balance - amount)
            elif t == SupplierTransaction.TxType.ADVANCE_USE:
                supplier.advance_balance += amount
                supplier.total_debt      += amount

        reversal = SupplierTransaction.objects.create(
            supplier=supplier,
            tx_type=SupplierTransaction.TxType.REVERSAL,
            currency=cur,
            amount=amount,
            amount_afn=transaction_obj.amount_afn,
            debt_before=debt_before,
            debt_after=supplier.total_debt,
            advance_before=advance_before,
            advance_after=supplier.advance_balance,
            debt_before_usd=debt_before_usd,
            debt_after_usd=supplier.total_debt_usd,
            advance_before_usd=advance_before_usd,
            advance_after_usd=supplier.advance_balance_usd,
            transaction_date=timezone.now().date(),
            notes=notes or f'برگشت: {transaction_obj.get_tx_type_display()}',
            created_by=user,
        )

        transaction_obj.is_reversed = True
        transaction_obj.reversed_by = reversal
        transaction_obj.save(update_fields=['is_reversed', 'reversed_by'])

        supplier.last_transaction_date = timezone.now().date()
        supplier.save(update_fields=[
            'total_debt', 'advance_balance',
            'total_debt_usd', 'advance_balance_usd',
            'last_transaction_date', 'updated_at'
        ])
        return reversal

    @staticmethod
    @transaction.atomic
    def initialize_opening_balance(supplier: Supplier, user=None):
        """Called on CREATE only. Handles both AFN and USD opening balances."""

        today = supplier.created_at.date()

        # ── AFN ──────────────────────────────────────────────────────────────
        if supplier.opening_balance > 0:
            SupplierTransaction.objects.create(
                supplier=supplier,
                tx_type=SupplierTransaction.TxType.OPENING_DEBT,
                currency='AFN',
                amount=supplier.opening_balance,
                amount_afn=supplier.opening_balance,
                debt_before=Decimal('0'),
                debt_after=supplier.opening_balance,
                advance_before=Decimal('0'),
                advance_after=Decimal('0'),
                debt_before_usd=Decimal('0'),
                debt_after_usd=Decimal('0'),
                advance_before_usd=Decimal('0'),
                advance_after_usd=Decimal('0'),
                transaction_date=today,
                notes='بدهی اولیه هنگام ثبت تامین‌کننده (افغانی)',
                created_by=user,
            )
            supplier.total_debt = supplier.opening_balance
            supplier.save(update_fields=['total_debt', 'updated_at'])

        # ── USD ──────────────────────────────────────────────────────────────
        if supplier.opening_balance_usd > 0:
            SupplierTransaction.objects.create(
                supplier=supplier,
                tx_type=SupplierTransaction.TxType.OPENING_DEBT,
                currency='USD',
                amount=supplier.opening_balance_usd,
                amount_afn=Decimal('0'),
                debt_before=supplier.total_debt,
                debt_after=supplier.total_debt,
                advance_before=Decimal('0'),
                advance_after=Decimal('0'),
                debt_before_usd=Decimal('0'),
                debt_after_usd=supplier.opening_balance_usd,
                advance_before_usd=Decimal('0'),
                advance_after_usd=Decimal('0'),
                transaction_date=today,
                notes='بدهی اولیه هنگام ثبت تامین‌کننده (دالر)',
                created_by=user,
            )
            supplier.total_debt_usd = supplier.opening_balance_usd
            supplier.save(update_fields=['total_debt_usd', 'updated_at'])

    @staticmethod
    @transaction.atomic
    def update_opening_balance(
        supplier: Supplier,
        old_afn: Decimal,
        old_usd: Decimal,
        user=None,
    ):
        """
        Called on EDIT. Adjusts total_debt / total_debt_usd by the diff
        between old and new opening balances, and updates or removes the
        original OPENING_DEBT transactions so the ledger stays correct.
        """
        new_afn = supplier.opening_balance
        new_usd = supplier.opening_balance_usd
        today   = timezone.now().date()

        # ── AFN ──────────────────────────────────────────────────────────────
        diff_afn = new_afn - old_afn
        if diff_afn != 0:
            # Adjust running balance by the difference only
            supplier.total_debt = max(Decimal('0'), supplier.total_debt + diff_afn)

            # Update the existing OPENING_DEBT AFN transaction if it exists
            opening_tx_afn = SupplierTransaction.objects.filter(
                supplier=supplier,
                tx_type=SupplierTransaction.TxType.OPENING_DEBT,
                currency='AFN',
                is_reversed=False,
            ).first()

            if opening_tx_afn and new_afn > 0:
                # Update amount and snapshot on the existing transaction
                opening_tx_afn.amount     = new_afn
                opening_tx_afn.amount_afn = new_afn
                opening_tx_afn.debt_after = new_afn
                opening_tx_afn.notes      = 'بدهی اولیه (افغانی) — ویرایش شد'
                opening_tx_afn.save(update_fields=[
                    'amount', 'amount_afn', 'debt_after', 'notes'
                ])
            elif opening_tx_afn and new_afn <= 0:
                # Opening balance removed — reverse the transaction
                opening_tx_afn.is_reversed = True
                opening_tx_afn.save(update_fields=['is_reversed'])
                supplier.total_debt = max(Decimal('0'), supplier.total_debt)
            elif not opening_tx_afn and new_afn > 0:
                # Was zero before, now has a value — create fresh
                SupplierTransaction.objects.create(
                    supplier=supplier,
                    tx_type=SupplierTransaction.TxType.OPENING_DEBT,
                    currency='AFN',
                    amount=new_afn,
                    amount_afn=new_afn,
                    debt_before=Decimal('0'),
                    debt_after=new_afn,
                    advance_before=Decimal('0'),
                    advance_after=Decimal('0'),
                    debt_before_usd=supplier.total_debt_usd,
                    debt_after_usd=supplier.total_debt_usd,
                    advance_before_usd=Decimal('0'),
                    advance_after_usd=Decimal('0'),
                    transaction_date=today,
                    notes='بدهی اولیه (افغانی) — اضافه شد در ویرایش',
                    created_by=user,
                )

        # ── USD ──────────────────────────────────────────────────────────────
        diff_usd = new_usd - old_usd
        if diff_usd != 0:
            supplier.total_debt_usd = max(Decimal('0'), supplier.total_debt_usd + diff_usd)

            opening_tx_usd = SupplierTransaction.objects.filter(
                supplier=supplier,
                tx_type=SupplierTransaction.TxType.OPENING_DEBT,
                currency='USD',
                is_reversed=False,
            ).first()

            if opening_tx_usd and new_usd > 0:
                opening_tx_usd.amount         = new_usd
                opening_tx_usd.debt_after_usd = new_usd
                opening_tx_usd.notes          = 'بدهی اولیه (دالر) — ویرایش شد'
                opening_tx_usd.save(update_fields=[
                    'amount', 'debt_after_usd', 'notes'
                ])
            elif opening_tx_usd and new_usd <= 0:
                opening_tx_usd.is_reversed = True
                opening_tx_usd.save(update_fields=['is_reversed'])
                supplier.total_debt_usd = max(Decimal('0'), supplier.total_debt_usd)
            elif not opening_tx_usd and new_usd > 0:
                SupplierTransaction.objects.create(
                    supplier=supplier,
                    tx_type=SupplierTransaction.TxType.OPENING_DEBT,
                    currency='USD',
                    amount=new_usd,
                    amount_afn=Decimal('0'),
                    debt_before=supplier.total_debt,
                    debt_after=supplier.total_debt,
                    advance_before=Decimal('0'),
                    advance_after=Decimal('0'),
                    debt_before_usd=Decimal('0'),
                    debt_after_usd=new_usd,
                    advance_before_usd=Decimal('0'),
                    advance_after_usd=Decimal('0'),
                    transaction_date=today,
                    notes='بدهی اولیه (دالر) — اضافه شد در ویرایش',
                    created_by=user,
                )

        supplier.save(update_fields=['total_debt', 'total_debt_usd', 'updated_at'])

    @staticmethod
    def _apply_payment_to_balance(
        supplier, amount, currency, payment_method,
        invoice, date, notes, user
    ) -> dict:
        applied_to_debt = Decimal('0')
        new_advance     = Decimal('0')

        debt_before        = supplier.total_debt
        advance_before     = supplier.advance_balance
        debt_before_usd    = supplier.total_debt_usd
        advance_before_usd = supplier.advance_balance_usd

        if currency == 'USD':
            if supplier.total_debt_usd > 0:
                applied_to_debt = min(amount, supplier.total_debt_usd)
                dbt_b_usd = supplier.total_debt_usd
                supplier.total_debt_usd -= applied_to_debt
                SupplierTransaction.objects.create(
                    supplier=supplier,
                    tx_type=SupplierTransaction.TxType.PAYMENT,
                    currency='USD',
                    amount=applied_to_debt,
                    amount_afn=applied_to_debt,
                    debt_before=debt_before,
                    debt_after=supplier.total_debt,
                    advance_before=advance_before,
                    advance_after=advance_before,
                    debt_before_usd=dbt_b_usd,
                    debt_after_usd=supplier.total_debt_usd,
                    advance_before_usd=advance_before_usd,
                    advance_after_usd=advance_before_usd,
                    purchase_invoice=invoice,
                    payment_method=payment_method,
                    transaction_date=date,
                    notes=notes,
                    created_by=user,
                )

            excess = amount - applied_to_debt
            if excess > 0:
                new_advance = excess
                adv_b_usd = supplier.advance_balance_usd
                supplier.advance_balance_usd += excess
                SupplierTransaction.objects.create(
                    supplier=supplier,
                    tx_type=SupplierTransaction.TxType.ADVANCE_ADD,
                    currency='USD',
                    amount=excess,
                    amount_afn=excess,
                    debt_before=supplier.total_debt,
                    debt_after=supplier.total_debt,
                    advance_before=supplier.advance_balance,
                    advance_after=supplier.advance_balance,
                    debt_before_usd=supplier.total_debt_usd,
                    debt_after_usd=supplier.total_debt_usd,
                    advance_before_usd=adv_b_usd,
                    advance_after_usd=supplier.advance_balance_usd,
                    purchase_invoice=invoice,
                    payment_method=payment_method,
                    transaction_date=date,
                    notes=f'پیش‌پرداخت دالر — {date}',
                    created_by=user,
                )
        else:  # AFN
            if supplier.total_debt > 0:
                applied_to_debt = min(amount, supplier.total_debt)
                dbt_b = supplier.total_debt
                supplier.total_debt -= applied_to_debt
                SupplierTransaction.objects.create(
                    supplier=supplier,
                    tx_type=SupplierTransaction.TxType.PAYMENT,
                    currency='AFN',
                    amount=applied_to_debt,
                    amount_afn=applied_to_debt,
                    debt_before=dbt_b,
                    debt_after=supplier.total_debt,
                    advance_before=advance_before,
                    advance_after=advance_before,
                    debt_before_usd=debt_before_usd,
                    debt_after_usd=debt_before_usd,
                    advance_before_usd=advance_before_usd,
                    advance_after_usd=advance_before_usd,
                    purchase_invoice=invoice,
                    payment_method=payment_method,
                    transaction_date=date,
                    notes=notes,
                    created_by=user,
                )

            excess = amount - applied_to_debt
            if excess > 0:
                new_advance = excess
                adv_b = supplier.advance_balance
                supplier.advance_balance += excess
                SupplierTransaction.objects.create(
                    supplier=supplier,
                    tx_type=SupplierTransaction.TxType.ADVANCE_ADD,
                    currency='AFN',
                    amount=excess,
                    amount_afn=excess,
                    debt_before=supplier.total_debt,
                    debt_after=supplier.total_debt,
                    advance_before=adv_b,
                    advance_after=supplier.advance_balance,
                    debt_before_usd=debt_before_usd,
                    debt_after_usd=debt_before_usd,
                    advance_before_usd=advance_before_usd,
                    advance_after_usd=advance_before_usd,
                    purchase_invoice=invoice,
                    payment_method=payment_method,
                    transaction_date=date,
                    notes=f'پیش‌پرداخت افغانی — {date}',
                    created_by=user,
                )

        return {
            'applied_to_debt': applied_to_debt,
            'new_advance': new_advance,
        }

    @staticmethod
    @transaction.atomic
    def apply_payment_to_open_invoices(
        supplier: Supplier,
        amount: Decimal,
        currency: str,
        date,
        user=None,
    ) -> Decimal:
        from apps.purchases.models import PurchaseInvoice

        remaining_to_apply = amount
        open_invoices = PurchaseInvoice.objects.filter(
            supplier=supplier,
            currency=currency,
            is_deleted=False,
            status__in=[PurchaseInvoice.Status.UNPAID, PurchaseInvoice.Status.PARTIAL],
        ).order_by('purchase_date', 'created_at')

        for invoice in open_invoices:
            if remaining_to_apply <= 0:
                break
            apply_amt = min(remaining_to_apply, invoice.remaining_amount)
            if apply_amt <= 0:
                continue

            invoice.paid_amount      += apply_amt
            invoice.remaining_amount  = invoice.total_amount - invoice.paid_amount
            if invoice.remaining_amount <= 0:
                invoice.status = PurchaseInvoice.Status.PAID
                invoice.remaining_amount = Decimal('0')
            else:
                invoice.status = PurchaseInvoice.Status.PARTIAL
            invoice.save(update_fields=['paid_amount', 'remaining_amount', 'status', 'updated_at'])

            remaining_to_apply -= apply_amt

        applied = amount - remaining_to_apply
        return applied

    @staticmethod
    @transaction.atomic
    def recalculate_supplier_balance(supplier):
        supplier = Supplier.objects.select_for_update().get(pk=supplier.pk)

        total_debt     = supplier.opening_balance      # start from opening balance (AFN)
        advance_bal    = Decimal('0')
        total_debt_usd = supplier.opening_balance_usd  # start from opening balance (USD)
        advance_usd    = Decimal('0')

        # Replay all non-reversed, non-REVERSAL, non-OPENING_DEBT transactions
        # in chronological order
        txs = SupplierTransaction.objects.filter(
            supplier=supplier,
            is_reversed=False,
        ).exclude(
            tx_type=SupplierTransaction.TxType.REVERSAL
        ).exclude(
            tx_type=SupplierTransaction.TxType.OPENING_DEBT
        ).order_by('transaction_date', 'created_at')

        for tx in txs:
            t   = tx.tx_type
            cur = tx.currency
            amt = tx.amount

            if cur == 'USD':
                if t == SupplierTransaction.TxType.PURCHASE:
                    total_debt_usd += amt
                elif t == SupplierTransaction.TxType.PAYMENT:
                    total_debt_usd = max(Decimal('0'), total_debt_usd - amt)
                elif t == SupplierTransaction.TxType.ADVANCE_ADD:
                    advance_usd += amt
                elif t == SupplierTransaction.TxType.ADVANCE_USE:
                    advance_usd    = max(Decimal('0'), advance_usd - amt)
                    total_debt_usd = max(Decimal('0'), total_debt_usd - amt)
            else:  # AFN
                if t == SupplierTransaction.TxType.PURCHASE:
                    total_debt += amt
                elif t == SupplierTransaction.TxType.PAYMENT:
                    total_debt = max(Decimal('0'), total_debt - amt)
                elif t == SupplierTransaction.TxType.ADVANCE_ADD:
                    advance_bal += amt
                elif t == SupplierTransaction.TxType.ADVANCE_USE:
                    advance_bal = max(Decimal('0'), advance_bal - amt)
                    total_debt  = max(Decimal('0'), total_debt - amt)

        supplier.total_debt          = max(Decimal('0'), total_debt)
        supplier.advance_balance     = max(Decimal('0'), advance_bal)
        supplier.total_debt_usd      = max(Decimal('0'), total_debt_usd)
        supplier.advance_balance_usd = max(Decimal('0'), advance_usd)
        supplier.save(update_fields=[
            'total_debt', 'advance_balance',
            'total_debt_usd', 'advance_balance_usd', 'updated_at'
        ])
        return supplier