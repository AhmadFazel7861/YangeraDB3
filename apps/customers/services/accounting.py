"""
CustomerAccountingService — dual-currency accounting engine.
AFN and USD balances tracked separately.
USD payments with exchange_rate can also reduce AFN debt.
"""
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.customers.models import Customer, CustomerTransaction, CustomerPayment


class CustomerAccountingService:

    @staticmethod
    @transaction.atomic
    def apply_invoice(
        customer: Customer,
        invoice,
        paid_amount: Decimal = Decimal('0'),
        payment_method: str = 'cash',
        currency: str = 'AFN',
        exchange_rate: Decimal = Decimal('1'),
        user=None
    ) -> dict:
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        invoice_amount = invoice.total_amount
        inv_currency   = getattr(invoice, 'currency', 'AFN')

        # Snapshots
        debt_before         = customer.total_debt
        advance_before      = customer.advance_balance
        debt_before_usd     = customer.total_debt_usd
        advance_before_usd  = customer.advance_balance_usd

        # Step 1: Add invoice to correct debt bucket
        if inv_currency == 'USD':
            customer.total_debt_usd += invoice_amount
            amount_afn = (invoice_amount * exchange_rate).quantize(Decimal('0.01'))
        else:
            customer.total_debt += invoice_amount
            amount_afn = invoice_amount

        CustomerTransaction.objects.create(
            customer=customer,
            tx_type=CustomerTransaction.TxType.INVOICE,
            currency=inv_currency,
            exchange_rate=exchange_rate,
            amount=invoice_amount,
            amount_afn=amount_afn,
            debt_before=debt_before,
            debt_after=customer.total_debt,
            advance_before=advance_before,
            advance_after=advance_before,
            debt_before_usd=debt_before_usd,
            debt_after_usd=customer.total_debt_usd,
            advance_before_usd=advance_before_usd,
            advance_after_usd=advance_before_usd,
            invoice=invoice,
            transaction_date=invoice.invoice_date,
            notes=f'فاکتور {invoice.invoice_number}',
            created_by=user,
        )

        # Step 2: Auto-use advance — SAME currency only, never cross-currency
        advance_used = Decimal('0')
        if inv_currency == 'USD' and customer.advance_balance_usd > 0:
            advance_used = min(customer.advance_balance_usd, customer.total_debt_usd)
            if advance_used > 0:
                adv_b = customer.advance_balance_usd
                customer.advance_balance_usd -= advance_used
                customer.total_debt_usd      -= advance_used
                CustomerTransaction.objects.create(
                    customer=customer,
                    tx_type=CustomerTransaction.TxType.ADVANCE_USE,
                    currency='USD',
                    exchange_rate=exchange_rate,
                    amount=advance_used,
                    amount_afn=(advance_used * exchange_rate).quantize(Decimal('0.01')),
                    debt_before=customer.total_debt,
                    debt_after=customer.total_debt,
                    advance_before=customer.advance_balance,
                    advance_after=customer.advance_balance,
                    debt_before_usd=customer.total_debt_usd + advance_used,
                    debt_after_usd=customer.total_debt_usd,
                    advance_before_usd=adv_b,
                    advance_after_usd=customer.advance_balance_usd,
                    invoice=invoice,
                    transaction_date=invoice.invoice_date,
                    notes=f'کسر پیش‌پرداخت دالر فاکتور {invoice.invoice_number}',
                    created_by=user,
                )
        elif inv_currency == 'AFN' and customer.advance_balance > 0:
            advance_used = min(customer.advance_balance, customer.total_debt)
            if advance_used > 0:
                adv_b = customer.advance_balance
                customer.advance_balance -= advance_used
                customer.total_debt      -= advance_used
                CustomerTransaction.objects.create(
                    customer=customer,
                    tx_type=CustomerTransaction.TxType.ADVANCE_USE,
                    currency='AFN',
                    exchange_rate=Decimal('1'),
                    amount=advance_used,
                    amount_afn=advance_used,
                    debt_before=customer.total_debt + advance_used,
                    debt_after=customer.total_debt,
                    advance_before=adv_b,
                    advance_after=customer.advance_balance,
                    debt_before_usd=customer.total_debt_usd,
                    debt_after_usd=customer.total_debt_usd,
                    advance_before_usd=customer.advance_balance_usd,
                    advance_after_usd=customer.advance_balance_usd,
                    invoice=invoice,
                    transaction_date=invoice.invoice_date,
                    notes=f'کسر پیش‌پرداخت افغانی فاکتور {invoice.invoice_number}',
                    created_by=user,
                )

        # Step 3: Apply cash payment — strictly same currency as invoice
        cash_applied = Decimal('0')
        new_advance  = Decimal('0')
        pay_currency = inv_currency  # always match invoice currency, ignore caller's currency arg

        if paid_amount > 0:
            result = CustomerAccountingService._apply_payment_to_balance(
                customer=customer,
                amount=paid_amount,
                currency=pay_currency,
                exchange_rate=Decimal('1'),  # no cross-currency conversion on invoice payment
                payment_method=payment_method,
                invoice=invoice,
                date=invoice.invoice_date,
                notes=f'پرداخت فاکتور {invoice.invoice_number}',
                user=user,
                skip_cross_currency=True,  # invoice payment never clears other-currency debt
            )
            cash_applied = result['applied_to_debt']
            new_advance  = result['new_advance']

        # Step 4: Update invoice paid/remaining/status
        actual_paid = advance_used + cash_applied
        invoice.paid_amount      = actual_paid
        invoice.remaining_amount = max(Decimal('0'), invoice_amount - actual_paid)
        from apps.sales.models import Invoice as SalesInvoice
        if invoice.remaining_amount <= 0:
            invoice.status = SalesInvoice.Status.PAID
        elif actual_paid > 0:
            invoice.status = SalesInvoice.Status.PARTIAL
        else:
            invoice.status = SalesInvoice.Status.CONFIRMED
        invoice.save(update_fields=['paid_amount', 'remaining_amount', 'status', 'updated_at'])

        customer.last_transaction_date = invoice.invoice_date
        customer.save(update_fields=[
            'total_debt', 'advance_balance',
            'total_debt_usd', 'advance_balance_usd',
            'last_transaction_date', 'updated_at'
        ])

        return {
            'advance_used': advance_used,
            'cash_applied': cash_applied,
            'new_advance': new_advance,
            'remaining_debt': customer.total_debt,
            'remaining_debt_usd': customer.total_debt_usd,
        }

    @staticmethod
    @transaction.atomic
    def apply_payment(
        customer: Customer,
        amount: Decimal,
        payment_method: str = 'cash',
        currency: str = 'AFN',
        exchange_rate: Decimal = Decimal('1'),
        payment_date=None,
        notes: str = '',
        invoice=None,
        user=None
    ) -> CustomerPayment:
        if amount <= 0:
            raise ValidationError('مبلغ پرداخت باید بیشتر از صفر باشد.')
        if payment_date is None:
            payment_date = timezone.now().date()

        customer = Customer.objects.select_for_update().get(pk=customer.pk)

        result = CustomerAccountingService._apply_payment_to_balance(
            customer=customer,
            amount=amount,
            currency=currency,
            exchange_rate=exchange_rate,
            payment_method=payment_method,
            invoice=invoice,
            date=payment_date,
            notes=notes or f'دریافت وجه — {payment_date}',
            user=user,
            # skip_cross_currency NOT set — standalone payments may clear cross-currency debt
        )

        customer.last_transaction_date = payment_date
        customer.save(update_fields=[
            'total_debt', 'advance_balance',
            'total_debt_usd', 'advance_balance_usd',
            'last_transaction_date', 'updated_at'
        ])

        tx = CustomerTransaction.objects.filter(
            customer=customer,
            tx_type__in=[
                CustomerTransaction.TxType.PAYMENT,
                CustomerTransaction.TxType.ADVANCE_ADD,
            ],
            transaction_date=payment_date,
            created_by=user,
        ).order_by('-created_at').first()

        payment = CustomerPayment.objects.create(
            customer=customer,
            transaction=tx,
            amount=amount,
            payment_method=payment_method,
            currency=currency,
            exchange_rate=exchange_rate,
            payment_date=payment_date,
            notes=notes,
            received_by=user,
        )
        return payment

    @staticmethod
    @transaction.atomic
    def add_advance(
        customer: Customer,
        amount: Decimal,
        payment_method: str = 'cash',
        currency: str = 'AFN',
        exchange_rate: Decimal = Decimal('1'),
        payment_date=None,
        notes: str = '',
        user=None
    ) -> CustomerTransaction:
        if amount <= 0:
            raise ValidationError('مبلغ باید بیشتر از صفر باشد.')
        if payment_date is None:
            payment_date = timezone.now().date()

        customer = Customer.objects.select_for_update().get(pk=customer.pk)

        result = CustomerAccountingService._apply_payment_to_balance(
            customer=customer,
            amount=amount,
            currency=currency,
            exchange_rate=exchange_rate,
            payment_method=payment_method,
            invoice=None,
            date=payment_date,
            notes=notes or f'افزایش پیش‌پرداخت — {payment_date}',
            user=user,
        )

        customer.last_transaction_date = payment_date
        customer.save(update_fields=[
            'total_debt', 'advance_balance',
            'total_debt_usd', 'advance_balance_usd',
            'last_transaction_date', 'updated_at'
        ])

        return result

    @staticmethod
    @transaction.atomic
    def reverse_invoice(
        customer: Customer,
        invoice,
        user=None,
    ) -> None:
        customer = Customer.objects.select_for_update().get(pk=customer.pk)

        txs = CustomerTransaction.objects.filter(
            invoice=invoice,
            is_reversed=False,
        ).exclude(
            tx_type=CustomerTransaction.TxType.REVERSAL,
        ).order_by('-created_at')

        for tx in txs:
            amount = tx.amount
            t      = tx.tx_type
            cur    = tx.currency

            debt_before         = customer.total_debt
            advance_before      = customer.advance_balance
            debt_before_usd     = customer.total_debt_usd
            advance_before_usd  = customer.advance_balance_usd

            if cur == 'USD':
                if t == CustomerTransaction.TxType.INVOICE:
                    # Undo the debt added when invoice was created
                    customer.total_debt_usd = max(Decimal('0'), customer.total_debt_usd - amount)

                elif t == CustomerTransaction.TxType.ADVANCE_USE:
                    # Undo advance-used-against-debt: restore both advance and debt
                    customer.advance_balance_usd += amount
                    customer.total_debt_usd      += amount

                elif t == CustomerTransaction.TxType.PAYMENT:
                    # Undo a payment: cash paid comes back as advance.
                    # The INVOICE reversal above already removed the debt —
                    # do NOT add back to debt here or it will double-count.
                    customer.advance_balance_usd += amount

                elif t == CustomerTransaction.TxType.ADVANCE_ADD:
                    # Undo an overpayment that became advance
                    customer.advance_balance_usd = max(Decimal('0'), customer.advance_balance_usd - amount)

                else:
                    continue

            else:  # AFN
                if t == CustomerTransaction.TxType.INVOICE:
                    # Undo the debt added when invoice was created
                    customer.total_debt = max(Decimal('0'), customer.total_debt - amount)

                elif t == CustomerTransaction.TxType.ADVANCE_USE:
                    # Undo advance-used-against-debt: restore both advance and debt
                    customer.advance_balance += amount
                    customer.total_debt      += amount

                elif t == CustomerTransaction.TxType.PAYMENT:
                    # Undo a payment: cash paid comes back as advance.
                    # The INVOICE reversal above already removed the debt —
                    # do NOT add back to debt here or it will double-count.
                    customer.advance_balance += amount

                elif t == CustomerTransaction.TxType.ADVANCE_ADD:
                    # Undo an overpayment that became advance
                    customer.advance_balance = max(Decimal('0'), customer.advance_balance - amount)

                else:
                    continue

            reversal = CustomerTransaction.objects.create(
                customer=customer,
                tx_type=CustomerTransaction.TxType.REVERSAL,
                currency=cur,
                exchange_rate=tx.exchange_rate,
                amount=amount,
                amount_afn=tx.amount_afn,
                debt_before=debt_before,
                debt_after=customer.total_debt,
                advance_before=advance_before,
                advance_after=customer.advance_balance,
                debt_before_usd=debt_before_usd,
                debt_after_usd=customer.total_debt_usd,
                advance_before_usd=advance_before_usd,
                advance_after_usd=customer.advance_balance_usd,
                invoice=invoice,
                transaction_date=timezone.now().date(),
                notes=f'برگشت فاکتور {invoice.invoice_number} — {tx.get_tx_type_display()}',
                created_by=user,
            )

            tx.is_reversed = True
            tx.reversed_by = reversal
            tx.save(update_fields=['is_reversed', 'reversed_by'])

        customer.last_transaction_date = timezone.now().date()
        customer.save(update_fields=[
            'total_debt', 'advance_balance',
            'total_debt_usd', 'advance_balance_usd',
            'last_transaction_date', 'updated_at',
        ])

    @staticmethod
    @transaction.atomic
    def reverse_transaction(
        transaction_obj: CustomerTransaction,
        notes: str = '',
        user=None
    ) -> CustomerTransaction:
        if transaction_obj.is_reversed:
            raise ValidationError('این تراکنش قبلاً برگشت داده شده است.')

        customer = Customer.objects.select_for_update().get(pk=transaction_obj.customer.pk)
        amount = transaction_obj.amount
        t      = transaction_obj.tx_type
        cur    = transaction_obj.currency

        debt_before        = customer.total_debt
        advance_before     = customer.advance_balance
        debt_before_usd    = customer.total_debt_usd
        advance_before_usd = customer.advance_balance_usd

        if cur == 'USD':
            if t == CustomerTransaction.TxType.INVOICE:
                customer.total_debt_usd = max(Decimal('0'), customer.total_debt_usd - amount)
            elif t == CustomerTransaction.TxType.PAYMENT:
                customer.total_debt_usd += amount
            elif t == CustomerTransaction.TxType.ADVANCE_ADD:
                customer.advance_balance_usd = max(Decimal('0'), customer.advance_balance_usd - amount)
            elif t == CustomerTransaction.TxType.ADVANCE_USE:
                customer.advance_balance_usd += amount
                customer.total_debt_usd      += amount
        else:
            if t == CustomerTransaction.TxType.INVOICE:
                customer.total_debt = max(Decimal('0'), customer.total_debt - amount)
            elif t == CustomerTransaction.TxType.PAYMENT:
                customer.total_debt += amount
            elif t == CustomerTransaction.TxType.ADVANCE_ADD:
                customer.advance_balance = max(Decimal('0'), customer.advance_balance - amount)
            elif t == CustomerTransaction.TxType.ADVANCE_USE:
                customer.advance_balance += amount
                customer.total_debt      += amount
            elif t == CustomerTransaction.TxType.ADVANCE_REFUND:
                customer.advance_balance += amount

        reversal = CustomerTransaction.objects.create(
            customer=customer,
            tx_type=CustomerTransaction.TxType.REVERSAL,
            currency=cur,
            exchange_rate=transaction_obj.exchange_rate,
            amount=amount,
            amount_afn=transaction_obj.amount_afn,
            debt_before=debt_before,
            debt_after=customer.total_debt,
            advance_before=advance_before,
            advance_after=customer.advance_balance,
            debt_before_usd=debt_before_usd,
            debt_after_usd=customer.total_debt_usd,
            advance_before_usd=advance_before_usd,
            advance_after_usd=customer.advance_balance_usd,
            invoice=transaction_obj.invoice,
            transaction_date=timezone.now().date(),
            notes=notes or f'برگشت: {transaction_obj.get_tx_type_display()}',
            created_by=user,
        )

        transaction_obj.is_reversed = True
        transaction_obj.reversed_by = reversal
        transaction_obj.save(update_fields=['is_reversed', 'reversed_by'])

        customer.last_transaction_date = timezone.now().date()
        customer.save(update_fields=[
            'total_debt', 'advance_balance',
            'total_debt_usd', 'advance_balance_usd',
            'last_transaction_date', 'updated_at'
        ])
        return reversal

    @staticmethod
    @transaction.atomic
    def initialize_opening_balance(customer: Customer, user=None):
        """
        Posts opening balance transactions for AFN and/or USD, whichever
        are > 0. Each currency is checked and recorded independently, and
        each only runs once (idempotent), matching the original AFN-only
        behavior exactly.
        """
        # ── AFN opening balance (unchanged from original) ──
        if customer.opening_balance > 0:
            already_afn = CustomerTransaction.objects.filter(
                customer=customer,
                tx_type=CustomerTransaction.TxType.OPENING_DEBT,
                currency='AFN',
            ).exists()
            if not already_afn:
                CustomerTransaction.objects.create(
                    customer=customer,
                    tx_type=CustomerTransaction.TxType.OPENING_DEBT,
                    currency='AFN',
                    exchange_rate=Decimal('1'),
                    amount=customer.opening_balance,
                    amount_afn=customer.opening_balance,
                    debt_before=Decimal('0'),
                    debt_after=customer.opening_balance,
                    advance_before=Decimal('0'),
                    advance_after=Decimal('0'),
                    debt_before_usd=Decimal('0'),
                    debt_after_usd=Decimal('0'),
                    advance_before_usd=Decimal('0'),
                    advance_after_usd=Decimal('0'),
                    transaction_date=customer.created_at.date(),
                    notes='بدهی اولیه هنگام ثبت مشتری',
                    created_by=user,
                )
                customer.total_debt = customer.opening_balance
                customer.save(update_fields=['total_debt', 'updated_at'])

        # ── USD opening balance (new) ──
        if customer.opening_balance_usd > 0:
            already_usd = CustomerTransaction.objects.filter(
                customer=customer,
                tx_type=CustomerTransaction.TxType.OPENING_DEBT,
                currency='USD',
            ).exists()
            if not already_usd:
                CustomerTransaction.objects.create(
                    customer=customer,
                    tx_type=CustomerTransaction.TxType.OPENING_DEBT,
                    currency='USD',
                    exchange_rate=Decimal('1'),
                    amount=customer.opening_balance_usd,
                    amount_afn=Decimal('0'),  # no exchange rate known at customer creation
                    debt_before=Decimal('0'),
                    debt_after=Decimal('0'),
                    advance_before=Decimal('0'),
                    advance_after=Decimal('0'),
                    debt_before_usd=Decimal('0'),
                    debt_after_usd=customer.opening_balance_usd,
                    advance_before_usd=Decimal('0'),
                    advance_after_usd=Decimal('0'),
                    transaction_date=customer.created_at.date(),
                    notes='بدهی اولیه دالر هنگام ثبت مشتری',
                    created_by=user,
                )
                customer.total_debt_usd = customer.opening_balance_usd
                customer.save(update_fields=['total_debt_usd', 'updated_at'])

    @staticmethod
    @transaction.atomic
    def recalculate_customer_balance(customer: Customer):
        customer = Customer.objects.select_for_update().get(pk=customer.pk)

        total_debt     = customer.opening_balance
        advance_bal    = Decimal('0')
        total_debt_usd = customer.opening_balance_usd
        advance_usd    = Decimal('0')

        txs = CustomerTransaction.objects.filter(
            customer=customer, is_reversed=False,
        ).exclude(
            tx_type=CustomerTransaction.TxType.REVERSAL
        ).exclude(
            tx_type=CustomerTransaction.TxType.OPENING_DEBT
        ).order_by('transaction_date', 'created_at')

        for tx in txs:
            t   = tx.tx_type
            cur = tx.currency
            amt = tx.amount

            if cur == 'USD':
                if t == CustomerTransaction.TxType.INVOICE:
                    total_debt_usd += amt
                elif t == CustomerTransaction.TxType.PAYMENT:
                    total_debt_usd = max(Decimal('0'), total_debt_usd - amt)
                elif t == CustomerTransaction.TxType.ADVANCE_ADD:
                    advance_usd += amt
                elif t == CustomerTransaction.TxType.ADVANCE_USE:
                    advance_usd    = max(Decimal('0'), advance_usd - amt)
                    total_debt_usd = max(Decimal('0'), total_debt_usd - amt)
            else:
                if t == CustomerTransaction.TxType.INVOICE:
                    total_debt += amt
                elif t == CustomerTransaction.TxType.PAYMENT:
                    total_debt = max(Decimal('0'), total_debt - amt)
                elif t == CustomerTransaction.TxType.ADVANCE_ADD:
                    advance_bal += amt
                elif t == CustomerTransaction.TxType.ADVANCE_USE:
                    advance_bal = max(Decimal('0'), advance_bal - amt)
                    total_debt  = max(Decimal('0'), total_debt - amt)
                elif t == CustomerTransaction.TxType.DEBT_WRITE_OFF:
                    total_debt = max(Decimal('0'), total_debt - amt)

        customer.total_debt          = max(Decimal('0'), total_debt)
        customer.advance_balance     = max(Decimal('0'), advance_bal)
        customer.total_debt_usd      = max(Decimal('0'), total_debt_usd)
        customer.advance_balance_usd = max(Decimal('0'), advance_usd)
        customer.save(update_fields=[
            'total_debt', 'advance_balance',
            'total_debt_usd', 'advance_balance_usd', 'updated_at'
        ])
        return customer

    @staticmethod
    @transaction.atomic
    def _apply_payment_to_balance(
        customer, amount, currency, exchange_rate,
        payment_method, invoice, date, notes, user,
        skip_cross_currency: bool = False,
    ) -> dict:
        """
        Core payment logic.

        AFN payment  → reduces AFN debt → excess to AFN advance
        USD payment:
          1. If customer has AFN debt and exchange_rate > 1 AND skip_cross_currency=False:
             convert USD to AFN, clear AFN debt first.
             (Skipped for invoice payments — each currency stays in its own bucket)
          2. Remaining USD reduces USD debt
          3. Any further excess → USD advance
        """
        applied_to_debt = Decimal('0')
        new_advance     = Decimal('0')

        debt_before        = customer.total_debt
        advance_before     = customer.advance_balance
        debt_before_usd    = customer.total_debt_usd
        advance_before_usd = customer.advance_balance_usd

        if currency == 'USD':
            remaining_usd = amount

            # Step 1: Use USD to clear AFN debt (standalone payments only)
            # Never fires for invoice payments (skip_cross_currency=True)
            if not skip_cross_currency and exchange_rate > 1 and customer.total_debt > 0:
                afn_equivalent   = (remaining_usd * exchange_rate).quantize(Decimal('0.01'))
                afn_to_clear     = min(afn_equivalent, customer.total_debt)
                usd_used_for_afn = (afn_to_clear / exchange_rate).quantize(Decimal('0.0001'), rounding='ROUND_UP')
                usd_used_for_afn = min(usd_used_for_afn, remaining_usd)

                if afn_to_clear > 0:
                    dbt_b = customer.total_debt
                    customer.total_debt -= afn_to_clear
                    CustomerTransaction.objects.create(
                        customer=customer,
                        tx_type=CustomerTransaction.TxType.PAYMENT,
                        currency='USD',
                        exchange_rate=exchange_rate,
                        amount=usd_used_for_afn,
                        amount_afn=afn_to_clear,
                        debt_before=dbt_b,
                        debt_after=customer.total_debt,
                        advance_before=advance_before,
                        advance_after=advance_before,
                        debt_before_usd=debt_before_usd,
                        debt_after_usd=customer.total_debt_usd,
                        advance_before_usd=advance_before_usd,
                        advance_after_usd=advance_before_usd,
                        invoice=invoice,
                        payment_method=payment_method,
                        transaction_date=date,
                        notes=f'{notes} — کسر بدهی افغانی',
                        created_by=user,
                    )
                    remaining_usd   -= usd_used_for_afn
                    applied_to_debt += usd_used_for_afn

            # Step 2: Use remaining USD to clear USD debt
            if remaining_usd > 0 and customer.total_debt_usd > 0:
                usd_to_clear  = min(remaining_usd, customer.total_debt_usd)
                dbt_b_usd     = customer.total_debt_usd
                customer.total_debt_usd -= usd_to_clear
                CustomerTransaction.objects.create(
                    customer=customer,
                    tx_type=CustomerTransaction.TxType.PAYMENT,
                    currency='USD',
                    exchange_rate=exchange_rate,
                    amount=usd_to_clear,
                    amount_afn=(usd_to_clear * exchange_rate).quantize(Decimal('0.01')),
                    debt_before=customer.total_debt,
                    debt_after=customer.total_debt,
                    advance_before=advance_before,
                    advance_after=advance_before,
                    debt_before_usd=dbt_b_usd,
                    debt_after_usd=customer.total_debt_usd,
                    advance_before_usd=advance_before_usd,
                    advance_after_usd=advance_before_usd,
                    invoice=invoice,
                    payment_method=payment_method,
                    transaction_date=date,
                    notes=f'{notes} — کسر بدهی دالر',
                    created_by=user,
                )
                remaining_usd   -= usd_to_clear
                applied_to_debt += usd_to_clear

            # Step 3: Any remaining USD → USD advance
            if remaining_usd > 0:
                new_advance = remaining_usd
                adv_b_usd   = customer.advance_balance_usd
                customer.advance_balance_usd += remaining_usd
                CustomerTransaction.objects.create(
                    customer=customer,
                    tx_type=CustomerTransaction.TxType.ADVANCE_ADD,
                    currency='USD',
                    exchange_rate=exchange_rate,
                    amount=remaining_usd,
                    amount_afn=(remaining_usd * exchange_rate).quantize(Decimal('0.01')),
                    debt_before=customer.total_debt,
                    debt_after=customer.total_debt,
                    advance_before=customer.advance_balance,
                    advance_after=customer.advance_balance,
                    debt_before_usd=customer.total_debt_usd,
                    debt_after_usd=customer.total_debt_usd,
                    advance_before_usd=adv_b_usd,
                    advance_after_usd=customer.advance_balance_usd,
                    invoice=invoice,
                    payment_method=payment_method,
                    transaction_date=date,
                    notes=f'پیش‌پرداخت دالر — {date}',
                    created_by=user,
                )

        else:  # AFN
            # Clear AFN debt first
            if customer.total_debt > 0:
                applied_to_debt = min(amount, customer.total_debt)
                dbt_b = customer.total_debt
                customer.total_debt -= applied_to_debt
                CustomerTransaction.objects.create(
                    customer=customer,
                    tx_type=CustomerTransaction.TxType.PAYMENT,
                    currency='AFN',
                    exchange_rate=Decimal('1'),
                    amount=applied_to_debt,
                    amount_afn=applied_to_debt,
                    debt_before=dbt_b,
                    debt_after=customer.total_debt,
                    advance_before=advance_before,
                    advance_after=advance_before,
                    debt_before_usd=debt_before_usd,
                    debt_after_usd=debt_before_usd,
                    advance_before_usd=advance_before_usd,
                    advance_after_usd=advance_before_usd,
                    invoice=invoice,
                    payment_method=payment_method,
                    transaction_date=date,
                    notes=notes,
                    created_by=user,
                )

            # Excess → AFN advance
            excess = amount - applied_to_debt
            if excess > 0:
                new_advance = excess
                adv_b = customer.advance_balance
                customer.advance_balance += excess
                CustomerTransaction.objects.create(
                    customer=customer,
                    tx_type=CustomerTransaction.TxType.ADVANCE_ADD,
                    currency='AFN',
                    exchange_rate=Decimal('1'),
                    amount=excess,
                    amount_afn=excess,
                    debt_before=customer.total_debt,
                    debt_after=customer.total_debt,
                    advance_before=adv_b,
                    advance_after=customer.advance_balance,
                    debt_before_usd=debt_before_usd,
                    debt_after_usd=debt_before_usd,
                    advance_before_usd=advance_before_usd,
                    advance_after_usd=advance_before_usd,
                    invoice=invoice,
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
        customer: Customer,
        amount: Decimal,
        currency: str,
        date,
        user=None,
    ) -> Decimal:
        """
        Apply a general payment (not tied to a specific invoice) against
        the customer's oldest open sales invoices first, in the given
        currency. Updates each invoice's paid_amount/remaining_amount/status.

        Returns the amount actually applied.
        """
        from apps.sales.models import Invoice

        remaining_to_apply = amount
        open_invoices = Invoice.objects.filter(
            customer=customer,
            currency=currency,
            is_deleted=False,
            status__in=[Invoice.Status.CONFIRMED, Invoice.Status.PARTIAL],
        ).order_by('invoice_date', 'created_at')

        for invoice in open_invoices:
            if remaining_to_apply <= 0:
                break
            apply_amt = min(remaining_to_apply, invoice.remaining_amount)
            if apply_amt <= 0:
                continue

            invoice.paid_amount      += apply_amt
            invoice.remaining_amount  = invoice.total_amount - invoice.paid_amount
            if invoice.remaining_amount <= 0:
                invoice.status = Invoice.Status.PAID
                invoice.remaining_amount = Decimal('0')
            else:
                invoice.status = Invoice.Status.PARTIAL
            invoice.save(update_fields=['paid_amount', 'remaining_amount', 'status', 'updated_at'])

            remaining_to_apply -= apply_amt

        applied = amount - remaining_to_apply
        return applied