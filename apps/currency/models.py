"""
Currency Models — Phase 8
Currency, ExchangeRate
"""
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from apps.core.models import BaseModel


class Currency(BaseModel):
    """
    Currency master.
    AFN is always base currency (rate = 1.0).
    """
    code = models.CharField(
        max_length=10, unique=True,
        verbose_name='کد ارز'
    )
    name = models.CharField(
        max_length=100,
        verbose_name='نام ارز'
    )
    name_en = models.CharField(
        max_length=100, blank=True,
        verbose_name='نام انگلیسی'
    )
    symbol = models.CharField(
        max_length=10,
        verbose_name='نماد'
    )
    is_base = models.BooleanField(
        default=False,
        verbose_name='ارز پایه'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='فعال'
    )
    decimal_places = models.PositiveSmallIntegerField(
        default=2,
        verbose_name='اعشار'
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name='ترتیب'
    )

    class Meta:
        verbose_name = 'ارز'
        verbose_name_plural = 'ارزها'
        db_table = 'currency_currency'
        ordering = ['sort_order', 'code']

    def __str__(self):
        return f'{self.code} — {self.name}'

    def save(self, *args, **kwargs):
        # Only one base currency allowed
        if self.is_base:
            Currency.objects.filter(
                is_base=True
            ).exclude(pk=self.pk).update(is_base=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_base(cls):
        return cls.objects.filter(is_base=True).first()

    @classmethod
    def get_usd(cls):
        return cls.objects.filter(code='USD', is_active=True).first()

    @property
    def latest_rate(self):
        """Return today's or most recent exchange rate vs AFN."""
        rate = self.rates.order_by('-rate_date').first()
        return rate.rate_to_afn if rate else Decimal('1')


class ExchangeRate(BaseModel):
    """
    Daily exchange rate record.
    rate_to_afn = how many AFN per 1 unit of this currency.
    Example: 1 USD = 73.50 AFN → rate_to_afn = 73.50
    """
    currency = models.ForeignKey(
        Currency,
        on_delete=models.CASCADE,
        related_name='rates',
        verbose_name='ارز'
    )
    rate_date = models.DateField(
        verbose_name='تاریخ'
    )

    # Buy/sell rates (used in sarafi)
    rate_to_afn = models.DecimalField(
        max_digits=12, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
        verbose_name='نرخ به افغانی'
    )
    buy_rate = models.DecimalField(
        max_digits=12, decimal_places=4,
        null=True, blank=True,
        verbose_name='نرخ خرید'
    )
    sell_rate = models.DecimalField(
        max_digits=12, decimal_places=4,
        null=True, blank=True,
        verbose_name='نرخ فروش'
    )

    notes = models.CharField(
        max_length=200, blank=True,
        verbose_name='یادداشت'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='ثبت‌کننده'
    )

    class Meta:
        verbose_name = 'نرخ ارز'
        verbose_name_plural = 'نرخ‌های ارز'
        db_table = 'currency_exchange_rate'
        ordering = ['-rate_date', 'currency']
        unique_together = [['currency', 'rate_date']]
        indexes = [
            models.Index(fields=['currency', '-rate_date']),
            models.Index(fields=['-rate_date']),
        ]

    def __str__(self):
        return (
            f'{self.currency.code} | '
            f'{self.rate_date} | '
            f'{self.rate_to_afn:,.2f} AFN'
        )

    def save(self, *args, **kwargs):
        # Auto-set buy/sell if not provided
        if not self.buy_rate:
            self.buy_rate = self.rate_to_afn
        if not self.sell_rate:
            self.sell_rate = self.rate_to_afn
        super().save(*args, **kwargs)