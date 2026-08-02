"""
ReportService — pulls data from all modules for reporting.
"""
import zoneinfo
from decimal import Decimal
from datetime import date, timedelta, datetime
from django.db.models import Sum, Count, Avg, F, Q
from django.db.models import ExpressionWrapper, DecimalField
from django.utils import timezone
from django.conf import settings


def _local_today():
    """Return today's date in the configured local timezone (e.g. Asia/Kabul)."""
    tz = zoneinfo.ZoneInfo(settings.TIME_ZONE)
    return timezone.now().astimezone(tz).date()


def _parse_date(value):
    """
    Safely convert a string like '2026-01-01' to a date object.
    Returns None if value is empty, None, or unparseable.
    """
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


class ReportService:

    # ══════════════════════════════════════════════════════════
    # DATE HELPERS
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def get_date_range(period: str, custom_from=None, custom_to=None):
        # Jalali-aware period boundaries. Uses the existing apps/core/jalali.py
        # helpers only — no new date library, no duplicated conversion logic.
        from apps.core.jalali import (
            to_jalali_str,
            jalali_month_range_str,
            jalali_str_to_gregorian,
        )

        today = _local_today()

        if period == 'today':
            return today, today

        elif period == 'yesterday':
            y = today - timedelta(days=1)
            return y, y

        elif period == 'this_week':
            # Jalali week runs Saturday..Friday.
            # Python's date.weekday(): Monday=0 ... Saturday=5, Sunday=6.
            days_since_saturday = (today.weekday() - 5) % 7
            start = today - timedelta(days=days_since_saturday)
            return start, today

        elif period == 'last_week':
            days_since_saturday = (today.weekday() - 5) % 7
            this_week_start = today - timedelta(days=days_since_saturday)
            start = this_week_start - timedelta(days=7)
            end = this_week_start - timedelta(days=1)
            return start, end

        elif period == 'this_month':
            jy, jm, _jd = (int(p) for p in to_jalali_str(today).split('/'))
            first_day_str, _last_day_str = jalali_month_range_str(jy, jm)
            start = jalali_str_to_gregorian(first_day_str)
            return start, today

        elif period == 'last_month':
            jy, jm, _jd = (int(p) for p in to_jalali_str(today).split('/'))
            if jm == 1:
                last_jy, last_jm = jy - 1, 12
            else:
                last_jy, last_jm = jy, jm - 1
            first_day_str, last_day_str = jalali_month_range_str(last_jy, last_jm)
            start = jalali_str_to_gregorian(first_day_str)
            end = jalali_str_to_gregorian(last_day_str)
            return start, end

        elif period == 'this_year':
            jy, _jm, _jd = (int(p) for p in to_jalali_str(today).split('/'))
            first_day_str, _last_day_str = jalali_month_range_str(jy, 1)
            start = jalali_str_to_gregorian(first_day_str)
            return start, today

        elif period == 'custom':
            df = _parse_date(custom_from)
            dt = _parse_date(custom_to)
            # fallback to today if either date is missing/invalid
            if not df:
                df = today
            if not dt:
                dt = today
            return df, dt

        return today, today

    # ══════════════════════════════════════════════════════════
    # SALES REPORT
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def get_sales_report(date_from, date_to):
        from apps.sales.models import Invoice, InvoiceItem

        invoices = Invoice.objects.filter(
            is_deleted=False,
            invoice_date__gte=date_from,
            invoice_date__lte=date_to,
            status__in=['confirmed', 'partial', 'paid'],
        ).select_related('customer', 'warehouse')

        afn_invoices = invoices.filter(currency='AFN')
        usd_invoices = invoices.filter(currency='USD')

        # AFN totals
        totals = afn_invoices.aggregate(
            total_sales=Sum('total_amount'),
            total_cost=Sum('total_cost'),
            total_paid=Sum('paid_amount'),
            total_remaining=Sum('remaining_amount'),
            total_discount=Sum('discount_amount'),
            invoice_count=Count('id'),
        )

        # USD totals
        totals_usd = usd_invoices.aggregate(
            total_sales=Sum('total_amount'),
            total_cost=Sum('total_cost'),
            total_paid=Sum('paid_amount'),
            total_remaining=Sum('remaining_amount'),
            total_discount=Sum('discount_amount'),
            invoice_count=Count('id'),
        )

        gross_profit = (
            (totals['total_sales'] or Decimal('0')) -
            (totals['total_cost'] or Decimal('0'))
        )
        gross_profit_usd = (
            (totals_usd['total_sales'] or Decimal('0')) -
            (totals_usd['total_cost'] or Decimal('0'))
        )

        # Daily breakdown (AFN)
        daily = afn_invoices.values('invoice_date').annotate(
            sales=Sum('total_amount'),
            cost=Sum('total_cost'),
            count=Count('id'),
        ).order_by('invoice_date')

        # Daily breakdown (USD)
        daily_usd = usd_invoices.values('invoice_date').annotate(
            sales=Sum('total_amount'),
            cost=Sum('total_cost'),
            count=Count('id'),
        ).order_by('invoice_date')

        top_products = InvoiceItem.objects.filter(
            invoice__is_deleted=False,
            invoice__invoice_date__gte=date_from,
            invoice__invoice_date__lte=date_to,
            invoice__status__in=['confirmed', 'partial', 'paid'],
        ).values(
            'product__name', 'product__code'
        ).annotate(
            total_qty=Sum('quantity'),
            total_revenue=Sum('line_total'),
            total_cost=Sum('total_cost_fifo'),
        ).order_by('-total_revenue')[:10]

        # Top customers (AFN)
        top_customers = afn_invoices.values(
            'customer__name', 'customer__code'
        ).annotate(
            total=Sum('total_amount'),
            count=Count('id'),
        ).order_by('-total')[:10]

        # Top customers (USD)
        top_customers_usd = usd_invoices.values(
            'customer__name', 'customer__code'
        ).annotate(
            total=Sum('total_amount'),
            count=Count('id'),
        ).order_by('-total')[:10]

        return {
            'invoices': invoices.order_by('-invoice_date'),
            'totals': totals,
            'totals_usd': totals_usd,
            'gross_profit': gross_profit,
            'gross_profit_usd': gross_profit_usd,
            'profit_margin': (
                gross_profit / totals['total_sales'] * 100
                if totals['total_sales'] else Decimal('0')
            ),
            'profit_margin_usd': (
                gross_profit_usd / totals_usd['total_sales'] * 100
                if totals_usd['total_sales'] else Decimal('0')
            ),
            'daily': list(daily),
            'daily_usd': list(daily_usd),
            'top_products': list(top_products),
            'top_customers': list(top_customers),
            'top_customers_usd': list(top_customers_usd),
        }

    # ══════════════════════════════════════════════════════════
    # PURCHASE REPORT
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def get_purchase_report(date_from, date_to):
        from apps.purchases.models import PurchaseInvoice

        invoices = PurchaseInvoice.objects.filter(
            is_deleted=False,
            purchase_date__gte=date_from,
            purchase_date__lte=date_to,
        ).select_related('supplier', 'warehouse')

        afn_invoices = invoices.filter(currency='AFN')
        usd_invoices = invoices.filter(currency='USD')

        totals = afn_invoices.aggregate(
            total_purchases=Sum('total_amount'),
            total_paid=Sum('paid_amount'),
            total_remaining=Sum('remaining_amount'),
            invoice_count=Count('id'),
        )

        totals_usd = usd_invoices.aggregate(
            total_purchases=Sum('total_amount'),
            total_paid=Sum('paid_amount'),
            total_remaining=Sum('remaining_amount'),
            invoice_count=Count('id'),
        )

        # Top suppliers (AFN)
        top_suppliers = afn_invoices.values(
            'supplier__name', 'supplier__code'
        ).annotate(
            total=Sum('total_amount'),
            count=Count('id'),
        ).order_by('-total')[:10]

        # Top suppliers (USD)
        top_suppliers_usd = usd_invoices.values(
            'supplier__name', 'supplier__code'
        ).annotate(
            total=Sum('total_amount'),
            count=Count('id'),
        ).order_by('-total')[:10]

        return {
            'invoices': invoices.order_by('-purchase_date'),
            'totals': totals,
            'totals_usd': totals_usd,
            'top_suppliers': list(top_suppliers),
            'top_suppliers_usd': list(top_suppliers_usd),
        }

    # ══════════════════════════════════════════════════════════
    # PROFIT & LOSS
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def get_profit_loss(date_from, date_to):
        from apps.sales.models import Invoice
        from apps.purchases.models import PurchaseInvoice
        from apps.expenses.models import Expense

        # Revenue — AFN
        sales_afn = Invoice.objects.filter(
            is_deleted=False, currency='AFN',
            invoice_date__gte=date_from,
            invoice_date__lte=date_to,
            status__in=['confirmed', 'partial', 'paid'],
        ).aggregate(
            total_revenue=Sum('total_amount'),
            total_cogs=Sum('total_cost'),
            total_discount=Sum('discount_amount'),
        )

        # Revenue — USD
        sales_usd = Invoice.objects.filter(
            is_deleted=False, currency='USD',
            invoice_date__gte=date_from,
            invoice_date__lte=date_to,
            status__in=['confirmed', 'partial', 'paid'],
        ).aggregate(
            total_revenue=Sum('total_amount'),
            total_cogs=Sum('total_cost'),
            total_discount=Sum('discount_amount'),
        )

        total_revenue = sales_afn['total_revenue'] or Decimal('0')
        total_cogs    = sales_afn['total_cogs']    or Decimal('0')
        gross_profit  = total_revenue - total_cogs

        total_revenue_usd = sales_usd['total_revenue'] or Decimal('0')
        total_cogs_usd    = sales_usd['total_cogs']    or Decimal('0')
        gross_profit_usd  = total_revenue_usd - total_cogs_usd

        # ── split expenses by currency ──
        expenses_afn = Expense.objects.filter(
            is_deleted=False,
            status='approved',
            currency='AFN',
            expense_date__gte=date_from,
            expense_date__lte=date_to,
        ).aggregate(total=Sum('amount'))
        total_expenses_afn = expenses_afn['total'] or Decimal('0')

        expenses_usd = Expense.objects.filter(
            is_deleted=False,
            status='approved',
            currency='USD',
            expense_date__gte=date_from,
            expense_date__lte=date_to,
        ).aggregate(total=Sum('amount'))
        total_expenses_usd = expenses_usd['total'] or Decimal('0')

        expense_breakdown = Expense.objects.filter(
            is_deleted=False,
            status='approved',
            expense_date__gte=date_from,
            expense_date__lte=date_to,
        ).values('category__name', 'currency').annotate(
            total=Sum('amount')
        ).order_by('-total')

        net_profit     = gross_profit - total_expenses_afn
        net_profit_usd = gross_profit_usd - total_expenses_usd

        profit_margin = (
            net_profit / total_revenue * 100
            if total_revenue > 0 else Decimal('0')
        )
        profit_margin_usd = (
            net_profit_usd / total_revenue_usd * 100
            if total_revenue_usd > 0 else Decimal('0')
        )

        return {
            'total_revenue': total_revenue,
            'total_cogs': total_cogs,
            'gross_profit': gross_profit,
            'gross_margin': (
                gross_profit / total_revenue * 100
                if total_revenue > 0 else Decimal('0')
            ),
            'total_expenses':     total_expenses_afn,
            'total_expenses_usd': total_expenses_usd,
            'expense_breakdown': list(expense_breakdown),
            'net_profit': net_profit,
            'profit_margin': profit_margin,
            'is_profit': net_profit >= 0,

            # USD
            'total_revenue_usd': total_revenue_usd,
            'total_cogs_usd': total_cogs_usd,
            'gross_profit_usd': gross_profit_usd,
            'gross_margin_usd': (
                gross_profit_usd / total_revenue_usd * 100
                if total_revenue_usd > 0 else Decimal('0')
            ),
            'net_profit_usd': net_profit_usd,
            'profit_margin_usd': profit_margin_usd,
            'is_profit_usd': net_profit_usd >= 0,
        }

    # ══════════════════════════════════════════════════════════
    # DASHBOARD STATS
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def get_dashboard_stats():
        from apps.sales.models import Invoice
        from apps.purchases.models import PurchaseInvoice
        from apps.customers.models import Customer
        from apps.suppliers.models import Supplier
        from apps.inventory.models import Product
        from apps.expenses.models import Expense

        today       = _local_today()
        month_start = today.replace(day=1)

        # AFN: Today's sales
        today_sales_afn = Invoice.objects.filter(
            is_deleted=False, currency='AFN',
            invoice_date=today,
            status__in=['confirmed', 'partial', 'paid'],
        ).aggregate(total=Sum('total_amount'), count=Count('id'))

        # USD: Today's sales
        today_sales_usd = Invoice.objects.filter(
            is_deleted=False, currency='USD',
            invoice_date=today,
            status__in=['confirmed', 'partial', 'paid'],
        ).aggregate(total=Sum('total_amount'), count=Count('id'))

        # AFN: Today's purchases
        today_purchases_afn = PurchaseInvoice.objects.filter(
            is_deleted=False, currency='AFN',
            purchase_date=today,
        ).aggregate(total=Sum('total_amount'))

        # USD: Today's purchases
        today_purchases_usd = PurchaseInvoice.objects.filter(
            is_deleted=False, currency='USD',
            purchase_date=today,
        ).aggregate(total=Sum('total_amount'))

        # AFN: Month sales
        month_sales_afn = Invoice.objects.filter(
            is_deleted=False, currency='AFN',
            invoice_date__gte=month_start,
            status__in=['confirmed', 'partial', 'paid'],
        ).aggregate(total=Sum('total_amount'), cost=Sum('total_cost'))

        # USD: Month sales
        month_sales_usd = Invoice.objects.filter(
            is_deleted=False, currency='USD',
            invoice_date__gte=month_start,
            status__in=['confirmed', 'partial', 'paid'],
        ).aggregate(total=Sum('total_amount'), cost=Sum('total_cost'))

        # Customer debts
        customer_debt_totals = Customer.objects.filter(
            is_deleted=False, is_active=True
        ).aggregate(
            total_afn=Sum('total_debt'),
            total_usd=Sum('total_debt_usd'),
        )

        # Supplier debts
        supplier_debt_totals = Supplier.objects.filter(
            is_deleted=False, is_active=True
        ).aggregate(
            total_afn=Sum('total_debt'),
            total_usd=Sum('total_debt_usd'),
        )

        # Counts
        product_count = Product.objects.filter(
            is_deleted=False, is_active=True
        ).count()

        customer_count = Customer.objects.filter(
            is_deleted=False, is_active=True
        ).count()

        low_stock_count = Product.objects.filter(
            is_deleted=False, is_active=True,
            minimum_stock__gt=0,
            current_stock__lte=F('minimum_stock'),
        ).count()

        out_of_stock = Product.objects.filter(
            is_deleted=False, is_active=True,
            current_stock__lte=0,
        ).count()

        # Month expenses by currency
        month_expenses_afn = Expense.objects.filter(
            is_deleted=False, status='approved',
            currency='AFN',
            expense_date__gte=month_start,
        ).aggregate(total=Sum('amount'))

        month_expenses_usd = Expense.objects.filter(
            is_deleted=False, status='approved',
            currency='USD',
            expense_date__gte=month_start,
        ).aggregate(total=Sum('amount'))

        month_profit_afn = (
            (month_sales_afn['total'] or Decimal('0')) -
            (month_sales_afn['cost'] or Decimal('0')) -
            (month_expenses_afn['total'] or Decimal('0'))
        )

        month_profit_usd = (
            (month_sales_usd['total'] or Decimal('0')) -
            (month_sales_usd['cost'] or Decimal('0')) -
            (month_expenses_usd['total'] or Decimal('0'))
        )

        recent_invoices = Invoice.objects.filter(
            is_deleted=False,
        ).select_related('customer').order_by(
            '-invoice_date', '-created_at'
        )[:8]

        return {
            # AFN
            'today_sales':           today_sales_afn['total'] or Decimal('0'),
            'today_sales_count':     today_sales_afn['count'] or 0,
            'today_purchases':       today_purchases_afn['total'] or Decimal('0'),
            'month_sales':           month_sales_afn['total'] or Decimal('0'),
            'month_profit':          month_profit_afn,
            'customer_debt':         customer_debt_totals['total_afn'] or Decimal('0'),
            'supplier_debt':         supplier_debt_totals['total_afn'] or Decimal('0'),
            'month_expenses':        month_expenses_afn['total'] or Decimal('0'),

            # USD
            'today_sales_usd':       today_sales_usd['total'] or Decimal('0'),
            'today_sales_count_usd': today_sales_usd['count'] or 0,
            'today_purchases_usd':   today_purchases_usd['total'] or Decimal('0'),
            'month_sales_usd':       month_sales_usd['total'] or Decimal('0'),
            'month_profit_usd':      month_profit_usd,
            'customer_debt_usd':     customer_debt_totals['total_usd'] or Decimal('0'),
            'supplier_debt_usd':     supplier_debt_totals['total_usd'] or Decimal('0'),
            'month_expenses_usd':    month_expenses_usd['total'] or Decimal('0'),

            # Counts
            'product_count':    product_count,
            'customer_count':   customer_count,
            'low_stock_count':  low_stock_count,
            'out_of_stock':     out_of_stock,
            'recent_invoices':  recent_invoices,
        }

    # ══════════════════════════════════════════════════════════
    # INVENTORY REPORT
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def get_inventory_report():
        from apps.warehouse.services import WarehouseValuationService
        from apps.inventory.models import Product

        valuation = WarehouseValuationService.get_product_valuation()
        total     = WarehouseValuationService.get_total_valuation()
        expiring  = WarehouseValuationService.get_expiring_batches(30)
        expired   = WarehouseValuationService.get_expired_batches()

        low_stock = Product.objects.filter(
            is_deleted=False, is_active=True,
            minimum_stock__gt=0,
            current_stock__lte=F('minimum_stock'),
        ).select_related('category', 'unit').order_by('current_stock')

        out_stock = Product.objects.filter(
            is_deleted=False, is_active=True,
            current_stock__lte=0,
        ).select_related('category', 'unit')

        return {
            'valuation': valuation,
            'total':     total,
            'expiring':  expiring,
            'expired':   expired,
            'low_stock': low_stock,
            'out_stock': out_stock,
        }

    # ══════════════════════════════════════════════════════════
    # FINANCIAL SUMMARY
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def get_financial_summary(date_from, date_to):
        sales_data    = ReportService.get_sales_report(date_from, date_to)
        purchase_data = ReportService.get_purchase_report(date_from, date_to)
        pl_data       = ReportService.get_profit_loss(date_from, date_to)

        from apps.customers.models import Customer
        from apps.suppliers.models import Supplier
        from apps.capital.services import CapitalService
        from apps.warehouse.services import WarehouseValuationService
        from django.db.models import Sum

        # Customer debts (all-time)
        total_customer_debt = Customer.objects.filter(
            is_deleted=False
        ).aggregate(t=Sum('total_debt'))['t'] or Decimal('0')

        total_supplier_debt = Supplier.objects.filter(
            is_deleted=False
        ).aggregate(t=Sum('total_debt'))['t'] or Decimal('0')

        total_customer_debt_usd = Customer.objects.filter(
            is_deleted=False
        ).aggregate(t=Sum('total_debt_usd'))['t'] or Decimal('0')

        total_supplier_debt_usd = Supplier.objects.filter(
            is_deleted=False
        ).aggregate(t=Sum('total_debt_usd'))['t'] or Decimal('0')

        # Dakkan — all-time, no date filter
        dakkan_data    = CapitalService.get_shop_income(
            date_from=None, date_to=None, currency=None
        )
        dakkan_net_afn = dakkan_data.get('net_afn', Decimal('0')) or Decimal('0')
        dakkan_net_usd = dakkan_data.get('net_usd', Decimal('0')) or Decimal('0')

        # Banker balances
        banker_data      = CapitalService.get_banker_balances()
        banker_total_afn = banker_data.get('total_afn', Decimal('0')) or Decimal('0')
        banker_total_usd = banker_data.get('total_usd', Decimal('0')) or Decimal('0')

        # Warehouse stock valuation
        stock_data      = WarehouseValuationService.get_total_valuation()
        stock_value_afn = stock_data.get('total_value_all_afn', Decimal('0')) or Decimal('0')
        stock_value_usd = stock_data.get('total_value_usd',     Decimal('0')) or Decimal('0')

        # Net Business Capital
        net_capital_afn = (
            total_customer_debt
            - total_supplier_debt
            + dakkan_net_afn
            + banker_total_afn
            + stock_value_afn
        )
        net_capital_usd = (
            total_customer_debt_usd
            - total_supplier_debt_usd
            + dakkan_net_usd
            + banker_total_usd
            + stock_value_usd
        )

        return {
            'sales':                    sales_data,
            'purchases':                purchase_data,
            'pl':                       pl_data,
            # existing keys
            'total_customer_debt':      total_customer_debt,
            'total_supplier_debt':      total_supplier_debt,
            'total_customer_debt_usd':  total_customer_debt_usd,
            'total_supplier_debt_usd':  total_supplier_debt_usd,
            # new keys
            'dakkan_net_afn':           dakkan_net_afn,
            'dakkan_net_usd':           dakkan_net_usd,
            'banker_total_afn':         banker_total_afn,
            'banker_total_usd':         banker_total_usd,
            'stock_value_afn':          stock_value_afn,
            'stock_value_usd':          stock_value_usd,
            'net_capital_afn':          net_capital_afn,
            'net_capital_usd':          net_capital_usd,
            'net_capital_positive_afn': net_capital_afn >= Decimal('0'),
            'net_capital_positive_usd': net_capital_usd >= Decimal('0'),
        }