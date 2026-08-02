from django.contrib import admin
from .models import Category, Unit, Product, StockHistory


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'product_count', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ['name', 'abbreviation', 'is_active']
    list_filter = ['is_active']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'category', 'unit', 'current_stock', 'sale_price', 'is_active']
    list_filter = ['category', 'is_active', 'has_expiry']
    search_fields = ['name', 'code', 'barcode']
    readonly_fields = ['current_stock', 'created_at', 'updated_at']


@admin.register(StockHistory)
class StockHistoryAdmin(admin.ModelAdmin):
    list_display = ['product', 'movement_type', 'quantity', 'quantity_before', 'quantity_after', 'created_at']
    list_filter = ['movement_type']
    readonly_fields = ['created_at']