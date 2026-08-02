from django.contrib import admin
from .models import Warehouse, StockBatch, BatchMovement


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'is_default', 'is_active', 'total_batches']
    list_filter = ['is_default', 'is_active']


@admin.register(StockBatch)
class StockBatchAdmin(admin.ModelAdmin):
    list_display = [
        'batch_number', 'product', 'warehouse',
        'initial_quantity', 'remaining_quantity',
        'unit_cost', 'expiry_date', 'created_at'
    ]
    list_filter = ['warehouse', 'product__category']
    search_fields = ['batch_number', 'product__name', 'supplier_name']
    readonly_fields = ['batch_number', 'created_at', 'updated_at']


@admin.register(BatchMovement)
class BatchMovementAdmin(admin.ModelAdmin):
    list_display = ['batch', 'movement_type', 'quantity', 'unit_cost_at_time', 'created_at']
    list_filter = ['movement_type']
    readonly_fields = ['created_at']