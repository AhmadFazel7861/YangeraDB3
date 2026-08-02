"""
BankerService — atomic transaction engine.
All calculations go through here.
"""
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.accounts import models

from .models import Banker, BankerTransaction

# Currencies that get converted into an AFN-equivalent via exchange_rate
# when they're not AFN themselves.
FOREIGN_CURRENCIES = ('USD', 'EUR', 'IRR')


class BankerService:

    @staticmethod
    @transaction.atomic
    def record_transaction(
        banker: Banker,
        tx_type: str,
        amount: Decimal,
        currency: str,
        exchange_rate: Decimal = Decimal('1'),
        transaction_date=None,
        notes: str = '',
        reference: str = '',
        user=None
    ) -> BankerTransaction:
        if amount <= 0:
            raise ValidationError('مبلغ باید بیشتر از صفر باشد.')
        if exchange_rate <= 0:
            raise ValidationError('نرخ تبدیل باید بیشتر از صفر باشد.')

        if transaction_date is None:
            transaction_date = timezone.now().date()

        banker = Banker.objects.select_for_update().get(pk=banker.pk)

        if currency == 'AFN':
            amount_afn = amount
        else:
            amount_afn = (
                amount * exchange_rate
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        sign = Decimal('1') if tx_type == BankerTransaction.TxType.GIVEN else Decimal('-1')
        if tx_type not in (BankerTransaction.TxType.GIVEN, BankerTransaction.TxType.RECEIVED):
            raise ValidationError('نوع تراکنش نامعتبر است.')

        if currency == 'AFN':
            banker.balance_afn += sign * amount
        elif currency in FOREIGN_CURRENCIES:
            banker.set_balance(currency, banker.get_balance(currency) + sign * amount)
            # Only update balance_afn if a real exchange rate was provided
            # (exchange_rate > 1 means the user explicitly gave an AFN equivalent)
            if exchange_rate > Decimal('1'):
                banker.balance_afn += sign * amount_afn
        else:
            raise ValidationError('واحد پول نامعتبر است.')

        update_fields = ['balance_afn', 'balance_usd', 'balance_eur', 'balance_irr', 'updated_at']
        banker.save(update_fields=update_fields)

        tx = BankerTransaction.objects.create(
            banker=banker,
            tx_type=tx_type,
            currency=currency,
            amount=amount,
            exchange_rate=exchange_rate,
            amount_afn=amount_afn,
            balance_after_afn=banker.balance_afn,
            balance_after_usd=banker.balance_usd,
            balance_after_eur=banker.balance_eur,
            balance_after_irr=banker.balance_irr,
            transaction_date=transaction_date,
            notes=notes,
            reference=reference,
            created_by=user,
        )

        try:
            from apps.activity_logs.services import ActivityLogService
            direction = 'داده شده به' if tx_type == 'given' else 'دریافت شده از'
            ActivityLogService.log(
                action='create',
                module='system',
                description=(
                    f'تراکنش صراف: {amount:,.4f} {currency} '
                    f'{direction} صراف «{banker.name}»'
                ),
                user=user,
                model_name='BankerTransaction',
                object_id=str(tx.pk),
            )
        except Exception:
            pass

        return tx

    @staticmethod
    @transaction.atomic
    def delete_transaction(tx: BankerTransaction, user=None):
        banker = Banker.objects.select_for_update().get(pk=tx.banker.pk)

        sign = Decimal('-1') if tx.tx_type == BankerTransaction.TxType.GIVEN else Decimal('1')

        if tx.currency == 'AFN':
            banker.balance_afn += sign * tx.amount
        elif tx.currency in FOREIGN_CURRENCIES:
            banker.set_balance(tx.currency, banker.get_balance(tx.currency) + sign * tx.amount)
            banker.balance_afn += sign * tx.amount_afn

        update_fields = ['balance_afn', 'balance_usd', 'balance_eur', 'balance_irr', 'updated_at']
        banker.save(update_fields=update_fields)

        tx.is_deleted = True
        tx.deleted_at = timezone.now()
        tx.save(update_fields=['is_deleted', 'deleted_at'])

        try:
            from apps.activity_logs.services import ActivityLogService
            ActivityLogService.log(
                action='delete',
                module='system',
                description=(
                    f'تراکنش صراف حذف شد: {tx.amount:,.4f} {tx.currency} '
                    f'— {tx.banker.name}'
                ),
                user=user,
                model_name='BankerTransaction',
                object_id=str(tx.pk),
            )
        except Exception:
            pass

    @staticmethod
    @transaction.atomic
    def recalculate_balance(banker: Banker):
        banker = Banker.objects.select_for_update().get(pk=banker.pk)

        txs = BankerTransaction.objects.filter(
            banker=banker,
            is_deleted=False,
        ).order_by('transaction_date', 'created_at')

        balance_afn = Decimal('0')
        balance_usd = Decimal('0')
        balance_eur = Decimal('0')
        balance_irr = Decimal('0')
        foreign_balances = {'USD': balance_usd, 'EUR': balance_eur, 'IRR': balance_irr}

        for tx in txs:
            sign = Decimal('1') if tx.tx_type == BankerTransaction.TxType.GIVEN else Decimal('-1')
            if tx.currency == 'AFN':
                balance_afn += sign * tx.amount
            elif tx.currency in FOREIGN_CURRENCIES:
                foreign_balances[tx.currency] += sign * tx.amount
                if tx.exchange_rate > Decimal('1'):
                    balance_afn += sign * tx.amount_afn

        banker.balance_afn = balance_afn
        banker.balance_usd = foreign_balances['USD']
        banker.balance_eur = foreign_balances['EUR']
        banker.balance_irr = foreign_balances['IRR']
        banker.save(update_fields=['balance_afn', 'balance_usd', 'balance_eur', 'balance_irr', 'updated_at'])
        return banker

    @staticmethod
    def get_dashboard_stats():
        from datetime import timedelta

        today = timezone.now().date()
        week_start = today - timedelta(days=7)
        month_start = today.replace(day=1)

        base_qs = BankerTransaction.objects.filter(is_deleted=False)

        total_given = base_qs.filter(
            tx_type='given', currency='AFN'
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

        total_received = base_qs.filter(
            tx_type='received', currency='AFN'
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

        today_txs = base_qs.filter(
            transaction_date=today
        ).aggregate(count=Count('id'), total=Sum('amount_afn'))

        week_txs = base_qs.filter(
            transaction_date__gte=week_start
        ).aggregate(count=Count('id'), total=Sum('amount_afn'))

        month_txs = base_qs.filter(
            transaction_date__gte=month_start
        ).aggregate(count=Count('id'), total=Sum('amount_afn'))

        active_bankers = Banker.objects.filter(
            is_active=True, is_deleted=False
        ).count()

        pending = Banker.objects.filter(
            is_deleted=False
        ).exclude(
            balance_afn=0, balance_usd=0, balance_eur=0, balance_irr=0
        ).count()

        daily_chart = []
        for i in range(13, -1, -1):
            d = today - timedelta(days=i)
            given = base_qs.filter(
                transaction_date=d, tx_type='given'
            ).aggregate(t=Sum('amount_afn'))['t'] or Decimal('0')
            received = base_qs.filter(
                transaction_date=d, tx_type='received'
            ).aggregate(t=Sum('amount_afn'))['t'] or Decimal('0')
            daily_chart.append({
                'date': str(d),
                'given': float(given),
                'received': float(received),
            })

        top_bankers = Banker.objects.filter(
            is_deleted=False
        ).annotate(
            volume=Sum(
                'transactions__amount_afn',
                filter=Q(transactions__is_deleted=False, transactions__currency='AFN')
            )
        ).order_by('-volume')[:5]

        return {
            'total_given': total_given,
            'total_received': total_received,
            'net_balance': total_given - total_received,
            'today_count': today_txs['count'] or 0,
            'today_total': today_txs['total'] or Decimal('0'),
            'week_count': week_txs['count'] or 0,
            'week_total': week_txs['total'] or Decimal('0'),
            'month_count': month_txs['count'] or 0,
            'month_total': month_txs['total'] or Decimal('0'),
            'active_bankers': active_bankers,
            'pending_bankers': pending,
            'daily_chart': daily_chart,
            'top_bankers': top_bankers,
        }

    @staticmethod
    def get_ledger(banker: Banker, date_from=None, date_to=None):
        qs = BankerTransaction.objects.filter(
            banker=banker,
            is_deleted=False,
        )
        if date_from:
            qs = qs.filter(transaction_date__gte=date_from)
        if date_to:
            qs = qs.filter(transaction_date__lte=date_to)

        txs = qs.order_by('transaction_date', 'created_at')

        entries = []
        running_afn = Decimal('0')
        running_usd = Decimal('0')
        total_debit_afn  = Decimal('0')
        total_credit_afn = Decimal('0')
        total_debit_usd  = Decimal('0')
        total_credit_usd = Decimal('0')

        for tx in txs:
            if tx.tx_type == 'given':
                debit_afn  = tx.amount_afn
                credit_afn = Decimal('0')
                debit_usd  = tx.amount if tx.currency == 'USD' else Decimal('0')
                credit_usd = Decimal('0')
                # FIX: only accumulate AFN running total / totals for actual
                # AFN transactions. Previously this used tx.amount_afn
                # unconditionally, and since USD payments set amount_afn =
                # amount (no conversion), USD amounts were leaking into the
                # AFN running balance and totals.
                if tx.currency == 'AFN':
                    running_afn += tx.amount
                    total_debit_afn += tx.amount_afn
                running_usd += (tx.amount if tx.currency == 'USD' else Decimal('0'))
                total_debit_usd  += (tx.amount if tx.currency == 'USD' else Decimal('0'))
            else:
                debit_afn  = Decimal('0')
                credit_afn = tx.amount if tx.currency == 'AFN' else tx.amount_afn
                debit_usd  = Decimal('0')
                credit_usd = tx.amount if tx.currency == 'USD' else Decimal('0')
                # FIX: same correction as above, for the 'received' branch.
                if tx.currency == 'AFN':
                    running_afn -= tx.amount
                    total_credit_afn += tx.amount_afn
                running_usd -= (tx.amount if tx.currency == 'USD' else Decimal('0'))
                total_credit_usd += (tx.amount if tx.currency == 'USD' else Decimal('0'))

            entries.append({
                'tx': tx,
                'debit_afn': debit_afn if tx.currency == 'AFN' else Decimal('0'),
                'credit_afn': credit_afn if tx.currency == 'AFN' else Decimal('0'),
                'debit_usd': debit_usd,
                'credit_usd': credit_usd,
                'running_afn': running_afn if tx.currency == 'AFN' else Decimal('0'),
                'running_usd': running_usd if tx.currency == 'USD' else Decimal('0'),
            })

        return {
            'entries': entries,
            'total_debit_afn': total_debit_afn,
            'total_credit_afn': total_credit_afn,
            'total_debit_usd': total_debit_usd,
            'total_credit_usd': total_credit_usd,
            'closing_afn': total_debit_afn - total_credit_afn,
            'closing_usd': total_debit_usd - total_credit_usd,
        }

    @staticmethod
    def get_report(date_from=None, date_to=None, banker_id=None, currency=None):
        qs = BankerTransaction.objects.filter(is_deleted=False)

        if date_from:
            qs = qs.filter(transaction_date__gte=date_from)
        if date_to:
            qs = qs.filter(transaction_date__lte=date_to)
        if banker_id:
            qs = qs.filter(banker_id=banker_id)
        if currency:
            qs = qs.filter(currency=currency)

        qs = qs.select_related('banker', 'created_by').order_by(
            '-transaction_date', '-created_at'
        )

        def currency_totals(code):
            given = qs.filter(
                tx_type='given', currency=code
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
            received = qs.filter(
                tx_type='received', currency=code
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
            return given, received

        total_given_afn, total_received_afn = currency_totals('AFN')
        total_given_usd, total_received_usd = currency_totals('USD')
        total_given_eur, total_received_eur = currency_totals('EUR')
        total_given_irr, total_received_irr = currency_totals('IRR')

        count = qs.aggregate(c=Count('id'))['c'] or 0

        totals = {
            'count': count,
            'total_given_afn': total_given_afn,
            'total_received_afn': total_received_afn,
            'total_given_usd': total_given_usd,
            'total_received_usd': total_received_usd,
            'total_given_eur': total_given_eur,
            'total_received_eur': total_received_eur,
            'total_given_irr': total_given_irr,
            'total_received_irr': total_received_irr,
        }

        return {
            'transactions': qs,
            'totals': totals,
        }

    # ------------------------------------------------------------------
    # Purchase integration (صراف as a purchase payment method)
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def apply_purchase_payment(
        banker: Banker,
        amount: Decimal,
        currency: str,
        purchase_invoice,
        transaction_date=None,
        user=None,
    ) -> BankerTransaction:
        """
        Pay a purchase invoice using a صراف account.

        We're drawing on credit we have with the banker (or going into
        debt if balance is insufficient) to pay the supplier. This is
        recorded as a 'received' transaction — it reduces
        balance_afn/balance_usd by `amount`:
          - If balance was >= amount: balance decreases but stays >= 0
            (we used up some of our credit with the banker).
          - If balance was < amount: balance goes negative
            (we now owe the banker the shortfall — debt to صراف).

        For USD: exchange_rate is fixed at 1 (no AFN conversion, per
        invoice currency policy), so amount_afn == amount and
        balance_afn is NOT touched for USD purchase payments.
        """
        if amount <= 0:
            raise ValidationError('مبلغ پرداخت باید بیشتر از صفر باشد.')
        if currency not in ('AFN', 'USD'):
            raise ValidationError('واحد پول نامعتبر است.')

        if transaction_date is None:
            transaction_date = timezone.now().date()

        banker = Banker.objects.select_for_update().get(pk=banker.pk)

        if currency == 'AFN':
            banker.balance_afn -= amount
            amount_afn = amount
        else:
            banker.balance_usd -= amount
            amount_afn = amount  # no conversion — USD invoice is self-contained

        banker.save(update_fields=['balance_afn', 'balance_usd', 'updated_at'])

        tx = BankerTransaction.objects.create(
            banker=banker,
            tx_type=BankerTransaction.TxType.RECEIVED,
            currency=currency,
            amount=amount,
            exchange_rate=Decimal('1'),
            amount_afn=amount_afn,
            balance_after_afn=banker.balance_afn,
            balance_after_usd=banker.balance_usd,
            transaction_date=transaction_date,
            notes=f'پرداخت فاکتور خرید {purchase_invoice.invoice_number} از طریق صراف',
            reference=purchase_invoice.invoice_number,
            created_by=user,
        )

        try:
            from apps.activity_logs.services import ActivityLogService
            ActivityLogService.log(
                action='create',
                module='purchases',
                description=(
                    f'پرداخت {amount:,.2f} {currency} برای فاکتور خرید '
                    f'{purchase_invoice.invoice_number} از طریق صراف «{banker.name}»'
                ),
                user=user,
                model_name='BankerTransaction',
                object_id=str(tx.pk),
            )
        except Exception:
            pass

        return tx

    @staticmethod
    @transaction.atomic
    def reverse_purchase_payment(
        banker: Banker,
        amount: Decimal,
        currency: str,
        purchase_invoice,
        user=None,
    ) -> BankerTransaction:
        """
        Reverse a previous apply_purchase_payment (e.g. when the
        purchase invoice is cancelled) — restores the banker's
        balance by `amount`.
        """
        if amount <= 0:
            raise ValidationError('مبلغ بازگشت باید بیشتر از صفر باشد.')
        if currency not in ('AFN', 'USD'):
            raise ValidationError('واحد پول نامعتبر است.')

        banker = Banker.objects.select_for_update().get(pk=banker.pk)

        if currency == 'AFN':
            banker.balance_afn += amount
            amount_afn = amount
        else:
            banker.balance_usd += amount
            amount_afn = amount

        banker.save(update_fields=['balance_afn', 'balance_usd', 'updated_at'])

        tx = BankerTransaction.objects.create(
            banker=banker,
            tx_type=BankerTransaction.TxType.GIVEN,
            currency=currency,
            amount=amount,
            exchange_rate=Decimal('1'),
            amount_afn=amount_afn,
            balance_after_afn=banker.balance_afn,
            balance_after_usd=banker.balance_usd,
            transaction_date=timezone.now().date(),
            notes=f'برگشت پرداخت فاکتور خرید {purchase_invoice.invoice_number} (لغو فاکتور)',
            reference=purchase_invoice.invoice_number,
            created_by=user,
        )

        try:
            from apps.activity_logs.services import ActivityLogService
            ActivityLogService.log(
                action='delete',
                module='purchases',
                description=(
                    f'برگشت پرداخت {amount:,.2f} {currency} فاکتور خرید '
                    f'{purchase_invoice.invoice_number} از صراف «{banker.name}»'
                ),
                user=user,
                model_name='BankerTransaction',
                object_id=str(tx.pk),
            )
        except Exception:
            pass

        return tx
    
    @staticmethod
    @transaction.atomic
    def apply_sale_payment(
        banker: Banker,
        amount: Decimal,
        currency: str,
        sale_invoice,
        transaction_date=None,
        user=None,
    ) -> BankerTransaction:
        """
        Customer pays via صراف — credits our banker balance.
        The customer pays the banker, banker owes us → balance increases.
        Recorded as 'given' (increases balance_afn/balance_usd).
        """
        if amount <= 0:
            raise ValidationError('مبلغ پرداخت باید بیشتر از صفر باشد.')
        if currency not in ('AFN', 'USD'):
            raise ValidationError('واحد پول نامعتبر است.')

        if transaction_date is None:
            transaction_date = timezone.now().date()

        banker = Banker.objects.select_for_update().get(pk=banker.pk)

        if currency == 'AFN':
            banker.balance_afn += amount
            amount_afn = amount
        else:
            banker.balance_usd += amount
            amount_afn = amount  # no conversion

        banker.save(update_fields=['balance_afn', 'balance_usd', 'updated_at'])

        tx = BankerTransaction.objects.create(
            banker=banker,
            tx_type=BankerTransaction.TxType.GIVEN,
            currency=currency,
            amount=amount,
            exchange_rate=Decimal('1'),
            amount_afn=amount_afn,
            balance_after_afn=banker.balance_afn,
            balance_after_usd=banker.balance_usd,
            transaction_date=transaction_date,
            notes=f'دریافت فاکتور فروش {sale_invoice.invoice_number} از طریق صراف',
            reference=sale_invoice.invoice_number,
            created_by=user,
        )

        try:
            from apps.activity_logs.services import ActivityLogService
            ActivityLogService.log(
                action='create',
                module='sales',
                description=(
                    f'دریافت {amount:,.2f} {currency} برای فاکتور فروش '
                    f'{sale_invoice.invoice_number} از طریق صراف «{banker.name}»'
                ),
                user=user,
                model_name='BankerTransaction',
                object_id=str(tx.pk),
            )
        except Exception:
            pass

        return tx

    @staticmethod
    @transaction.atomic
    def reverse_sale_payment(
        banker: Banker,
        amount: Decimal,
        currency: str,
        sale_invoice,
        user=None,
    ) -> BankerTransaction:
        """
        Reverse a sale payment via صراف (e.g. invoice cancelled/edited).
        Decreases banker balance by amount.
        """
        if amount <= 0:
            raise ValidationError('مبلغ بازگشت باید بیشتر از صفر باشد.')
        if currency not in ('AFN', 'USD'):
            raise ValidationError('واحد پول نامعتبر است.')

        banker = Banker.objects.select_for_update().get(pk=banker.pk)

        if currency == 'AFN':
            banker.balance_afn -= amount
            amount_afn = amount
        else:
            banker.balance_usd -= amount
            amount_afn = amount

        banker.save(update_fields=['balance_afn', 'balance_usd', 'updated_at'])

        tx = BankerTransaction.objects.create(
            banker=banker,
            tx_type=BankerTransaction.TxType.RECEIVED,
            currency=currency,
            amount=amount,
            exchange_rate=Decimal('1'),
            amount_afn=amount_afn,
            balance_after_afn=banker.balance_afn,
            balance_after_usd=banker.balance_usd,
            transaction_date=timezone.now().date(),
            notes=f'برگشت دریافت فاکتور فروش {sale_invoice.invoice_number} (لغو/ویرایش)',
            reference=sale_invoice.invoice_number,
            created_by=user,
        )

        try:
            from apps.activity_logs.services import ActivityLogService
            ActivityLogService.log(
                action='delete',
                module='sales',
                description=(
                    f'برگشت دریافت {amount:,.2f} {currency} فاکتور فروش '
                    f'{sale_invoice.invoice_number} از صراف «{banker.name}»'
                ),
                user=user,
                model_name='BankerTransaction',
                object_id=str(tx.pk),
            )
        except Exception:
            pass

        return tx
    
    @staticmethod
    @transaction.atomic
    def apply_expense_payment(banker, amount, currency, exchange_rate=Decimal('1'),
                          expense=None, transaction_date=None, user=None):
        """Expense paid via saraf — reduces our balance (we used saraf credit)."""
        from decimal import ROUND_HALF_UP
        if transaction_date is None:
            transaction_date = timezone.now().date()
        banker = Banker.objects.select_for_update().get(pk=banker.pk)
        if currency == 'AFN':
            banker.balance_afn -= amount
            amount_afn = amount
        else:
            banker.balance_usd -= amount
            amount_afn = (amount * exchange_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            banker.balance_afn -= amount_afn
        banker.save(update_fields=['balance_afn', 'balance_usd', 'updated_at'])
        return BankerTransaction.objects.create(
            banker=banker,
            tx_type=BankerTransaction.TxType.RECEIVED,
            currency=currency,
            amount=amount,
            exchange_rate=exchange_rate,
            amount_afn=amount_afn,
            balance_after_afn=banker.balance_afn,
            balance_after_usd=banker.balance_usd,
            transaction_date=transaction_date,
            notes=f'پرداخت مصرف از طریق صراف: {expense.title if expense else ""}',
            reference=str(expense.pk) if expense else '',
            created_by=user,
        )
    
    # ------------------------------------------------------------------
    # Saraf → Saraf transfer
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def transfer_between_bankers(
        from_banker: Banker,
        to_banker: Banker,
        amount: Decimal,
        currency: str,
        transaction_date=None,
        notes: str = '',
        reference: str = '',
        user=None,
    ):
        """
        Move money from one صراف to another, same currency only.

        Each currency is tracked completely independently:
          - AFN balance is only ever compared against AFN amounts
          - USD balance is only ever compared against USD amounts
          - EUR balance is only ever compared against EUR amounts
          - IRR balance is only ever compared against IRR amounts
        They are never summed or mixed together.

        Raises ValidationError if from_banker doesn't have enough balance
        in that SPECIFIC currency to cover the transfer.
        """
        import uuid as uuid_lib

        if from_banker.pk == to_banker.pk:
            raise ValidationError('صراف مبدا و مقصد نمی‌توانند یکسان باشند.')
        if amount <= 0:
            raise ValidationError('مبلغ باید بیشتر از صفر باشد.')
        if currency not in BankerTransaction.Currency.values:
            raise ValidationError('واحد پول نامعتبر است.')

        if transaction_date is None:
            transaction_date = timezone.now().date()

        # Lock both bankers (consistent ordering avoids deadlocks)
        pks = sorted([str(from_banker.pk), str(to_banker.pk)])
        locked = {
            str(b.pk): b for b in
            Banker.objects.select_for_update().filter(pk__in=pks)
        }
        from_banker = locked[str(from_banker.pk)]
        to_banker = locked[str(to_banker.pk)]

        # ── THE INSUFFICIENT BALANCE CHECK ──
        # get_balance(currency) reads ONLY the matching field:
        #   AFN -> balance_afn, USD -> balance_usd,
        #   EUR -> balance_eur, IRR -> balance_irr
        # so an AFN amount is only ever compared to the AFN balance, etc.
        current_balance = from_banker.get_balance(currency)
        if current_balance < amount:
            currency_label = dict(BankerTransaction.Currency.choices).get(currency, currency)
            raise ValidationError(
                f'موجودی ناکافی! مانده صراف «{from_banker.name}» در {currency_label} '
                f'برابر {current_balance:,.4f} است، اما {amount:,.4f} درخواست شده است.'
            )

        transfer_ref = reference or f'TRANSFER:{uuid_lib.uuid4().hex[:10]}'

        if currency == 'AFN':
            amount_afn = amount
            from_banker.balance_afn -= amount
            to_banker.balance_afn += amount
        else:
            amount_afn = Decimal('0')
            from_banker.set_balance(currency, from_banker.get_balance(currency) - amount)
            to_banker.set_balance(currency, to_banker.get_balance(currency) + amount)

        update_fields = ['balance_afn', 'balance_usd', 'balance_eur', 'balance_irr', 'updated_at']
        from_banker.save(update_fields=update_fields)
        to_banker.save(update_fields=update_fields)

        transfer_note_out = f'انتقال به صراف «{to_banker.name}» — {notes}'.strip(' —')
        transfer_note_in = f'انتقال از صراف «{from_banker.name}» — {notes}'.strip(' —')

        tx_out = BankerTransaction.objects.create(
            banker=from_banker,
            tx_type=BankerTransaction.TxType.RECEIVED,
            currency=currency,
            amount=amount,
            exchange_rate=Decimal('1'),
            amount_afn=amount_afn,
            balance_after_afn=from_banker.balance_afn,
            balance_after_usd=from_banker.balance_usd,
            balance_after_eur=from_banker.balance_eur,
            balance_after_irr=from_banker.balance_irr,
            transaction_date=transaction_date,
            notes=transfer_note_out,
            reference=transfer_ref,
            created_by=user,
        )

        tx_in = BankerTransaction.objects.create(
            banker=to_banker,
            tx_type=BankerTransaction.TxType.GIVEN,
            currency=currency,
            amount=amount,
            exchange_rate=Decimal('1'),
            amount_afn=amount_afn,
            balance_after_afn=to_banker.balance_afn,
            balance_after_usd=to_banker.balance_usd,
            balance_after_eur=to_banker.balance_eur,
            balance_after_irr=to_banker.balance_irr,
            transaction_date=transaction_date,
            notes=transfer_note_in,
            reference=transfer_ref,
            created_by=user,
        )

        try:
            from apps.activity_logs.services import ActivityLogService
            ActivityLogService.log(
                action='create',
                module='system',
                description=(
                    f'انتقال {amount:,.4f} {currency} از صراف «{from_banker.name}» '
                    f'به صراف «{to_banker.name}»'
                ),
                user=user,
                model_name='BankerTransaction',
                object_id=str(tx_out.pk),
            )
        except Exception:
            pass

        return tx_out, tx_in