"""
Loans App Models — قرضه‌ها
Tracks personal loans the shop owner gives out and repayments received.
Completely isolated — no modifications to any existing app.
"""
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from apps.core.models import BaseModel


class LoanPerson(BaseModel):
    """
    A person the shop owner lends money to.
    Not a Customer, not a Supplier — a standalone profile for loan tracking.
    """
    name = models.CharField(
        max_length=200,
        verbose_name='نام'
    )
    phone = models.CharField(
        max_length=20, blank=True,
        verbose_name='تلفن'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='یادداشت'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='فعال'
    )

    # Running balance per currency (positive = they owe us money)
    balance_afn = models.DecimalField(
        max_digits=18, decimal_places=2,
        default=Decimal('0'),
        verbose_name='مانده قرضه (افغانی)'
    )
    balance_usd = models.DecimalField(
        max_digits=18, decimal_places=4,
        default=Decimal('0'),
        verbose_name='مانده قرضه (دالر)'
    )

    class Meta:
        verbose_name = 'شخص قرضه‌گیر'
        verbose_name_plural = 'اشخاص قرضه‌گیر'
        db_table = 'loans_person'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name

    @property
    def balance_status_afn(self):
        if self.balance_afn > 0:
            return 'debt'      # they owe us
        elif self.balance_afn < 0:
            return 'excess'    # we somehow overpaid (shouldn't happen normally)
        return 'clear'

    @property
    def balance_status_usd(self):
        if self.balance_usd > 0:
            return 'debt'
        elif self.balance_usd < 0:
            return 'excess'
        return 'clear'


class LoanTransaction(BaseModel):
    """
    Every lending/repayment event for a LoanPerson.

    tx_type:
      GIVEN    — we lent money out (increases their debt to us)
      RECEIVED — they repaid us     (decreases their debt to us)

    payment_method:
      CASH   — physical cash, no side effects on banker or shop till
      SARAF  — via banker account (calls BankerService)
      DAKKAN — out of / into the shop till (tracked via LoanDakkhanEntry
               so CapitalService.get_shop_income can subtract/add them)

    is_reversed / reversed_by — mirrors CustomerTransaction reversal pattern.
    """

    class TxType(models.TextChoices):
        GIVEN    = 'given',    'دادن قرض'
        RECEIVED = 'received', 'بازپرداخت قرض'

    class Currency(models.TextChoices):
        AFN = 'AFN', 'افغانی'
        USD = 'USD', 'دالر'

    class PaymentMethod(models.TextChoices):
        CASH   = 'cash',   'نقدی'
        SARAF  = 'saraf',  'صراف'
        DAKKAN = 'dakkan', 'دخل دکان'

    person = models.ForeignKey(
        LoanPerson,
        on_delete=models.PROTECT,
        related_name='transactions',
        verbose_name='شخص'
    )
    tx_type = models.CharField(
        max_length=20,
        choices=TxType.choices,
        verbose_name='نوع تراکنش'
    )
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.AFN,
        verbose_name='ارز'
    )
    amount = models.DecimalField(
        max_digits=18, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
        verbose_name='مبلغ'
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
        verbose_name='روش پرداخت'
    )

    # Required only when payment_method == SARAF
    banker = models.ForeignKey(
        'banker.Banker',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='loan_transactions',
        verbose_name='صراف'
    )

    # Balance snapshots at time of transaction (per currency)
    balance_before_afn = models.DecimalField(
        max_digits=18, decimal_places=2,
        default=Decimal('0'),
        verbose_name='مانده AFN قبل'
    )
    balance_after_afn = models.DecimalField(
        max_digits=18, decimal_places=2,
        default=Decimal('0'),
        verbose_name='مانده AFN بعد'
    )
    balance_before_usd = models.DecimalField(
        max_digits=18, decimal_places=4,
        default=Decimal('0'),
        verbose_name='مانده USD قبل'
    )
    balance_after_usd = models.DecimalField(
        max_digits=18, decimal_places=4,
        default=Decimal('0'),
        verbose_name='مانده USD بعد'
    )

    transaction_date = models.DateField(verbose_name='تاریخ')
    notes = models.TextField(blank=True, verbose_name='یادداشت')

    # Reversal pattern — mirrors CustomerTransaction exactly
    is_reversed = models.BooleanField(
        default=False,
        verbose_name='برگشت شده'
    )
    reversed_by = models.OneToOneField(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reversal_of',
        verbose_name='برگشت داده شده توسط'
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='loan_transactions',
        verbose_name='ثبت‌کننده'
    )

    class Meta:
        verbose_name = 'تراکنش قرضه'
        verbose_name_plural = 'تراکنش‌های قرضه'
        db_table = 'loans_transaction'
        ordering = ['-transaction_date', '-created_at']
        indexes = [
            models.Index(fields=['person', '-transaction_date']),
            models.Index(fields=['tx_type']),
            models.Index(fields=['currency']),
            models.Index(fields=['payment_method']),
            models.Index(fields=['is_reversed']),
        ]

    def __str__(self):
        sym = '$' if self.currency == 'USD' else '؋'
        direction = '↑ داد' if self.tx_type == 'given' else '↓ گرفت'
        return (
            f'{self.person.name} | {direction} | '
            f'{self.amount:,.2f} {sym} | {self.transaction_date}'
        )

    @property
    def currency_symbol(self):
        return '$' if self.currency == 'USD' else '؋'

    @property
    def is_given(self):
        return self.tx_type == self.TxType.GIVEN


class LoanDakkhanEntry(BaseModel):
    """
    Tracks every loan transaction that touches دخل دکان (shop till cash).
    CapitalService.get_shop_income subtracts GIVEN entries and adds back
    RECEIVED entries to compute net_afn / net_usd — exactly as it already
    does for dakkan expenses and banker transfers.

    This model is append-only (soft-delete only via BaseModel.is_deleted).
    When a LoanTransaction is reversed, a compensating entry is created here
    with the opposite sign (is_given flipped), restoring the dakkan balance.
    """
    loan_transaction = models.OneToOneField(
        LoanTransaction,
        on_delete=models.PROTECT,
        related_name='dakkan_entry',
        verbose_name='تراکنش قرضه'
    )
    # Mirrors loan_transaction fields for easy querying by CapitalService
    amount = models.DecimalField(
        max_digits=18, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='مبلغ'
    )
    currency = models.CharField(
        max_length=3,
        choices=LoanTransaction.Currency.choices,
        default=LoanTransaction.Currency.AFN,
        verbose_name='ارز'
    )
    # True  = GIVEN  (cash left the till — subtract from net)
    # False = RECEIVED (cash returned to till — add back to net)
    is_outflow = models.BooleanField(
        verbose_name='خروج از دخل دکان'
    )
    entry_date = models.DateField(verbose_name='تاریخ')
    notes = models.TextField(blank=True, verbose_name='یادداشت')

    class Meta:
        verbose_name = 'ورودی دخل دکان قرضه'
        verbose_name_plural = 'ورودی‌های دخل دکان قرضه'
        db_table = 'loans_dakkan_entry'
        ordering = ['-entry_date', '-created_at']
        indexes = [
            models.Index(fields=['-entry_date']),
            models.Index(fields=['currency']),
            models.Index(fields=['is_outflow']),
        ]

    def __str__(self):
        sym = '$' if self.currency == 'USD' else '؋'
        direction = 'خروج' if self.is_outflow else 'ورود'
        return f'{direction} {self.amount:,.2f} {sym} دخل دکان — {self.entry_date}'
