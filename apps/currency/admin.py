from django.contrib import admin
from .models import Currency, ExchangeRate


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'name', 'symbol',
        'is_base', 'is_active', 'sort_order'
    ]
    list_filter = ['is_active', 'is_base']


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = [
        'currency', 'rate_date',
        'rate_to_afn', 'buy_rate', 'sell_rate'
    ]
    list_filter = ['currency', 'rate_date']
    ordering = ['-rate_date']