"""
Customer Financial Service Layer
"""
from decimal import Decimal
from django.db.models import Sum, Q
from django.utils import timezone


class CustomerLedgerService:
    """
    Generates a complete transaction ledger for a customer.
    Entries include: opening balance, invoices, invoice payments, direct payments.
    Each entry has a running balance.
    """

    @staticmethod
    def get_ledger(customer, date_from=None, date_to=None):
        """
        Returns chronological list of all transactions with running balance.
        """
        from apps.sales.models import Invoice, Payment

        entries = []

        # 1. Opening balance
        if customer.opening_balance > 0:
            entries.append({
                'date': customer.created_at.date() if customer.created_at else timezone.now().date(),
                'type': 'opening',
                'type_display': 'بدهی اولیه',
                'reference': '—',
                'debit': customer.opening_balance,   # amount owed
                'credit': Decimal('0'),              # amount paid
                'notes': 'بدهی اولیه هنگام ثبت مشتری',
                'icon': 'bi-person-plus',
                'color': 'warning',
            })

        # 2. Invoices
        invoice_qs = Invoice.objects.filter(
            customer=customer,
            is_deleted=False,
            status__in=['confirmed', 'partial', 'paid', 'cancelled']
        ).order_by('invoice_date', 'created_at')

        if date_from:
            invoice_qs = invoice_qs.filter(invoice_date__gte=date_from)
        if date_to:
            invoice_qs = invoice_qs.filter(invoice_date__lte=date_to)

        for inv in invoice_qs:
            if inv.status != 'cancelled':
                entries.append({
                    'date': inv.invoice_date,
                    'type': 'invoice',
                    'type_display': 'فاکتور فروش',
                    'reference': inv.invoice_number,
                    'reference_url': f'/sales/{inv.pk}/',
                    'debit': inv.total_amount,
                    'credit': Decimal('0'),
                    'notes': f'فاکتور {inv.invoice_number}',
                    'icon': 'bi-receipt',
                    'color': 'danger',
                })

            # Payments on this invoice
            for pmt in inv.payments.all().order_by('payment_date', 'created_at'):
                if date_from and pmt.payment_date < date_from:
                    continue
                if date_to and pmt.payment_date > date_to:
                    continue
                entries.append({
                    'date': pmt.payment_date,
                    'type': 'invoice_payment',
                    'type_display': 'پرداخت فاکتور',
                    'reference': inv.invoice_number,
                    'reference_url': f'/sales/{inv.pk}/',
                    'debit': Decimal('0'),
                    'credit': pmt.amount,
                    'notes': f'پرداخت روی فاکتور {inv.invoice_number} — {pmt.get_payment_method_display()}',
                    'icon': 'bi-cash-coin',
                    'color': 'success',
                })

        # 3. Direct payments
        from apps.customers.models import CustomerPayment
        direct_qs = CustomerPayment.objects.filter(
            customer=customer,
            is_deleted=False,
        ).order_by('payment_date', 'created_at')

        if date_from:
            direct_qs = direct_qs.filter(payment_date__gte=date_from)
        if date_to:
            direct_qs = direct_qs.filter(payment_date__lte=date_to)

        for pmt in direct_qs:
            entries.append({
                'date': pmt.payment_date,
                'type': 'direct_payment',
                'type_display': 'پرداخت مستقیم',
                'reference': f'PMT-{str(pmt.pk)[:8].upper()}',
                'debit': Decimal('0'),
                'credit': pmt.amount,
                'notes': pmt.notes or f'پرداخت مستقیم — {pmt.get_payment_method_display()}',
                'icon': 'bi-cash-stack',
                'color': 'success',
            })

        # Sort by date
        entries.sort(key=lambda x: x['date'])

        # Calculate running balance
        balance = Decimal('0')
        for entry in entries:
            balance += entry['debit'] - entry['credit']
            entry['balance'] = balance

        return entries

    @staticmethod
    def get_all_customers_debt():
        """
        Return all customers with their debt summary.
        Used for the debt report.
        """
        from apps.customers.models import Customer
        from apps.sales.models import Invoice
        from django.db.models import Sum, Count

        customers = Customer.objects.filter(
            is_active=True,
            is_deleted=False,
        ).order_by('name')

        result = []
        for customer in customers:
            debt = customer.total_debt
            result.append({
                'customer': customer,
                'debt': debt,
                'invoice_count': Invoice.objects.filter(
                    customer=customer,
                    is_deleted=False,
                    status__in=['confirmed', 'partial']
                ).count(),
            })

        # Sort by debt descending
        result.sort(key=lambda x: x['debt'], reverse=True)
        return result