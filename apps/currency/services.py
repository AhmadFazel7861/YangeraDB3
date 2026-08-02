"""
CurrencyService — conversion utilities used across the ERP.
"""
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone


class CurrencyService:

    @staticmethod
    def get_rate(currency_code: str, date=None) -> Decimal:
        """
        Get exchange rate for a currency on a given date.
        Returns rate_to_afn (how many AFN per 1 unit of currency).
        Falls back to most recent rate if date not found.
        """
        from apps.currency.models import ExchangeRate, Currency

        if currency_code == 'AFN':
            return Decimal('1')

        if date is None:
            date = timezone.now().date()

        try:
            rate = ExchangeRate.objects.filter(
                currency__code=currency_code,
                rate_date__lte=date,
            ).order_by('-rate_date').first()

            if rate:
                return rate.rate_to_afn
        except Exception:
            pass

        return Decimal('1')

    @staticmethod
    def to_afn(amount: Decimal, currency_code: str, date=None) -> Decimal:
        """Convert any currency amount to AFN."""
        if currency_code == 'AFN':
            return amount
        rate = CurrencyService.get_rate(currency_code, date)
        return (amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @staticmethod
    def from_afn(amount_afn: Decimal, currency_code: str, date=None) -> Decimal:
        """Convert AFN to another currency."""
        if currency_code == 'AFN':
            return amount_afn
        rate = CurrencyService.get_rate(currency_code, date)
        if rate == 0:
            return Decimal('0')
        return (amount_afn / rate).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

    @staticmethod
    def get_today_rates():
        """Get all active currency rates for today."""
        from apps.currency.models import Currency
        from django.utils import timezone

        today = timezone.now().date()
        currencies = Currency.objects.filter(
            is_active=True, is_deleted=False
        ).exclude(is_base=True).order_by('sort_order')

        results = []
        for currency in currencies:
            rate = ExchangeRateHelper.get_latest(currency, today)
            results.append({
                'currency': currency,
                'rate': rate,
            })
        return results

    @staticmethod
    def initialize_default_currencies():
        """Create default currencies on first setup."""
        from apps.currency.models import Currency

        defaults = [
            {'code': 'AFN', 'name': 'افغانی',   'name_en': 'Afghan Afghani',
             'symbol': '؋', 'is_base': True,  'sort_order': 1},
            {'code': 'USD', 'name': 'دالر امریکایی', 'name_en': 'US Dollar',
             'symbol': '$', 'is_base': False, 'sort_order': 2},
            {'code': 'PKR', 'name': 'روپیه پاکستانی', 'name_en': 'Pakistani Rupee',
             'symbol': '₨', 'is_base': False, 'sort_order': 3},
            {'code': 'IRR', 'name': 'ریال ایرانی', 'name_en': 'Iranian Rial',
             'symbol': '﷼', 'is_base': False, 'sort_order': 4},
            {'code': 'EUR', 'name': 'یورو', 'name_en': 'Euro',
             'symbol': '€', 'is_base': False, 'sort_order': 5},
        ]

        for d in defaults:
            Currency.objects.get_or_create(
                code=d['code'],
                defaults=d
            )


class ExchangeRateHelper:
    @staticmethod
    def get_latest(currency, date=None):
        """Get most recent rate for a currency."""
        from apps.currency.models import ExchangeRate
        if date is None:
            date = timezone.now().date()
        return ExchangeRate.objects.filter(
            currency=currency,
            rate_date__lte=date,
        ).order_by('-rate_date').first()