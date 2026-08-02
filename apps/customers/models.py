"""
Customer Models — Phase 5 Enterprise Upgrade
Full accounting: advance balance, debt, ledger, transactions
Dual currency: AFN + USD tracked separately
"""
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from apps.core.models import BaseModel


class Customer(BaseModel):
    code = models.CharField(max_length=20, unique=True, blank=True, verbose_name='کد مشتری')
    name = models.CharField(max_length=200, verbose_name='نام مشتری')
    phone = models.CharField(max_length=20, blank=True, verbose_name='تلفن')
    phone2 = models.CharField(max_length=20, blank=True, verbose_name='تلفن دوم')
    address = models.TextField(blank=True, verbose_name='آدرس')
    notes = models.TextField(blank=True, verbose_name='یادداشت')
    is_active = models.BooleanField(default=True, verbose_name='فعال')

    # AFN balances
    total_debt = models.DecimalField(
        max_digits=16, decimal_places=2, default=0,
        verbose_name='مجموع بدهی (افغانی)'
    )
    advance_balance = models.DecimalField(
        max_digits=16, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        verbose_name='موجودی پیش‌پرداخت (افغانی)'
    )

    # USD balances
    total_debt_usd = models.DecimalField(
        max_digits=16, decimal_places=4, default=0,
        verbose_name='مجموع بدهی (دالر)'
    )
    advance_balance_usd = models.DecimalField(
        max_digits=16, decimal_places=4, default=0,
        validators=[MinValueValidator(0)],
        verbose_name='موجودی پیش‌پرداخت (دالر)'
    )

    opening_balance = models.DecimalField(
        max_digits=16, decimal_places=2, default=0,
        verbose_name='بدهی اولیه'
    )
    opening_balance_usd = models.DecimalField(
        max_digits=16, decimal_places=4, default=0,
        verbose_name='بدهی اولیه (دالر)'
    )
    credit_limit = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        verbose_name='حد اعتبار'
    )
    credit_limit_usd = models.DecimalField(
        max_digits=14, decimal_places=4, default=0,
        verbose_name='حد اعتبار (دالر)'
    )
    last_transaction_date = models.DateField(
        null=True, blank=True,
        verbose_name='تاریخ آخرین تراکنش'
    )

    class Meta:
        verbose_name = 'مشتری'
        verbose_name_plural = 'مشتریان'
        db_table = 'customers_customer'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['phone']),
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
        last = Customer.objects.order_by('-created_at').first()
        if last and last.code and last.code.startswith('CST-'):
            try:
                num = int(last.code.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'CST-{num:05d}'

    @property
    def net_balance(self):
        return self.total_debt - self.advance_balance

    @property
    def net_balance_usd(self):
        return self.total_debt_usd - self.advance_balance_usd

    @property
    def balance_status(self):
        nb = self.net_balance
        if nb > 0:
            return 'debt'
        elif nb < 0:
            return 'advance'
        return 'clear'

    @property
    def balance_status_display(self):
        return {'debt': 'بدهکار', 'advance': 'بستانکار', 'clear': 'تسویه'}[self.balance_status]


class CustomerTransaction(BaseModel):

    class TxType(models.TextChoices):
        OPENING_DEBT    = 'opening_debt',    'بدهی اولیه'
        OPENING_ADVANCE = 'opening_advance', 'پیش‌پرداخت اولیه'
        INVOICE         = 'invoice',         'فاکتور فروش'
        PAYMENT         = 'payment',         'دریافت وجه'
        ADVANCE_ADD     = 'advance_add',     'افزایش پیش‌پرداخت'
        ADVANCE_USE     = 'advance_use',     'استفاده از پیش‌پرداخت'
        ADVANCE_REFUND  = 'advance_refund',  'برگشت پیش‌پرداخت'
        DEBT_WRITE_OFF  = 'debt_write_off',  'بخشودگی بدهی'
        REVERSAL        = 'reversal',        'برگشت تراکنش'
        ADJUSTMENT      = 'adjustment',      'تعدیل'

    class Currency(models.TextChoices):
        AFN = 'AFN', 'افغانی'
        USD = 'USD', 'دالر'

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE,
        related_name='transactions', verbose_name='مشتری'
    )
    tx_type = models.CharField(
        max_length=30, choices=TxType.choices, verbose_name='نوع تراکنش'
    )
    currency = models.CharField(
        max_length=3, choices=Currency.choices,
        default=Currency.AFN, verbose_name='ارز'
    )
    exchange_rate = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal('1'),
        verbose_name='نرخ تبدیل (۱ USD = ؟ AFN)'
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

    invoice = models.ForeignKey(
        'sales.Invoice', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='customer_transactions', verbose_name='فاکتور'
    )
    reversed_by = models.OneToOneField(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reversal_of', verbose_name='برگشت داده شده توسط'
    )
    is_reversed = models.BooleanField(default=False, verbose_name='برگشت شده')

    payment_method = models.CharField(max_length=20, blank=True, verbose_name='روش پرداخت')
    transaction_date = models.DateField(verbose_name='تاریخ تراکنش')
    notes = models.TextField(blank=True, verbose_name='یادداشت')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='توسط'
    )

    class Meta:
        verbose_name = 'تراکنش مشتری'
        verbose_name_plural = 'تراکنش‌های مشتری'
        db_table = 'customers_transaction'
        ordering = ['-transaction_date', '-created_at']
        indexes = [
            models.Index(fields=['customer', '-transaction_date']),
            models.Index(fields=['tx_type']),
            models.Index(fields=['is_reversed']),
            models.Index(fields=['invoice']),
        ]

    def __str__(self):
        sym = '$' if self.currency == 'USD' else '؋'
        return f'{self.customer.name} | {self.get_tx_type_display()} | {self.amount:,.2f} {sym}'


class CustomerPayment(BaseModel):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE,
        related_name='direct_payments', verbose_name='مشتری'
    )
    transaction = models.OneToOneField(
        CustomerTransaction, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='payment_record', verbose_name='تراکنش'
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=4, verbose_name='مبلغ'
    )

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
    exchange_rate = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal('1'),
        verbose_name='نرخ تبدیل'
    )
    payment_date = models.DateField(verbose_name='تاریخ پرداخت')
    notes = models.TextField(blank=True, verbose_name='یادداشت')
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='دریافت‌کننده'
    )

    class Meta:
        verbose_name = 'پرداخت مستقیم'
        verbose_name_plural = 'پرداخت‌های مستقیم'
        db_table = 'customers_payment'
        ordering = ['-payment_date', '-created_at']

    def __str__(self):
        sym = '$' if self.currency == 'USD' else '؋'
        return f'{self.customer.name} — {self.amount:,.2f} {sym}'