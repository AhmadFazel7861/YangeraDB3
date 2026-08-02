"""
Capital Service — aggregates data for the سرمایه دکان (Shop Capital) page.

Sections:
  1. دخل دکان       — customer payments received (cash/credit/bank/mobile only — not saraf)
  2. موجودی گدام    — current warehouse stock value (FIFO cost)
  3. مصارف          — expenses summary
  4. بیلانس صراف    — banker account balances
  5. انتقال به صراف — transfer دخل دکان cash to banker
  6. خالص سرمایه    — net business capital (customer debts + stock + banker + dakkan − supplier debts)
"""
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from django.core.exceptions import ValidationError


class CapitalService:

    # ──────────────────────────────────────────────────────────────
    # 1. دخل دکان — Customer payments received
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _payment_qs(date_from=None, date_to=None, currency=None):
        """
        Returns a CustomerTransaction queryset for PAYMENT type
        where payment_method = 'dakkan' only.
        Excludes payments tied to deleted invoices.
        """
        from apps.customers.models import CustomerTransaction

        qs = CustomerTransaction.objects.filter(
            tx_type=CustomerTransaction.TxType.PAYMENT,
            is_reversed=False,
            payment_method='dakkan',
        ).exclude(
            invoice__is_deleted=True,
        ).select_related('customer', 'invoice', 'invoice__customer')

        if currency:
            qs = qs.filter(currency=currency)
        if date_from:
            qs = qs.filter(transaction_date__gte=date_from)
        if date_to:
            qs = qs.filter(transaction_date__lte=date_to)

        return qs.order_by('-transaction_date', '-created_at')

    @staticmethod
    def _dakkan_expenses(date_from=None, date_to=None):
        """
        Returns (expenses_afn, expenses_usd): the sum of approved Expense
        records paid via payment_method='dakkan' in the given date range.
        These are subtracted from دخل دکان net balance, since paying an
        expense out of the shop till reduces the cash actually in hand.
        """
        from apps.expenses.models import Expense

        qs = Expense.objects.filter(
            is_deleted=False,
            status=Expense.Status.APPROVED,
            payment_method='dakkan',
        )
        if date_from:
            qs = qs.filter(expense_date__gte=date_from)
        if date_to:
            qs = qs.filter(expense_date__lte=date_to)

        expenses_afn = qs.filter(currency='AFN').aggregate(
            t=Sum('amount'))['t'] or Decimal('0')
        expenses_usd = qs.filter(currency='USD').aggregate(
            t=Sum('amount'))['t'] or Decimal('0')

        return expenses_afn, expenses_usd

    @staticmethod
    def _loan_dakkan_movements(date_from=None, date_to=None):
        """
        Returns (outflows_afn, outflows_usd, inflows_afn, inflows_usd):

        Loans given via دخل دکان  → is_outflow=True  → subtract from net
          (cash physically left the till when we lent it out)
        Repayments received via دخل دکان → is_outflow=False → add back to net
          (cash physically returned to the till when borrower repaid)

        Reversed loan transactions automatically create a compensating
        LoanDakkhanEntry with the opposite is_outflow value, so they
        cancel out here without any special handling.
        """
        try:
            from apps.loans.models import LoanDakkhanEntry
        except ImportError:
            # loans app not installed — safe no-op
            return Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0')

        qs = LoanDakkhanEntry.objects.filter(is_deleted=False)
        if date_from:
            qs = qs.filter(entry_date__gte=date_from)
        if date_to:
            qs = qs.filter(entry_date__lte=date_to)

        outflows_afn = qs.filter(
            is_outflow=True, currency='AFN'
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

        outflows_usd = qs.filter(
            is_outflow=True, currency='USD'
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

        inflows_afn = qs.filter(
            is_outflow=False, currency='AFN'
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

        inflows_usd = qs.filter(
            is_outflow=False, currency='USD'
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

        return outflows_afn, outflows_usd, inflows_afn, inflows_usd

    @staticmethod
    def get_shop_income(date_from=None, date_to=None, currency=None):
        """
        Returns:
          payments            — queryset for the table (all received payments)
          total_afn           — gross AFN received (what customers paid)
          total_usd           — gross USD received (what customers paid)
          transferred_afn     — how much AFN was sent to banker
          transferred_usd     — how much USD was sent to banker
          dakkan_expenses_afn — AFN expenses paid out of دخل دکان
          dakkan_expenses_usd — USD expenses paid out of دخل دکان
          loan_outflows_afn   — AFN loans given out of دخل دکان
          loan_outflows_usd   — USD loans given out of دخل دکان
          loan_inflows_afn    — AFN loan repayments received into دخل دکان
          loan_inflows_usd    — USD loan repayments received into دخل دکان
          net_afn             — AFN still in hand
          net_usd             — USD still in hand
        """
        from .models import ShopIncomeTransfer

        qs_afn = CapitalService._payment_qs(date_from, date_to, currency='AFN')
        qs_usd = CapitalService._payment_qs(date_from, date_to, currency='USD')

        gross_afn = qs_afn.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        gross_usd = qs_usd.aggregate(t=Sum('amount'))['t'] or Decimal('0')

        # Transfers sent to banker in same date range
        transfer_qs = ShopIncomeTransfer.objects.filter(is_deleted=False)
        if date_from:
            transfer_qs = transfer_qs.filter(transfer_date__gte=date_from)
        if date_to:
            transfer_qs = transfer_qs.filter(transfer_date__lte=date_to)

        transferred_afn = transfer_qs.filter(currency='AFN').aggregate(
            t=Sum('amount'))['t'] or Decimal('0')
        transferred_usd = transfer_qs.filter(currency='USD').aggregate(
            t=Sum('amount'))['t'] or Decimal('0')

        # Expenses paid directly from دخل دکان
        dakkan_expenses_afn, dakkan_expenses_usd = CapitalService._dakkan_expenses(
            date_from, date_to
        )

        # ── Loan movements via دخل دکان ──
        # Loans given out reduce the till; repayments received add back to it.
        (
            loan_outflows_afn, loan_outflows_usd,
            loan_inflows_afn,  loan_inflows_usd,
        ) = CapitalService._loan_dakkan_movements(date_from, date_to)

        # Net = gross received
        #       − sent to banker
        #       − expenses paid from till
        #       − loans given from till
        #       + loan repayments received into till
        net_afn = max(
            Decimal('0'),
            gross_afn
            - transferred_afn
            - dakkan_expenses_afn
            - loan_outflows_afn
            + loan_inflows_afn
        )
        net_usd = max(
            Decimal('0'),
            gross_usd
            - transferred_usd
            - dakkan_expenses_usd
            - loan_outflows_usd
            + loan_inflows_usd
        )

        if currency == 'AFN':
            payments  = qs_afn
            total_afn = gross_afn
            total_usd = Decimal('0')
        elif currency == 'USD':
            payments  = qs_usd
            total_afn = Decimal('0')
            total_usd = gross_usd
        else:
            qs_both  = CapitalService._payment_qs(date_from, date_to, currency=None)
            payments  = qs_both
            total_afn = gross_afn
            total_usd = gross_usd

        return {
            'payments':            payments,
            'total_afn':           total_afn,
            'total_usd':           total_usd,
            'gross_afn':           gross_afn,
            'gross_usd':           gross_usd,
            'transferred_afn':     transferred_afn,
            'transferred_usd':     transferred_usd,
            'dakkan_expenses_afn': dakkan_expenses_afn,
            'dakkan_expenses_usd': dakkan_expenses_usd,
            'loan_outflows_afn':   loan_outflows_afn,
            'loan_outflows_usd':   loan_outflows_usd,
            'loan_inflows_afn':    loan_inflows_afn,
            'loan_inflows_usd':    loan_inflows_usd,
            'net_afn':             net_afn,
            'net_usd':             net_usd,
        }

    @staticmethod
    def get_this_month_income():
        today = timezone.now().date()
        month_start = today.replace(day=1)
        return CapitalService.get_shop_income(date_from=month_start)

    # ──────────────────────────────────────────────────────────────
    # 2. موجودی گدام — Warehouse stock value
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_stock_value():
        """
        Returns total warehouse stock value across all warehouses.
        Uses StockBatch.remaining_quantity × unit_cost (FIFO cost).
        Also returns per-warehouse breakdown.
        """
        from apps.warehouse.models import StockBatch, Warehouse
        from django.db.models import F, ExpressionWrapper, DecimalField

        result_afn = StockBatch.objects.filter(
            remaining_quantity__gt=0,
            is_deleted=False,
        ).aggregate(
            total=Sum(
                ExpressionWrapper(
                    F('remaining_quantity') * F('unit_cost'),
                    output_field=DecimalField(max_digits=20, decimal_places=2)
                )
            )
        )
        total_afn = result_afn['total'] or Decimal('0')

        result_usd = StockBatch.objects.filter(
            remaining_quantity__gt=0,
            is_deleted=False,
            unit_cost_usd__gt=0,
        ).aggregate(
            total=Sum(
                ExpressionWrapper(
                    F('remaining_quantity') * F('unit_cost_usd'),
                    output_field=DecimalField(max_digits=20, decimal_places=4)
                )
            )
        )
        total_usd = result_usd['total'] or Decimal('0')

        warehouses = Warehouse.objects.filter(is_active=True, is_deleted=False)
        warehouse_breakdown = []
        for wh in warehouses:
            warehouse_breakdown.append({
                'warehouse':   wh,
                'value_afn':   wh.total_value,
                'value_usd':   wh.total_value_usd,
                'batch_count': wh.total_batches,
            })

        from apps.inventory.models import Product
        product_stock = StockBatch.objects.filter(
            remaining_quantity__gt=0,
            is_deleted=False,
        ).values(
            'product__name', 'product__unit'
        ).annotate(
            total_qty=Sum('remaining_quantity'),
            total_val_afn=Sum(
                ExpressionWrapper(
                    F('remaining_quantity') * F('unit_cost'),
                    output_field=DecimalField(max_digits=20, decimal_places=2)
                )
            ),
            total_val_usd=Sum(
                ExpressionWrapper(
                    F('remaining_quantity') * F('unit_cost_usd'),
                    output_field=DecimalField(max_digits=20, decimal_places=4)
                )
            ),
        ).order_by('-total_val_afn')[:20]

        return {
            'total_afn':           total_afn,
            'total_usd':           total_usd,
            'warehouse_breakdown': warehouse_breakdown,
            'product_stock':       product_stock,
        }

    # ──────────────────────────────────────────────────────────────
    # 3. مصارف — Expenses
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_expenses_summary(date_from=None, date_to=None):
        from apps.expenses.models import Expense
        today = timezone.now().date()
        month_start = today.replace(day=1)

        base_qs = Expense.objects.filter(
            is_deleted=False,
            status=Expense.Status.APPROVED,
        )

        all_afn = base_qs.filter(currency='AFN').aggregate(
            t=Sum('amount'))['t'] or Decimal('0')
        all_usd = base_qs.filter(currency='USD').aggregate(
            t=Sum('amount'))['t'] or Decimal('0')

        month_afn = base_qs.filter(
            currency='AFN', expense_date__gte=month_start
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        month_usd = base_qs.filter(
            currency='USD', expense_date__gte=month_start
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

        range_afn = Decimal('0')
        range_usd = Decimal('0')
        if date_from or date_to:
            range_qs = base_qs
            if date_from:
                range_qs = range_qs.filter(expense_date__gte=date_from)
            if date_to:
                range_qs = range_qs.filter(expense_date__lte=date_to)
            range_afn = range_qs.filter(currency='AFN').aggregate(
                t=Sum('amount'))['t'] or Decimal('0')
            range_usd = range_qs.filter(currency='USD').aggregate(
                t=Sum('amount'))['t'] or Decimal('0')

        recent_qs = base_qs.select_related('category').order_by('-expense_date', '-created_at')
        if date_from:
            recent_qs = recent_qs.filter(expense_date__gte=date_from)
        if date_to:
            recent_qs = recent_qs.filter(expense_date__lte=date_to)

        return {
            'all_afn':         all_afn,
            'all_usd':         all_usd,
            'month_afn':       month_afn,
            'month_usd':       month_usd,
            'range_afn':       range_afn,
            'range_usd':       range_usd,
            'recent_expenses': recent_qs[:50],
        }

    # ──────────────────────────────────────────────────────────────
    # 4. بیلانس صراف — Banker balances
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_banker_balances():
        from apps.banker.models import Banker
        bankers = Banker.objects.filter(
            is_active=True, is_deleted=False
        ).order_by('name')

        total_afn = sum(b.balance_afn for b in bankers)
        total_usd = sum(b.balance_usd for b in bankers)

        return {
            'bankers':   bankers,
            'total_afn': total_afn,
            'total_usd': total_usd,
        }

    # ──────────────────────────────────────────────────────────────
    # 5. انتقال به صراف — Transfer shop income to banker
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def transfer_to_banker(
        banker,
        amount: Decimal,
        currency: str,
        transfer_date,
        notes: str = '',
        user=None,
    ):
        from apps.banker.services import BankerService
        from apps.banker.models import BankerTransaction
        from .models import ShopIncomeTransfer

        if amount <= 0:
            raise ValidationError('مبلغ باید بیشتر از صفر باشد.')
        if currency not in ('AFN', 'USD'):
            raise ValidationError('واحد پول نامعتبر است.')

        transfer = ShopIncomeTransfer.objects.create(
            banker=banker,
            amount=amount,
            currency=currency,
            transfer_date=transfer_date,
            notes=notes,
            created_by=user,
        )

        BankerService.record_transaction(
            banker=banker,
            tx_type=BankerTransaction.TxType.GIVEN,
            amount=amount,
            currency=currency,
            exchange_rate=Decimal('1'),
            transaction_date=transfer_date,
            notes=f'انتقال دخل دکان — {notes}'.strip(' —'),
            reference=f'SHOP-TRANSFER-{transfer.pk}',
            user=user,
        )

        try:
            from apps.activity_logs.services import ActivityLogService
            sym = '$' if currency == 'USD' else '؋'
            ActivityLogService.log(
                action='create',
                module='capital',
                description=(
                    f'انتقال {amount:,.2f} {sym} از دخل دکان به صراف «{banker.name}»'
                ),
                user=user,
                model_name='ShopIncomeTransfer',
                object_id=str(transfer.pk),
            )
        except Exception:
            pass

        return transfer

    @staticmethod
    def get_transfers(date_from=None, date_to=None):
        from .models import ShopIncomeTransfer
        qs = ShopIncomeTransfer.objects.filter(
            is_deleted=False
        ).select_related('banker', 'created_by')
        if date_from:
            qs = qs.filter(transfer_date__gte=date_from)
        if date_to:
            qs = qs.filter(transfer_date__lte=date_to)
        return qs.order_by('-transfer_date', '-created_at')

    # ──────────────────────────────────────────────────────────────
    # 6. خالص سرمایه کل دکان — Net worth (same formula as خلاصه مالی)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_net_worth():
        """
        Mirrors the exact formula used in ReportService.get_financial_summary():

          net_worth = بدهی مشتریان (customer total_debt)
                    - بدهی به تامین‌کنندگان (supplier total_debt)
                    + دخل دکان (dakkan net cash, all-time)
                    + مانده صرافان (banker balances)
                    + ارزش موجودی انبار (stock value)

        Uses Customer.total_debt_usd and Supplier.total_debt_usd
        — the same aggregated fields the financial summary page uses.
        """
        from apps.customers.models import Customer
        from apps.suppliers.models import Supplier

        customer_debt_usd = Customer.objects.filter(
            is_deleted=False
        ).aggregate(t=Sum('total_debt_usd'))['t'] or Decimal('0')

        customer_debt_afn = Customer.objects.filter(
            is_deleted=False
        ).aggregate(t=Sum('total_debt'))['t'] or Decimal('0')

        supplier_debt_usd = Supplier.objects.filter(
            is_deleted=False
        ).aggregate(t=Sum('total_debt_usd'))['t'] or Decimal('0')

        supplier_debt_afn = Supplier.objects.filter(
            is_deleted=False
        ).aggregate(t=Sum('total_debt'))['t'] or Decimal('0')

        return {
            'customer_debt_usd': customer_debt_usd,
            'customer_debt_afn': customer_debt_afn,
            'supplier_debt_usd': supplier_debt_usd,
            'supplier_debt_afn': supplier_debt_afn,
        }