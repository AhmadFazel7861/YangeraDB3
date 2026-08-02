from django.contrib import admin
from .models import Customer, CustomerPayment


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'opening_balance', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'phone']


@admin.register(CustomerPayment)
class CustomerPaymentAdmin(admin.ModelAdmin):
    list_display = ['customer', 'amount', 'payment_method', 'payment_date']
    list_filter = ['payment_method', 'payment_date']
    search_fields = ['customer__name']