"""
Capital App Models
ShopIncomeTransfer — records when دخل دکان cash is sent to a banker (صراف)
or paid directly to a supplier (purchase invoice paid via دخل دکان).
"""
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from apps.core.models import BaseModel


class ShopIncomeTransfer(BaseModel):
    """
    Records a manual transfer of دخل دکان (shop cash income) to a صراف account,
    OR a direct purchase-invoice payment made out of دخل دکان cash.
    This does NOT touch Payment records — it only records that physical cash
    collected from customers was handed over to the banker or paid to a supplier.
    banker is nullable to support direct supplier payments from دخل دکان.
    purchase_invoice links this transfer back to the purchase invoice it paid,
    so it can be found and removed if that invoice is later edited or cancelled.
    """

    class Currency(models.TextChoices):
        AFN = 'AFN', 'افغانی ؋'
        USD = 'USD', 'دالر $'

    banker = models.ForeignKey(
        'banker.Banker',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='shop_income_transfers',
        verbose_name='صراف'
    )
    purchase_invoice = models.ForeignKey(
        'purchases.PurchaseInvoice',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='shop_income_transfers',
        verbose_name='فاکتور خرید'
    )
    amount = models.DecimalField(
        max_digits=16, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='مبلغ انتقال'
    )
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.AFN,
        verbose_name='واحد پول'
    )
    transfer_date = models.DateField(verbose_name='تاریخ انتقال')
    notes = models.TextField(blank=True, verbose_name='یادداشت')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='shop_income_transfers',
        verbose_name='ثبت‌کننده'
    )

    class Meta:
        verbose_name = 'انتقال دخل دکان به صراف'
        verbose_name_plural = 'انتقال‌های دخل دکان به صراف'
        db_table = 'capital_shop_income_transfer'
        ordering = ['-transfer_date', '-created_at']
        indexes = [
            models.Index(fields=['-transfer_date']),
            models.Index(fields=['banker']),
            models.Index(fields=['currency']),
            models.Index(fields=['purchase_invoice']),
        ]

    def __str__(self):
        sym = '$' if self.currency == 'USD' else '؋'
        banker_name = self.banker.name if self.banker else 'پرداخت مستقیم'
        return f'انتقال {self.amount:,.2f} {sym} به {banker_name} — {self.transfer_date}'

    @property
    def currency_symbol(self):
        return '$' if self.currency == 'USD' else '؋'