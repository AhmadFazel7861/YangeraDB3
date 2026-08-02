"""
Inventory Models — Phase 2
Category, Unit, Product, StockHistory
"""
import uuid
from django.db import models
from django.core.validators import MinValueValidator
from django.conf import settings
from apps.core.models import BaseModel


# ─────────────────────────────────────────────────────────────
# CATEGORY
# ─────────────────────────────────────────────────────────────
class Category(BaseModel):
    """Product categories — e.g. روغن، آرد، برنج"""
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='نام دسته‌بندی'
    )
    description = models.TextField(
        blank=True,
        verbose_name='توضیحات'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='فعال'
    )

    class Meta:
        verbose_name = 'دسته‌بندی'
        verbose_name_plural = 'دسته‌بندی‌ها'
        db_table = 'inventory_category'
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name

    @property
    def product_count(self):
        return self.products.filter(is_deleted=False).count()


# ─────────────────────────────────────────────────────────────
# UNIT OF MEASUREMENT
# ─────────────────────────────────────────────────────────────
class Unit(BaseModel):
    """Units — e.g. کیلوگرم، لیتر، عدد، کارتن"""
    name = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='نام واحد'
    )
    abbreviation = models.CharField(
        max_length=10,
        verbose_name='مخفف'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='فعال'
    )

    class Meta:
        verbose_name = 'واحد اندازه‌گیری'
        verbose_name_plural = 'واحدهای اندازه‌گیری'
        db_table = 'inventory_unit'

    def __str__(self):
        return f'{self.name} ({self.abbreviation})'


# ─────────────────────────────────────────────────────────────
# PRODUCT
# ─────────────────────────────────────────────────────────────
class Product(BaseModel):
    """
    Core product model.
    Prices are NOT stored here — they live on purchase lots (Phase 3).
    FIFO cost is calculated from warehouse batches.
    """
    # Identity
    code = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        verbose_name='کد محصول'
    )
    name = models.CharField(
        max_length=200,
        verbose_name='نام محصول'
    )
    name_en = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='نام انگلیسی'
    )
    barcode = models.CharField(
        max_length=100,
        blank=True,
        unique=True,
        null=True,
        verbose_name='بارکد'
    )

    # Classification
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        verbose_name='دسته‌بندی'
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.SET_NULL,
        null=True,
        related_name='products',
        verbose_name='واحد اندازه‌گیری'
    )

    # Stock control
    current_stock = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='موجودی فعلی'
    )
    minimum_stock = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='حداقل موجودی'
    )
    maximum_stock = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='حداکثر موجودی'
    )

    # Pricing (display/default — actual cost from FIFO batches)
    sale_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='قیمت فروش پیشفرض'
    )
    sale_price_usd = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='قیمت فروش دالر'
    )

    # Expiry tracking
    has_expiry = models.BooleanField(
        default=False,
        verbose_name='تاریخ انقضا دارد؟'
    )
    expiry_warning_days = models.PositiveIntegerField(
        default=30,
        verbose_name='روزهای هشدار انقضا'
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        verbose_name='فعال'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='یادداشت'
    )

    class Meta:
        verbose_name = 'محصول'
        verbose_name_plural = 'محصولات'
        db_table = 'inventory_product'
        ordering = ['name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['name']),
            models.Index(fields=['barcode']),
            models.Index(fields=['category']),
            models.Index(fields=['is_active']),
            models.Index(fields=['current_stock']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(current_stock__gte=0),
                name='product_stock_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(sale_price__gte=0),
                name='product_sale_price_non_negative'
            ),
        ]

    def __str__(self):
        return f'{self.name} [{self.code}]'

    def save(self, *args, **kwargs):
        # Auto-generate product code if not provided
        if not self.code:
            self.code = self._generate_code()
        super().save(*args, **kwargs)

    def _generate_code(self):
        """Generate sequential product code: PRD-00001"""
        last = Product.objects.order_by('-created_at').first()
        if last and last.code and last.code.startswith('PRD-'):
            try:
                num = int(last.code.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'PRD-{num:05d}'

    @property
    def is_low_stock(self):
        return self.current_stock <= self.minimum_stock and self.minimum_stock > 0

    @property
    def stock_status(self):
        if self.current_stock <= 0:
            return 'out'
        elif self.is_low_stock:
            return 'low'
        else:
            return 'ok'

    @property
    def stock_status_display(self):
        status_map = {
            'out': 'ناموجود',
            'low': 'موجودی کم',
            'ok': 'موجود',
        }
        return status_map.get(self.stock_status, 'موجود')


# ─────────────────────────────────────────────────────────────
# STOCK HISTORY
# ─────────────────────────────────────────────────────────────
class StockHistory(models.Model):
    """
    Immutable log of every stock movement.
    Created automatically — never edited manually.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ')

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='stock_history',
        verbose_name='محصول'
    )

    class MovementType(models.TextChoices):
        PURCHASE    = 'purchase',   'خریداری'
        SALE        = 'sale',       'فروش'
        RETURN_IN   = 'return_in',  'برگشت از فروش'
        RETURN_OUT  = 'return_out', 'برگشت به تامین‌کننده'
        ADJUSTMENT  = 'adjustment', 'تعدیل موجودی'
        OPENING     = 'opening',    'موجودی اولیه'
        DAMAGE      = 'damage',     'ضایعات'

    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
        verbose_name='نوع حرکت'
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name='مقدار'
    )
    # positive = stock in, negative = stock out
    quantity_before = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name='موجودی قبل'
    )
    quantity_after = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name='موجودی بعد'
    )

    unit_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='قیمت فی واحد'
    )

    reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='مرجع'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='یادداشت'
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
        verbose_name='توسط'
    )

    class Meta:
        verbose_name = 'تاریخچه موجودی'
        verbose_name_plural = 'تاریخچه موجودی'
        db_table = 'inventory_stock_history'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['product', '-created_at']),
            models.Index(fields=['movement_type']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f'{self.product.name} | {self.get_movement_type_display()} | {self.quantity}'