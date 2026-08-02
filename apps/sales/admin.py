from django.contrib import admin
from .models import Invoice, InvoiceItem, Payment


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = ['unit_cost_fifo', 'total_cost_fifo', 'line_total']


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        'invoice_number', 'customer', 'invoice_date',
        'total_amount', 'paid_amount', 'remaining_amount', 'status'
    ]
    list_filter = ['status', 'invoice_date']
    search_fields = ['invoice_number', 'customer__name']
    inlines = [InvoiceItemInline, PaymentInline]
    readonly_fields = ['invoice_number', 'total_cost', 'created_at']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'amount', 'payment_method', 'payment_date']
    list_filter = ['payment_method', 'payment_date']