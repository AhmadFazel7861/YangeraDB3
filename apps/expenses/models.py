"""
Expense Models — Phase 7 + Saraf & USD support
ExpenseCategory, Expense
"""
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from apps.core.models import BaseModel


class ExpenseCategory(BaseModel):
    """Expense categories — e.g. کرایه، برق، معاش"""
    name = models.CharField(
        max_length=100, unique=True,
        verbose_name='نام دسته‌بندی'
    )
    description = models.TextField(
        blank=True, verbose_name='توضیحات'
    )
    is_active = models.BooleanField(
        default=True, verbose_name='فعال'
    )

    class Meta:
        verbose_name = 'دسته‌بندی مصرف'
        verbose_name_plural = 'دسته‌بندی‌های مصارف'
        db_table = 'expenses_category'
        ordering = ['name']

    def __str__(self):
        return self.name


class Expense(BaseModel):
    """Single expense record."""

    class PaymentMethod(models.TextChoices):
        CASH   = 'cash',   'نقد'
        SARAF  = 'saraf',  'صراف'
        DAKKAN = 'dakkan', 'دخل دکان'

    class Currency(models.TextChoices):
        AFN = 'AFN', 'افغانی ؋'
        USD = 'USD', 'دالر $'

    class Status(models.TextChoices):
        PENDING  = 'pending',  'در انتظار'
        APPROVED = 'approved', 'تایید شده'
        REJECTED = 'rejected', 'رد شده'

    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='expenses',
        verbose_name='دسته‌بندی'
    )
    title = models.CharField(
        max_length=200, verbose_name='عنوان مصرف'
    )

    # ── Currency ──
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.AFN,
        verbose_name='واحد پول'
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='مبلغ'
    )
    # AFN equivalent (for reporting)
    amount_afn = models.DecimalField(
        max_digits=14, decimal_places=2,
        default=Decimal('0'),
        verbose_name='معادل افغانی'
    )
    exchange_rate = models.DecimalField(
        max_digits=12, decimal_places=4,
        default=Decimal('1'),
        verbose_name='نرخ تبدیل (۱ USD = ؟ AFN)'
    )

    expense_date = models.DateField(verbose_name='تاریخ مصرف')
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
        verbose_name='روش پرداخت'
    )

    # ── Saraf fields ──
    banker = models.ForeignKey(
        'banker.Banker',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='expenses',
        verbose_name='صراف'
    )
    # How much was paid immediately via saraf (0 = full debt to saraf)
    saraf_paid_amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        default=Decimal('0'),
        verbose_name='مبلغ پرداخت شده به صراف'
    )
    saraf_debt_amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        default=Decimal('0'),
        verbose_name='بدهی به صراف'
    )
    saraf_settled = models.BooleanField(
        default=False,
        verbose_name='تسویه شده با صراف'
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.APPROVED,
        verbose_name='وضعیت'
    )
    description = models.TextField(blank=True, verbose_name='توضیحات')
    receipt_number = models.CharField(
        max_length=100, blank=True,
        verbose_name='شماره رسید'
    )
    paid_to = models.CharField(
        max_length=200, blank=True,
        verbose_name='پرداخت به'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='expenses_created',
        verbose_name='ثبت‌کننده'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='expenses_approved',
        verbose_name='تایید‌کننده'
    )

    class Meta:
        verbose_name = 'مصرف'
        verbose_name_plural = 'مصارف'
        db_table = 'expenses_expense'
        ordering = ['-expense_date', '-created_at']
        indexes = [
            models.Index(fields=['-expense_date']),
            models.Index(fields=['category']),
            models.Index(fields=['status']),
            models.Index(fields=['payment_method']),
            models.Index(fields=['banker']),
            models.Index(fields=['saraf_settled']),
        ]

    def __str__(self):
        sym = '$' if self.currency == 'USD' else '؋'
        return f'{self.title} — {self.amount:,.0f} {sym} — {self.expense_date}'

    @property
    def currency_symbol(self):
        return '$' if self.currency == 'USD' else '؋'

    @property
    def is_saraf(self):
        return self.payment_method == self.PaymentMethod.SARAF

    @property
    def saraf_remaining_debt(self):
        return max(Decimal('0'), self.saraf_debt_amount)