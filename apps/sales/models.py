"""
Sales Models — Phase 4
Invoice, InvoiceItem, Payment
"""
import uuid
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.conf import settings
from apps.core.models import BaseModel
from apps.customers.models import Customer
from apps.inventory.models import Product
from apps.warehouse.models import Warehouse, StockBatch


class Invoice(BaseModel):

    class Status(models.TextChoices):
        DRAFT     = 'draft',     'پیش‌نویس'
        CONFIRMED = 'confirmed', 'تایید شده'
        PARTIAL   = 'partial',   'پرداخت جزئی'
        PAID      = 'paid',      'پرداخت کامل'
        CANCELLED = 'cancelled', 'لغو شده'

    class Currency(models.TextChoices):
        AFN = 'AFN', 'افغانی'
        USD = 'USD', 'دالر'

    invoice_number = models.CharField(max_length=50, unique=True, verbose_name='شماره فاکتور')
    invoice_date   = models.DateField(verbose_name='تاریخ فاکتور')

    customer  = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices', verbose_name='مشتری')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='invoices', verbose_name='انبار')

    # Currency / Payment
    currency = models.CharField(
        max_length=3, choices=Currency.choices, default=Currency.AFN,
        verbose_name='واحد پول'
    )
    banker = models.ForeignKey(
        'banker.Banker',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='sale_invoices',
        verbose_name='صراف'
    )

    # Financials
    subtotal         = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name='مجموع قبل از تخفیف')
    discount_amount  = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name='تخفیف کل')
    total_amount     = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name='مبلغ کل')
    paid_amount      = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name='مبلغ پرداخت شده')
    remaining_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name='مبلغ باقی‌مانده')
    total_cost       = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name='قیمت تمام شده کل (FIFO)')
    previous_debt    = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name='بدهی قبلی مشتری')

    status    = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMED, verbose_name='وضعیت')
    notes     = models.TextField(blank=True, verbose_name='یادداشت')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='invoices_created', verbose_name='ثبت‌کننده'
    )

    class Meta:
        verbose_name = 'فاکتور فروش'
        verbose_name_plural = 'فاکتورهای فروش'
        db_table = 'sales_invoice'
        ordering = ['-invoice_date', '-created_at']
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['customer', '-invoice_date']),
            models.Index(fields=['status']),
            models.Index(fields=['-invoice_date']),
        ]

    def __str__(self):
        return f'فاکتور {self.invoice_number} — {self.customer.name}'

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self._generate_number()
        self.remaining_amount = self.total_amount - self.paid_amount
        if self.remaining_amount <= 0:
            self.status = self.Status.PAID
        elif self.paid_amount > 0:
            self.status = self.Status.PARTIAL
        super().save(*args, **kwargs)

    def _generate_number(self):
        from django.utils import timezone
        now = timezone.now()
        count = Invoice.objects.filter(created_at__year=now.year).count() + 1
        return f'INV-{now.strftime("%Y")}-{count:05d}'

    @property
    def gross_profit(self):
        return self.total_amount - self.total_cost

    @property
    def profit_margin(self):
        if self.total_amount > 0:
            return (self.gross_profit / self.total_amount) * 100
        return Decimal('0')

    @property
    def currency_symbol(self):
        return '$' if self.currency == self.Currency.USD else '؋'


class InvoiceItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    invoice  = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items', verbose_name='فاکتور')
    product  = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='sale_items', verbose_name='محصول')

    quantity         = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))], verbose_name='مقدار')
    unit_price       = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)], verbose_name='قیمت فروش فی واحد')
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name='تخفیف %')
    discount_amount  = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='مبلغ تخفیف')
    line_total       = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name='مجموع ردیف')
    unit_cost_fifo   = models.DecimalField(max_digits=14, decimal_places=4, default=0, verbose_name='قیمت خرید FIFO فی واحد')
    total_cost_fifo  = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name='قیمت تمام شده FIFO')

    class Meta:
        verbose_name = 'ردیف فاکتور'
        verbose_name_plural = 'ردیف‌های فاکتور'
        db_table = 'sales_invoice_item'
        indexes = [
            models.Index(fields=['invoice']),
            models.Index(fields=['product']),
        ]

    def __str__(self):
        return f'{self.product.name} × {self.quantity}'

    @property
    def gross_profit(self):
        return self.line_total - self.total_cost_fifo


class Payment(BaseModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments', verbose_name='فاکتور')
    amount  = models.DecimalField(max_digits=16, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], verbose_name='مبلغ')

    class PaymentMethod(models.TextChoices):
        CASH   = 'cash',   'نقد'
        CREDIT = 'credit', 'نسیه'
        SARAF  = 'saraf',  'صراف'
        DAKKAN = 'dakkan', 'دخل دکان'

    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH, verbose_name='روش پرداخت')
    payment_date   = models.DateField(verbose_name='تاریخ پرداخت')
    notes          = models.TextField(blank=True, verbose_name='یادداشت')
    received_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='دریافت‌کننده'
    )

    class Meta:
        verbose_name = 'پرداخت'
        verbose_name_plural = 'پرداخت‌ها'
        db_table = 'sales_payment'
        ordering = ['-payment_date', '-created_at']
        indexes = [models.Index(fields=['invoice', '-payment_date'])]

    def __str__(self):
        return f'{self.invoice.invoice_number} — {self.amount:,.0f}'