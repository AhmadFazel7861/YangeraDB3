from django.contrib import admin
from .models import Supplier, SupplierTransaction, SupplierPayment


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'phone', 'total_debt', 'is_active']
    search_fields = ['name', 'code', 'phone']
    list_filter = ['is_active']


@admin.register(SupplierTransaction)
class SupplierTransactionAdmin(admin.ModelAdmin):
    list_display = ['supplier', 'tx_type', 'amount', 'transaction_date', 'is_reversed']
    list_filter = ['tx_type', 'is_reversed']
    readonly_fields = ['created_at']


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = ['supplier', 'amount', 'payment_method', 'payment_date']