from django.contrib import admin
from .models import ExpenseCategory, Expense


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    search_fields = ['name']


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'category', 'amount',
        'expense_date', 'payment_method', 'status'
    ]
    list_filter = ['category', 'status', 'payment_method', 'expense_date']
    search_fields = ['title', 'paid_to']
    readonly_fields = ['created_at', 'updated_at']