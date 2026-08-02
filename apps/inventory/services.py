"""
Inventory Service Layer — business logic isolated from views.
"""
from decimal import Decimal
from django.db import transaction

from apps.accounts import models
from .models import Product, StockHistory


class StockService:
    """Handles all stock movement operations."""

    @staticmethod
    @transaction.atomic
    def adjust_stock(
        product: Product,
        quantity: Decimal,
        movement_type: str,
        unit_cost: Decimal = None,
        reference: str = '',
        notes: str = '',
        user=None
    ) -> StockHistory:
        """
        Core stock adjustment method.
        quantity: positive = stock in, negative = stock out
        """
        # Lock the product row for update (prevents race conditions)
        product = Product.objects.select_for_update().get(pk=product.pk)

        quantity_before = product.current_stock
        quantity_after = quantity_before + quantity

        if quantity_after < 0:
            raise ValueError(
                f'موجودی کافی نیست. موجودی فعلی: {quantity_before}'
            )

        # Update stock
        product.current_stock = quantity_after
        product.save(update_fields=['current_stock', 'updated_at'])

        # Create history record
        history = StockHistory.objects.create(
            product=product,
            movement_type=movement_type,
            quantity=quantity,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            unit_cost=unit_cost,
            reference=reference,
            notes=notes,
            created_by=user,
        )

        return history

    @staticmethod
    def set_opening_stock(product: Product, quantity: Decimal, unit_cost: Decimal = None, user=None):
        """Set initial stock for a product (used during setup)."""
        if product.current_stock != 0:
            raise ValueError('موجودی اولیه فقط برای محصولات جدید قابل تنظیم است.')

        return StockService.adjust_stock(
            product=product,
            quantity=quantity,
            movement_type=StockHistory.MovementType.OPENING,
            unit_cost=unit_cost,
            reference='موجودی اولیه',
            notes='ثبت موجودی اولیه',
            user=user,
        )

    @staticmethod
    def get_low_stock_products():
        from django.db.models import F
        return Product.objects.filter(
            is_active=True,
            is_deleted=False,
            minimum_stock__gt=0,
            current_stock__lte=F('minimum_stock')
        ).select_related('category', 'unit')

    @staticmethod
    def get_out_of_stock_products():
        """Return products with zero stock."""
        return Product.objects.filter(
            is_active=True,
            is_deleted=False,
            current_stock__lte=0
        ).select_related('category', 'unit')