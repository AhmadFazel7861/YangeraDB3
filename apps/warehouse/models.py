"""
Warehouse Models — Phase 3 + Pending Delivery + Backorder
Warehouse, StockBatch (FIFO), BatchMovement, PendingDelivery, Backorder
"""
import uuid
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.conf import settings
from apps.core.models import BaseModel
from apps.inventory.models import Product


# ─────────────────────────────────────────────────────────────
# WAREHOUSE
# ─────────────────────────────────────────────────────────────
class Warehouse(BaseModel):
    name = models.CharField(max_length=100, verbose_name='نام انبار')
    location = models.CharField(max_length=200, blank=True, verbose_name='موقعیت')
    is_default = models.BooleanField(default=False, verbose_name='انبار پیشفرض')
    is_active = models.BooleanField(default=True, verbose_name='فعال')
    notes = models.TextField(blank=True, verbose_name='یادداشت')

    class Meta:
        verbose_name = 'انبار'
        verbose_name_plural = 'انبارها'
        db_table = 'warehouse_warehouse'
        indexes = [
            models.Index(fields=['is_default']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_default:
            Warehouse.objects.filter(
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_default(cls):
        return (
            cls.objects.filter(is_default=True, is_active=True).first()
            or cls.objects.filter(is_active=True).first()
        )

    @property
    def total_batches(self):
        return self.batches.filter(
            remaining_quantity__gt=0,
            is_deleted=False
        ).count()

    @property
    def total_value(self):
        """Total inventory value in this warehouse (AFN)."""
        from django.db.models import Sum, F, ExpressionWrapper, DecimalField
        result = self.batches.filter(
            remaining_quantity__gt=0,
            is_deleted=False
        ).aggregate(
            total=Sum(
                ExpressionWrapper(
                    F('remaining_quantity') * F('unit_cost'),
                    output_field=DecimalField(max_digits=20, decimal_places=2)
                )
            )
        )
        return result['total'] or Decimal('0')

    @property
    def total_value_usd(self):
        """Total inventory value in this warehouse (USD)."""
        from django.db.models import Sum, F, ExpressionWrapper, DecimalField
        result = self.batches.filter(
            remaining_quantity__gt=0,
            is_deleted=False,
            unit_cost_usd__gt=0,
        ).aggregate(
            total=Sum(
                ExpressionWrapper(
                    F('remaining_quantity') * F('unit_cost_usd'),
                    output_field=DecimalField(max_digits=20, decimal_places=4)
                )
            )
        )
        return result['total'] or Decimal('0')


# ─────────────────────────────────────────────────────────────
# STOCK BATCH (FIFO)
# ─────────────────────────────────────────────────────────────
class StockBatch(BaseModel):
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT,
        related_name='batches', verbose_name='انبار'
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT,
        related_name='batches', verbose_name='محصول'
    )
    batch_number = models.CharField(max_length=50, blank=True, verbose_name='شماره بچ')
    initial_quantity = models.DecimalField(
        max_digits=12, decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='مقدار اولیه'
    )
    remaining_quantity = models.DecimalField(
        max_digits=12, decimal_places=3,
        validators=[MinValueValidator(0)],
        verbose_name='مقدار باقی‌مانده'
    )
    unit_cost = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(0)],
        verbose_name='قیمت خرید فی واحد (افغانی)'
    )
    unit_cost_usd = models.DecimalField(
        max_digits=14, decimal_places=6,
        default=Decimal('0'),
        validators=[MinValueValidator(0)],
        verbose_name='قیمت خرید فی واحد (دالر)'
    )
    exchange_rate = models.DecimalField(
        max_digits=10, decimal_places=4,
        default=Decimal('1'),
        verbose_name='نرخ تبدیل در زمان خرید'
    )
    expiry_date = models.DateField(null=True, blank=True, verbose_name='تاریخ انقضا')
    manufactured_date = models.DateField(null=True, blank=True, verbose_name='تاریخ تولید')
    purchase_reference = models.CharField(max_length=100, blank=True, verbose_name='مرجع خرید')
    supplier_name = models.CharField(max_length=200, blank=True, verbose_name='نام تامین‌کننده')
    notes = models.TextField(blank=True, verbose_name='یادداشت')
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='received_batches', verbose_name='دریافت‌کننده'
    )

    class Meta:
        verbose_name = 'بچ موجودی'
        verbose_name_plural = 'بچ‌های موجودی'
        db_table = 'warehouse_stock_batch'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['product', 'warehouse', 'created_at']),
            models.Index(fields=['product', 'remaining_quantity']),
            models.Index(fields=['expiry_date']),
            models.Index(fields=['warehouse', 'remaining_quantity']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(remaining_quantity__gte=0),
                name='batch_remaining_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(unit_cost__gte=0),
                name='batch_cost_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(remaining_quantity__lte=models.F('initial_quantity')),
                name='batch_remaining_lte_initial'
            ),
        ]

    def __str__(self):
        return (
            f'{self.product.name} | '
            f'{self.remaining_quantity}/{self.initial_quantity} | '
            f'{self.unit_cost} ؋'
        )

    def save(self, *args, **kwargs):
        if not self.batch_number:
            self.batch_number = self._generate_batch_number()
        super().save(*args, **kwargs)

    def _generate_batch_number(self):
        from django.utils import timezone
        now = timezone.now()
        count = StockBatch.objects.filter(
            created_at__year=now.year,
            created_at__month=now.month,
        ).count() + 1
        return f'BCH-{now.strftime("%Y%m")}-{count:04d}'

    @property
    def is_exhausted(self):
        return self.remaining_quantity <= 0

    @property
    def total_cost(self):
        return self.remaining_quantity * self.unit_cost

    @property
    def total_cost_usd(self):
        return self.remaining_quantity * self.unit_cost_usd

    @property
    def consumed_quantity(self):
        return self.initial_quantity - self.remaining_quantity

    @property
    def is_expiring_soon(self):
        if not self.expiry_date:
            return False
        from django.utils import timezone
        days_left = (self.expiry_date - timezone.now().date()).days
        return 0 < days_left <= self.product.expiry_warning_days

    @property
    def is_expired(self):
        if not self.expiry_date:
            return False
        from django.utils import timezone
        return self.expiry_date < timezone.now().date()

    @property
    def days_until_expiry(self):
        if not self.expiry_date:
            return None
        from django.utils import timezone
        return (self.expiry_date - timezone.now().date()).days


# ─────────────────────────────────────────────────────────────
# BATCH MOVEMENT
# ─────────────────────────────────────────────────────────────
class BatchMovement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    batch = models.ForeignKey(
        StockBatch, on_delete=models.PROTECT,
        related_name='movements', verbose_name='بچ'
    )

    class MovementType(models.TextChoices):
        SALE       = 'sale',       'فروش'
        RETURN     = 'return',     'برگشت'
        ADJUSTMENT = 'adjustment', 'تعدیل'
        TRANSFER   = 'transfer',   'انتقال'
        DAMAGE     = 'damage',     'ضایعات'

    movement_type = models.CharField(
        max_length=20, choices=MovementType.choices, verbose_name='نوع'
    )
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, verbose_name='مقدار'
    )
    unit_cost_at_time = models.DecimalField(
        max_digits=14, decimal_places=4, verbose_name='قیمت خرید در زمان عملیات'
    )
    reference = models.CharField(max_length=100, blank=True, verbose_name='مرجع')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='توسط'
    )

    class Meta:
        verbose_name = 'حرکت بچ'
        verbose_name_plural = 'حرکات بچ'
        db_table = 'warehouse_batch_movement'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['batch', '-created_at']),
            models.Index(fields=['movement_type']),
        ]

    def __str__(self):
        return f'{self.batch.product.name} | {self.movement_type} | {self.quantity}'

    @property
    def total_cost(self):
        return self.quantity * self.unit_cost_at_time


# ─────────────────────────────────────────────────────────────
# PENDING DELIVERY
# ─────────────────────────────────────────────────────────────
class PendingDelivery(BaseModel):
    """
    Tracks physical handover of goods to customers.

    When a sale invoice is created, stock is immediately deducted from
    StockBatch (accounting done). But the customer may not pick up the
    goods right away. This model records that the goods are physically
    still in the warehouse, waiting for the customer to collect them.

    When the customer collects, staff press خروج → delivered_at is set
    and is_delivered = True. The record stays for audit trail.
    """

    class Status(models.TextChoices):
        PENDING   = 'pending',   'در انتظار تحویل'
        DELIVERED = 'delivered', 'تحویل داده شد'
        CANCELLED = 'cancelled', 'لغو شد'

    invoice = models.ForeignKey(
        'sales.Invoice',
        on_delete=models.CASCADE,
        related_name='pending_deliveries',
        verbose_name='فاکتور'
    )
    invoice_item = models.OneToOneField(
        'sales.InvoiceItem',
        on_delete=models.CASCADE,
        related_name='pending_delivery',
        verbose_name='ردیف فاکتور'
    )
    customer = models.ForeignKey(
        'customers.Customer',
        on_delete=models.CASCADE,
        related_name='pending_deliveries',
        verbose_name='مشتری'
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='pending_deliveries',
        verbose_name='انبار'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='pending_deliveries',
        verbose_name='محصول'
    )

    quantity = models.DecimalField(
        max_digits=12, decimal_places=3,
        verbose_name='مقدار'
    )
    quantity_delivered = models.DecimalField(
        max_digits=12, decimal_places=3,
        default=Decimal('0'),
        verbose_name='مقدار تحویل داده شده'
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='وضعیت'
    )

    invoice_date = models.DateField(verbose_name='تاریخ فاکتور')
    delivered_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name='زمان تحویل'
    )
    delivered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='deliveries_made',
        verbose_name='تحویل‌دهنده'
    )
    notes = models.TextField(blank=True, verbose_name='یادداشت')

    class Meta:
        verbose_name = 'تحویل معلق'
        verbose_name_plural = 'تحویل‌های معلق'
        db_table = 'warehouse_pending_delivery'
        ordering = ['invoice_date', 'created_at']
        indexes = [
            models.Index(fields=['warehouse', 'status']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['invoice']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return (
            f'{self.customer.name} | {self.product.name} | '
            f'{self.quantity} | {self.get_status_display()}'
        )

    @property
    def quantity_remaining(self):
        return self.quantity - self.quantity_delivered


# ─────────────────────────────────────────────────────────────
# BACKORDER — sold quantity that exceeded available warehouse stock
# ─────────────────────────────────────────────────────────────
class Backorder(BaseModel):
    """
    Created automatically when a sale is confirmed for more quantity
    than currently exists in the warehouse (or when the product has
    zero stock). The shortfall is recorded here.

    When new stock is received for that product/warehouse
    (FIFOService.receive_stock), open backorders are fulfilled FIRST —
    oldest backorder first (FIFO) — before any of that new stock
    becomes generally available for new sales.
    """

    class Status(models.TextChoices):
        OPEN      = 'open',      'در انتظار موجودی'
        FULFILLED = 'fulfilled', 'تکمیل شد'
        CANCELLED = 'cancelled', 'لغو شد'

    invoice = models.ForeignKey(
        'sales.Invoice',
        on_delete=models.CASCADE,
        related_name='backorders',
        verbose_name='فاکتور'
    )
    invoice_item = models.ForeignKey(
        'sales.InvoiceItem',
        on_delete=models.CASCADE,
        related_name='backorders',
        verbose_name='ردیف فاکتور'
    )
    customer = models.ForeignKey(
        'customers.Customer',
        on_delete=models.CASCADE,
        related_name='backorders',
        verbose_name='مشتری'
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='backorders',
        verbose_name='انبار'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='backorders',
        verbose_name='محصول'
    )

    quantity = models.DecimalField(
        max_digits=12, decimal_places=3,
        verbose_name='مقدار کسری (فروخته شده بدون موجودی)'
    )
    quantity_fulfilled = models.DecimalField(
        max_digits=12, decimal_places=3,
        default=Decimal('0'),
        verbose_name='مقدار تامین شده'
    )
    # Accumulated FIFO cost for the portion fulfilled so far — used to
    # retroactively correct InvoiceItem / Invoice cost when stock arrives.
    total_cost_fulfilled = models.DecimalField(
        max_digits=16, decimal_places=4,
        default=Decimal('0'),
        verbose_name='هزینه تکمیل شده'
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name='وضعیت'
    )

    created_reference = models.CharField(max_length=100, blank=True, verbose_name='مرجع فاکتور')
    notes = models.TextField(blank=True, verbose_name='یادداشت')

    class Meta:
        verbose_name = 'کسری موجودی (سفارش معلق)'
        verbose_name_plural = 'کسری‌های موجودی (سفارش‌های معلق)'
        db_table = 'warehouse_backorder'
        ordering = ['created_at']  # FIFO — oldest backorder fulfilled first
        indexes = [
            models.Index(fields=['product', 'warehouse', 'status']),
            models.Index(fields=['status']),
            models.Index(fields=['invoice']),
        ]

    def __str__(self):
        return f'{self.product.name} | کسری {self.quantity_remaining} | {self.customer.name}'

    @property
    def quantity_remaining(self):
        return self.quantity - self.quantity_fulfilled