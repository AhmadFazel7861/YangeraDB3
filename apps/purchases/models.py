"""
Purchase Models — Phase 6
PurchaseInvoice, PurchaseItem
"""
import uuid
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.conf import settings
from apps.core.models import BaseModel
from apps.suppliers.models import Supplier
from apps.inventory.models import Product
from apps.warehouse.models import Warehouse, StockBatch


class PurchaseInvoice(BaseModel):
    """Purchase invoice header."""

    class Status(models.TextChoices):
        DRAFT    = 'draft',    'پیش‌نویس'
        UNPAID   = 'unpaid',   'پرداخت نشده'
        PARTIAL  = 'partial',  'پرداخت جزئی'
        PAID     = 'paid',     'پرداخت کامل'
        RETURNED = 'returned', 'برگشت شده'

    class Currency(models.TextChoices):
        AFN = 'AFN', 'افغانی'
        USD = 'USD', 'دالر'

    class PaymentMethod(models.TextChoices):
        CASH   = 'cash',   'نقد'
        SARAF  = 'saraf',  'صراف'
        DAKKAN = 'dakkan', 'دخل دکان'

    invoice_number = models.CharField(
        max_length=50, unique=True,
        verbose_name='شماره فاکتور'
    )
    purchase_date = models.DateField(
        verbose_name='تاریخ خرید'
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='purchase_invoices',
        verbose_name='تامین‌کننده'
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='purchase_invoices',
        verbose_name='انبار'
    )
    supplier_invoice_number = models.CharField(
        max_length=100, blank=True,
        verbose_name='شماره فاکتور تامین‌کننده'
    )

    # Currency / Payment
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.AFN,
        verbose_name='واحد پول'
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
        verbose_name='روش پرداخت'
    )
    banker = models.ForeignKey(
        'banker.Banker',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='purchase_invoices',
        verbose_name='صراف'
    )

    # Financials
    subtotal = models.DecimalField(
        max_digits=16, decimal_places=2, default=0,
        verbose_name='جمع قبل از تخفیف'
    )
    discount_amount = models.DecimalField(
        max_digits=16, decimal_places=2, default=0,
        verbose_name='تخفیف'
    )
    total_amount = models.DecimalField(
        max_digits=16, decimal_places=2, default=0,
        verbose_name='مبلغ کل'
    )
    paid_amount = models.DecimalField(
        max_digits=16, decimal_places=2, default=0,
        verbose_name='پرداخت شده'
    )
    remaining_amount = models.DecimalField(
        max_digits=16, decimal_places=2, default=0,
        verbose_name='باقی‌مانده'
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UNPAID,
        verbose_name='وضعیت'
    )
    notes = models.TextField(blank=True, verbose_name='یادداشت')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='purchases_created',
        verbose_name='ثبت‌کننده'
    )

    class Meta:
        verbose_name = 'فاکتور خرید'
        verbose_name_plural = 'فاکتورهای خرید'
        db_table = 'purchases_invoice'
        ordering = ['-purchase_date', '-created_at']
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['supplier', '-purchase_date']),
            models.Index(fields=['status']),
            models.Index(fields=['-purchase_date']),
        ]

    def __str__(self):
        return f'خرید {self.invoice_number} — {self.supplier.name}'

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self._generate_number()
        self.remaining_amount = self.total_amount - self.paid_amount
        super().save(*args, **kwargs)

    def _generate_number(self):
        from django.utils import timezone
        now = timezone.now()
        count = PurchaseInvoice.objects.filter(
            created_at__year=now.year
        ).count() + 1
        return f'PUR-{now.strftime("%Y")}-{count:05d}'

    @property
    def currency_symbol(self):
        return '$' if self.currency == self.Currency.USD else '؋'


class PurchaseItem(models.Model):
    """One line item on a purchase invoice."""

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)

    invoice = models.ForeignKey(
        PurchaseInvoice,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='فاکتور'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='purchase_items',
        verbose_name='محصول'
    )
    batch = models.ForeignKey(
        StockBatch,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='purchase_items',
        verbose_name='بچ ایجاد شده'
    )
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='مقدار'
    )
    unit_cost = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name='قیمت خرید فی واحد'
    )
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        verbose_name='تخفیف %'
    )
    discount_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        verbose_name='مبلغ تخفیف'
    )
    line_total = models.DecimalField(
        max_digits=16, decimal_places=2, default=0,
        verbose_name='مجموع ردیف'
    )
    expiry_date = models.DateField(
        null=True, blank=True,
        verbose_name='تاریخ انقضا'
    )

    class Meta:
        verbose_name = 'ردیف خرید'
        verbose_name_plural = 'ردیف‌های خرید'
        db_table = 'purchases_invoice_item'
        indexes = [
            models.Index(fields=['invoice']),
            models.Index(fields=['product']),
        ]

    def __str__(self):
        return f'{self.product.name} × {self.quantity}'