from django.contrib import admin
from .models import Banker, BankerTransaction


@admin.register(Banker)
class BankerAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'phone', 'balance_afn',
        'balance_usd', 'is_active', 'created_at'
    ]
    list_filter = ['is_active']
    search_fields = ['name', 'phone']
    readonly_fields = ['balance_afn', 'balance_usd', 'created_at']


@admin.register(BankerTransaction)
class BankerTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'banker', 'tx_type', 'amount', 'currency',
        'amount_afn', 'transaction_date', 'created_by'
    ]
    list_filter = ['tx_type', 'currency', 'transaction_date']
    search_fields = ['banker__name', 'notes', 'reference']
    readonly_fields = [
        'amount_afn', 'balance_after_afn',
        'balance_after_usd', 'created_at'
    ]

    def has_change_permission(self, request, obj=None):
        return False