"""
Banker System Models
Banker, BankerTransaction, BankerLedgerEntry
"""
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from apps.core.models import BaseModel


class Banker(BaseModel):
    """
    صراف — Money exchanger/banker entity.
    Each banker has a running balance we track, per currency.
    """
    name = models.CharField(
        max_length=200,
        verbose_name='نام صراف'
    )
    phone = models.CharField(
        max_length=20, blank=True,
        verbose_name='تلفن'
    )
    phone2 = models.CharField(
        max_length=20, blank=True,
        verbose_name='تلفن دوم'
    )
    address = models.TextField(
        blank=True,
        verbose_name='آدرس'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='یادداشت'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='فعال'
    )

    # Running balance per currency (auto-updated — positive = we have money with them)
    balance_afn = models.DecimalField(
        max_digits=18, decimal_places=2,
        default=Decimal('0'),
        verbose_name='مانده AFN'
    )
    balance_usd = models.DecimalField(
        max_digits=18, decimal_places=4,
        default=Decimal('0'),
        verbose_name='مانده USD'
    )
    balance_eur = models.DecimalField(
        max_digits=18, decimal_places=4,
        default=Decimal('0'),
        verbose_name='مانده EUR'
    )
    balance_irr = models.DecimalField(
        max_digits=18, decimal_places=4,
        default=Decimal('0'),
        verbose_name='مانده IRR'
    )

    class Meta:
        verbose_name = 'صراف'
        verbose_name_plural = 'صرافان'
        db_table = 'banker_banker'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name

    # ── Mapping helpers (used by services.py to stay generic) ──
    BALANCE_FIELD_MAP = {
        'AFN': 'balance_afn',
        'USD': 'balance_usd',
        'EUR': 'balance_eur',
        'IRR': 'balance_irr',
    }

    def get_balance(self, currency):
        return getattr(self, self.BALANCE_FIELD_MAP.get(currency, 'balance_afn'))

    def set_balance(self, currency, value):
        setattr(self, self.BALANCE_FIELD_MAP.get(currency, 'balance_afn'), value)

    @property
    def total_given_afn(self):
        return self._tx_sum('given', 'AFN')

    @property
    def total_received_afn(self):
        return self._tx_sum('received', 'AFN')

    @property
    def total_given_usd(self):
        return self._tx_sum('given', 'USD')

    @property
    def total_received_usd(self):
        return self._tx_sum('received', 'USD')

    @property
    def total_given_eur(self):
        return self._tx_sum('given', 'EUR')

    @property
    def total_received_eur(self):
        return self._tx_sum('received', 'EUR')

    @property
    def total_given_irr(self):
        return self._tx_sum('given', 'IRR')

    @property
    def total_received_irr(self):
        return self._tx_sum('received', 'IRR')

    def _tx_sum(self, tx_type, currency):
        return self.transactions.filter(
            tx_type=tx_type, currency=currency,
            is_deleted=False
        ).aggregate(
            t=models.Sum('amount')
        )['t'] or Decimal('0')

    @property
    def net_balance_afn(self):
        """Positive = we have given more than received (they owe us)."""
        return self.balance_afn

    @property
    def net_balance_usd(self):
        return self.balance_usd

    @property
    def balance_status(self):
        balances = [self.balance_afn, self.balance_usd, self.balance_eur, self.balance_irr]
        if any(b > 0 for b in balances):
            return 'credit'   # We gave them more
        elif any(b < 0 for b in balances):
            return 'debit'    # They gave us more
        return 'clear'


class BankerTransaction(BaseModel):
    """
    Every cash movement with a banker.
    given    = We gave cash TO banker (debit — they owe us)
    received = We received cash FROM banker (credit — we owe them)
    """

    class TxType(models.TextChoices):
        GIVEN    = 'given',    'پول داده شده به صراف'
        RECEIVED = 'received', 'پول دریافت شده از صراف'

    class Currency(models.TextChoices):
        AFN = 'AFN', 'افغانی'
        USD = 'USD', 'دالر'
        EUR = 'EUR', 'یورو'
        IRR = 'IRR', 'تومان ایران'

    banker = models.ForeignKey(
        Banker,
        on_delete=models.PROTECT,
        related_name='transactions',
        verbose_name='صراف'
    )
    tx_type = models.CharField(
        max_length=20,
        choices=TxType.choices,
        verbose_name='نوع تراکنش'
    )
    currency = models.CharField(
        max_length=5,
        choices=Currency.choices,
        default=Currency.AFN,
        verbose_name='ارز'
    )
    amount = models.DecimalField(
        max_digits=18, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
        verbose_name='مبلغ'
    )
    exchange_rate = models.DecimalField(
        max_digits=12, decimal_places=4,
        default=Decimal('1'),
        verbose_name='نرخ تبدیل (۱ واحد = ؟ AFN)'
    )
    amount_afn = models.DecimalField(
        max_digits=18, decimal_places=2,
        default=Decimal('0'),
        verbose_name='معادل افغانی'
    )

    # Balance snapshot at time of transaction (per currency)
    balance_after_afn = models.DecimalField(
        max_digits=18, decimal_places=2,
        default=Decimal('0'),
        verbose_name='مانده AFN بعد از تراکنش'
    )
    balance_after_usd = models.DecimalField(
        max_digits=18, decimal_places=4,
        default=Decimal('0'),
        verbose_name='مانده USD بعد از تراکنش'
    )
    balance_after_eur = models.DecimalField(
        max_digits=18, decimal_places=4,
        default=Decimal('0'),
        verbose_name='مانده EUR بعد از تراکنش'
    )
    balance_after_irr = models.DecimalField(
        max_digits=18, decimal_places=4,
        default=Decimal('0'),
        verbose_name='مانده IRR بعد از تراکنش'
    )

    transaction_date = models.DateField(
        verbose_name='تاریخ'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='یادداشت'
    )
    reference = models.CharField(
        max_length=100, blank=True,
        verbose_name='مرجع'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='banker_transactions',
        verbose_name='ثبت‌کننده'
    )

    class Meta:
        verbose_name = 'تراکنش صراف'
        verbose_name_plural = 'تراکنش‌های صراف'
        db_table = 'banker_transaction'
        ordering = ['-transaction_date', '-created_at']
        indexes = [
            models.Index(fields=['banker', '-transaction_date']),
            models.Index(fields=['tx_type']),
            models.Index(fields=['currency']),
            models.Index(fields=['-transaction_date']),
        ]

    def __str__(self):
        sign = '+' if self.tx_type == 'given' else '-'
        return (
            f'{self.banker.name} | '
            f'{sign}{self.amount:,.4f} {self.currency} | '
            f'{self.transaction_date}'
        )

    @property
    def is_given(self):
        return self.tx_type == 'given'

    @property
    def direction_display(self):
        return '▲ داده شده' if self.is_given else '▼ دریافت شده'