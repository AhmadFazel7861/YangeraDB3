from django.contrib import admin
from .models import PurchaseInvoice, PurchaseItem


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0
    readonly_fields = ['batch', 'line_total']


@admin.register(PurchaseInvoice)
class PurchaseInvoiceAdmin(admin.ModelAdmin):
    list_display = [
        'invoice_number', 'supplier', 'purchase_date',
        'total_amount', 'paid_amount', 'remaining_amount', 'status'
    ]
    list_filter = ['status', 'purchase_date']
    search_fields = ['invoice_number', 'supplier__name']
    inlines = [PurchaseItemInline]
    readonly_fields = ['invoice_number', 'created_at']