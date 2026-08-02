"""
Supplier Models — Phase 6
Supplier, SupplierTransaction, SupplierPayment
Dual currency: AFN + USD tracked separately
"""
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from apps.core.models import BaseModel


class Supplier(BaseModel):
    code = models.CharField(max_length=20, unique=True, blank=True, verbose_name='کد تامین‌کننده')
    name = models.CharField(max_length=200, verbose_name='نام تامین‌کننده')
    company = models.CharField(max_length=200, blank=True, verbose_name='نام شرکت')
    phone = models.CharField(max_length=20, blank=True, verbose_name='تلفن')
    phone2 = models.CharField(max_length=20, blank=True, verbose_name='تلفن دوم')
    address = models.TextField(blank=True, verbose_name='آدرس')
    notes = models.TextField(blank=True, verbose_name='یادداشت')
    is_active = models.BooleanField(default=True, verbose_name='فعال')

    # Link to customer account (for mutual accounts)
    customer = models.OneToOneField(
        'customers.Customer',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='supplier_account',
        verbose_name='حساب مشتری مرتبط'
    )

    # AFN balances
    total_debt = models.DecimalField(
        max_digits=16, decimal_places=2, default=0,
        verbose_name='بدهی ما (افغانی)'
    )
    advance_balance = models.DecimalField(
        max_digits=16, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        verbose_name='پیش‌پرداخت ما (افغانی)'
    )

    # USD balances
    total_debt_usd = models.DecimalField(
        max_digits=16, decimal_places=4, default=0,
        verbose_name='بدهی ما (دالر)'
    )
    advance_balance_usd = models.DecimalField(
        max_digits=16, decimal_places=4, default=0,
        validators=[MinValueValidator(0)],
        verbose_name='پیش‌پرداخت ما (دالر)'
    )

    opening_balance = models.DecimalField(
        max_digits=16, decimal_places=2, default=0,
        verbose_name='بدهی اولیه به تامین‌کننده'
    )
    opening_balance_usd = models.DecimalField(
        max_digits=16, decimal_places=4, default=0,
        verbose_name='بدهی اولیه به تامین‌کننده (دالر)'
    )
    last_transaction_date = models.DateField(
        null=True, blank=True, verbose_name='تاریخ آخرین تراکنش'
    )

    class Meta:
        verbose_name = 'تامین‌کننده'
        verbose_name_plural = 'تامین‌کنندگان'
        db_table = 'suppliers_supplier'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['code']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f'{self.name} [{self.code}]'

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        super().save(*args, **kwargs)

    def _generate_code(self):
        last = Supplier.objects.order_by('-created_at').first()
        if last and last.code and last.code.startswith('SUP-'):
            try:
                num = int(last.code.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'SUP-{num:05d}'

    @property
    def net_balance(self):
        """Positive = we owe them (AFN). Negative = they owe us."""
        return self.total_debt - self.advance_balance

    @property
    def net_balance_usd(self):
        return self.total_debt_usd - self.advance_balance_usd

    @property
    def mutual_net_balance(self):
        if not self.customer:
            return self.net_balance
        customer_debt = self.customer.total_debt - self.customer.advance_balance
        return self.net_balance - customer_debt

    @property
    def mutual_net_balance_usd(self):
        if not self.customer:
            return self.net_balance_usd
        customer_debt_usd = self.customer.total_debt_usd - self.customer.advance_balance_usd
        return self.net_balance_usd - customer_debt_usd

    @property
    def balance_status(self):
        nb = self.net_balance
        if nb > 0: return 'debt'
        elif nb < 0: return 'advance'
        return 'clear'


class SupplierTransaction(BaseModel):

    class TxType(models.TextChoices):
        OPENING_DEBT    = 'opening_debt',    'بدهی اولیه'
        OPENING_ADVANCE = 'opening_advance', 'پیش‌پرداخت اولیه'
        PURCHASE        = 'purchase',        'فاکتور خرید'
        PAYMENT         = 'payment',         'پرداخت به تامین‌کننده'
        ADVANCE_ADD     = 'advance_add',     'پیش‌پرداخت به تامین‌کننده'
        ADVANCE_USE     = 'advance_use',     'استفاده از پیش‌پرداخت'
        RETURN          = 'return',          'برگشت خرید'
        REVERSAL        = 'reversal',        'برگشت تراکنش'
        ADJUSTMENT      = 'adjustment',      'تعدیل'

    class Currency(models.TextChoices):
        AFN = 'AFN', 'افغانی'
        USD = 'USD', 'دالر'

    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE,
        related_name='transactions', verbose_name='تامین‌کننده'
    )
    tx_type = models.CharField(
        max_length=30, choices=TxType.choices, verbose_name='نوع تراکنش'
    )
    currency = models.CharField(
        max_length=3, choices=Currency.choices,
        default=Currency.AFN, verbose_name='ارز'
    )
    amount = models.DecimalField(
        max_digits=16, decimal_places=4, verbose_name='مبلغ'
    )
    amount_afn = models.DecimalField(
        max_digits=16, decimal_places=2, default=0,
        verbose_name='معادل افغانی'
    )

    # AFN balance snapshots
    debt_before    = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    debt_after     = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    advance_before = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    advance_after  = models.DecimalField(max_digits=16, decimal_places=2, default=0)

    # USD balance snapshots
    debt_before_usd    = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    debt_after_usd     = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    advance_before_usd = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    advance_after_usd  = models.DecimalField(max_digits=16, decimal_places=4, default=0)

    purchase_invoice = models.ForeignKey(
        'purchases.PurchaseInvoice',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='supplier_transactions',
        verbose_name='فاکتور خرید'
    )
    reversed_by = models.OneToOneField(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reversal_of'
    )
    is_reversed = models.BooleanField(default=False)
    payment_method = models.CharField(max_length=20, blank=True, verbose_name='روش پرداخت')
    transaction_date = models.DateField(verbose_name='تاریخ')
    notes = models.TextField(blank=True, verbose_name='یادداشت')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='توسط'
    )

    class Meta:
        verbose_name = 'تراکنش تامین‌کننده'
        verbose_name_plural = 'تراکنش‌های تامین‌کنندگان'
        db_table = 'suppliers_transaction'
        ordering = ['-transaction_date', '-created_at']
        indexes = [
            models.Index(fields=['supplier', '-transaction_date']),
            models.Index(fields=['tx_type']),
            models.Index(fields=['is_reversed']),
        ]

    def __str__(self):
        sym = '$' if self.currency == 'USD' else '؋'
        return f'{self.supplier.name} | {self.get_tx_type_display()} | {self.amount:,.2f} {sym}'


class SupplierPayment(BaseModel):

    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE,
        related_name='payments', verbose_name='تامین‌کننده'
    )
    transaction = models.OneToOneField(
        SupplierTransaction, on_delete=models.CASCADE,
        null=True, blank=True, related_name='payment_record'
    )
    amount = models.DecimalField(max_digits=14, decimal_places=4, verbose_name='مبلغ')

    class PaymentMethod(models.TextChoices):
        CASH   = 'cash',   'نقد'
        SARAF  = 'saraf',  'صراف'
        DAKKAN = 'dakkan', 'دخل دکان'

    class Currency(models.TextChoices):
        AFN = 'AFN', 'افغانی'
        USD = 'USD', 'دالر'

    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices,
        default=PaymentMethod.CASH, verbose_name='روش پرداخت'
    )
    currency = models.CharField(
        max_length=3, choices=Currency.choices,
        default=Currency.AFN, verbose_name='ارز'
    )
    payment_date = models.DateField(verbose_name='تاریخ پرداخت')
    notes = models.TextField(blank=True, verbose_name='یادداشت')
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='پرداخت‌کننده'
    )

    class Meta:
        verbose_name = 'پرداخت به تامین‌کننده'
        verbose_name_plural = 'پرداخت‌های تامین‌کنندگان'
        db_table = 'suppliers_payment'
        ordering = ['-payment_date', '-created_at']

    def __str__(self):
        sym = '$' if self.currency == 'USD' else '؋'
        return f'{self.supplier.name} — {self.amount:,.2f} {sym}'