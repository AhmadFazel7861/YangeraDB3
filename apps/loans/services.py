"""
LoanService — atomic engine for all loan operations.

Three public methods:
  give_loan(person, amount, currency, payment_method, banker, date, notes, user)
  record_repayment(person, amount, currency, payment_method, banker, date, notes, user)
  reverse_transaction(loan_tx, notes, user)

Integration rules (matches existing patterns exactly):
  CASH   → only updates LoanPerson balance. No side effects.
  SARAF  → calls BankerService.record_transaction with GIVEN (lending out)
            or RECEIVED (repayment comes back to us).
  DAKKAN → creates a LoanDakkhanEntry so CapitalService.get_shop_income
            can subtract outflows and add inflows when computing net_afn/net_usd.
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import LoanPerson, LoanTransaction, LoanDakkhanEntry


class LoanService:

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def give_loan(
        person: LoanPerson,
        amount: Decimal,
        currency: str,
        payment_method: str,
        transaction_date=None,
        banker=None,
        notes: str = '',
        user=None,
    ) -> LoanTransaction:
        """
        Record lending money OUT to person.
        Increases person's debt balance.
        """
        LoanService._validate(amount, currency, payment_method, banker)
        if transaction_date is None:
            transaction_date = timezone.now().date()

        person = LoanPerson.objects.select_for_update().get(pk=person.pk)

        balance_before_afn = person.balance_afn
        balance_before_usd = person.balance_usd

        # Update running balance
        if currency == 'AFN':
            person.balance_afn += amount
        else:
            person.balance_usd += amount
        person.save(update_fields=['balance_afn', 'balance_usd', 'updated_at'])

        loan_tx = LoanTransaction.objects.create(
            person=person,
            tx_type=LoanTransaction.TxType.GIVEN,
            currency=currency,
            amount=amount,
            payment_method=payment_method,
            banker=banker if payment_method == LoanTransaction.PaymentMethod.SARAF else None,
            balance_before_afn=balance_before_afn,
            balance_after_afn=person.balance_afn,
            balance_before_usd=balance_before_usd,
            balance_after_usd=person.balance_usd,
            transaction_date=transaction_date,
            notes=notes,
            created_by=user,
        )

        # Side effects per payment method
        if payment_method == LoanTransaction.PaymentMethod.SARAF:
            # Lending via saraf: money leaves our banker balance (RECEIVED = debit)
            LoanService._saraf_debit(banker, amount, currency, transaction_date, loan_tx, user)

        elif payment_method == LoanTransaction.PaymentMethod.DAKKAN:
            # Cash left the shop till
            LoanService._dakkan_entry(loan_tx, amount, currency, transaction_date, is_outflow=True)

        LoanService._log('create', person, loan_tx, user)
        return loan_tx

    @staticmethod
    @transaction.atomic
    def record_repayment(
        person: LoanPerson,
        amount: Decimal,
        currency: str,
        payment_method: str,
        transaction_date=None,
        banker=None,
        notes: str = '',
        user=None,
    ) -> LoanTransaction:
        """
        Record repayment received FROM person.
        Decreases person's debt balance.
        """
        LoanService._validate(amount, currency, payment_method, banker)
        if transaction_date is None:
            transaction_date = timezone.now().date()

        person = LoanPerson.objects.select_for_update().get(pk=person.pk)

        balance_before_afn = person.balance_afn
        balance_before_usd = person.balance_usd

        # Update running balance
        if currency == 'AFN':
            person.balance_afn -= amount
        else:
            person.balance_usd -= amount
        person.save(update_fields=['balance_afn', 'balance_usd', 'updated_at'])

        loan_tx = LoanTransaction.objects.create(
            person=person,
            tx_type=LoanTransaction.TxType.RECEIVED,
            currency=currency,
            amount=amount,
            payment_method=payment_method,
            banker=banker if payment_method == LoanTransaction.PaymentMethod.SARAF else None,
            balance_before_afn=balance_before_afn,
            balance_after_afn=person.balance_afn,
            balance_before_usd=balance_before_usd,
            balance_after_usd=person.balance_usd,
            transaction_date=transaction_date,
            notes=notes,
            created_by=user,
        )

        # Side effects per payment method
        if payment_method == LoanTransaction.PaymentMethod.SARAF:
            # Repayment via saraf: money comes back to our banker balance (GIVEN = credit)
            LoanService._saraf_credit(banker, amount, currency, transaction_date, loan_tx, user)

        elif payment_method == LoanTransaction.PaymentMethod.DAKKAN:
            # Cash returned to the shop till
            LoanService._dakkan_entry(loan_tx, amount, currency, transaction_date, is_outflow=False)

        LoanService._log('create', person, loan_tx, user)
        return loan_tx

    @staticmethod
    @transaction.atomic
    def reverse_transaction(
        loan_tx: LoanTransaction,
        notes: str = '',
        user=None,
    ) -> LoanTransaction:
        """
        Reverse a previously recorded loan transaction.
        Creates a mirror reversal transaction (not a delete).
        Also reverses any banker or dakkan side effects.
        """
        if loan_tx.is_reversed:
            raise ValidationError('این تراکنش قبلاً برگشت داده شده است.')

        person = LoanPerson.objects.select_for_update().get(pk=loan_tx.person.pk)
        amount   = loan_tx.amount
        currency = loan_tx.currency

        balance_before_afn = person.balance_afn
        balance_before_usd = person.balance_usd

        # Undo the original balance change
        if loan_tx.tx_type == LoanTransaction.TxType.GIVEN:
            # Original gave money out → undo by reducing the debt
            if currency == 'AFN':
                person.balance_afn -= amount
            else:
                person.balance_usd -= amount
            reversal_tx_type = LoanTransaction.TxType.RECEIVED
        else:
            # Original received repayment → undo by adding debt back
            if currency == 'AFN':
                person.balance_afn += amount
            else:
                person.balance_usd += amount
            reversal_tx_type = LoanTransaction.TxType.GIVEN

        person.save(update_fields=['balance_afn', 'balance_usd', 'updated_at'])

        reversal = LoanTransaction.objects.create(
            person=person,
            tx_type=reversal_tx_type,
            currency=currency,
            amount=amount,
            payment_method=loan_tx.payment_method,
            banker=loan_tx.banker,
            balance_before_afn=balance_before_afn,
            balance_after_afn=person.balance_afn,
            balance_before_usd=balance_before_usd,
            balance_after_usd=person.balance_usd,
            transaction_date=timezone.now().date(),
            notes=notes or f'برگشت: {loan_tx.get_tx_type_display()} — {loan_tx.transaction_date}',
            created_by=user,
        )

        # Mark original as reversed
        loan_tx.is_reversed = True
        loan_tx.reversed_by = reversal
        loan_tx.save(update_fields=['is_reversed', 'reversed_by', 'updated_at'])

        # Reverse banker side effect if applicable
        if loan_tx.payment_method == LoanTransaction.PaymentMethod.SARAF and loan_tx.banker:
            if loan_tx.tx_type == LoanTransaction.TxType.GIVEN:
                # Original debited banker → reversal credits it back
                LoanService._saraf_credit(
                    loan_tx.banker, amount, currency,
                    timezone.now().date(), reversal, user,
                    note_prefix='برگشت قرضه داده‌شده'
                )
            else:
                # Original credited banker → reversal debits it back
                LoanService._saraf_debit(
                    loan_tx.banker, amount, currency,
                    timezone.now().date(), reversal, user,
                    note_prefix='برگشت بازپرداخت قرضه'
                )

        # Reverse dakkan side effect if applicable
        if loan_tx.payment_method == LoanTransaction.PaymentMethod.DAKKAN:
            # The reversal transaction gets a compensating dakkan entry
            # with the opposite outflow direction
            original_was_outflow = (loan_tx.tx_type == LoanTransaction.TxType.GIVEN)
            LoanService._dakkan_entry(
                reversal, amount, currency,
                timezone.now().date(),
                is_outflow=not original_was_outflow,  # flip direction
            )

        LoanService._log('delete', person, loan_tx, user)
        return reversal

    # ──────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _validate(amount, currency, payment_method, banker):
        if amount <= 0:
            raise ValidationError('مبلغ باید بیشتر از صفر باشد.')
        if currency not in ('AFN', 'USD'):
            raise ValidationError('واحد پول نامعتبر است.')
        if payment_method not in LoanTransaction.PaymentMethod.values:
            raise ValidationError('روش پرداخت نامعتبر است.')
        if payment_method == LoanTransaction.PaymentMethod.SARAF and not banker:
            raise ValidationError('برای روش صراف، انتخاب صراف اجباری است.')

    @staticmethod
    def _saraf_debit(banker, amount, currency, date, loan_tx, user, note_prefix='قرضه از طریق صراف'):
        """
        Lending money out via saraf: our banker balance DECREASES.
        Mirrors apply_expense_payment logic — RECEIVED tx on banker.
        """
        from apps.banker.services import BankerService
        from apps.banker.models import BankerTransaction

        banker_obj = type('_Ref', (), {'pk': banker.pk})()
        banker_obj.__class__ = banker.__class__
        banker_obj.pk = banker.pk

        # Re-fetch via select_for_update inside BankerService.record_transaction
        BankerService.record_transaction(
            banker=banker,
            tx_type=BankerTransaction.TxType.RECEIVED,   # debit our balance
            amount=amount,
            currency=currency,
            exchange_rate=Decimal('1'),
            transaction_date=date,
            notes=f'{note_prefix} — {loan_tx.person.name}',
            reference=f'LOAN-{loan_tx.pk}',
            user=user,
        )

    @staticmethod
    def _saraf_credit(banker, amount, currency, date, loan_tx, user, note_prefix='بازپرداخت قرضه از طریق صراف'):
        """
        Repayment received via saraf: our banker balance INCREASES.
        Mirrors apply_sale_payment logic — GIVEN tx on banker.
        """
        from apps.banker.services import BankerService
        from apps.banker.models import BankerTransaction

        BankerService.record_transaction(
            banker=banker,
            tx_type=BankerTransaction.TxType.GIVEN,      # credit our balance
            amount=amount,
            currency=currency,
            exchange_rate=Decimal('1'),
            transaction_date=date,
            notes=f'{note_prefix} — {loan_tx.person.name}',
            reference=f'LOAN-{loan_tx.pk}',
            user=user,
        )

    @staticmethod
    def _dakkan_entry(loan_tx, amount, currency, date, is_outflow: bool):
        """
        Create a LoanDakkhanEntry so CapitalService.get_shop_income can
        include this movement in its net_afn / net_usd calculation.
        """
        LoanDakkhanEntry.objects.create(
            loan_transaction=loan_tx,
            amount=amount,
            currency=currency,
            is_outflow=is_outflow,
            entry_date=date,
            notes=loan_tx.notes,
        )

    @staticmethod
    def _log(action, person, loan_tx, user):
        try:
            from apps.activity_logs.services import ActivityLogService
            sym = '$' if loan_tx.currency == 'USD' else '؋'
            direction = 'داده شده به' if loan_tx.tx_type == 'given' else 'دریافت شده از'
            ActivityLogService.log(
                action=action,
                module='loans',
                description=(
                    f'قرضه {loan_tx.amount:,.2f} {sym} '
                    f'{direction} «{person.name}» '
                    f'({loan_tx.get_payment_method_display()})'
                ),
                user=user,
                model_name='LoanTransaction',
                object_id=str(loan_tx.pk),
            )
        except Exception:
            pass
