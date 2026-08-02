from django import forms
from django.utils import timezone
from decimal import Decimal
from .models import Invoice, Payment


class PaymentForm(forms.Form):
    CURRENCY_CHOICES = [('AFN', 'افغانی ؋'), ('USD', 'دالر $')]

    currency = forms.ChoiceField(
        label='واحد پول',
        choices=CURRENCY_CHOICES,
        widget=forms.Select(attrs={
            'class': 'erp-form-control',
            'id': 'paymentCurrencyInvoice',
        }),
    )
    amount = forms.DecimalField(
        label='مبلغ پرداخت',
        min_value=Decimal('0.01'),
        max_digits=16, decimal_places=4,
        widget=forms.NumberInput(attrs={
            'class': 'erp-form-control',
            'placeholder': '0',
            'dir': 'ltr',
            'step': '0.01',
        }),
    )
    exchange_rate = forms.DecimalField(
        label='نرخ تبدیل (۱ $ = ؟ ؋)',
        required=False,
        min_value=Decimal('1'),
        max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'erp-form-control',
            'placeholder': 'مثال: 65',
            'dir': 'ltr',
            'step': '0.01',
            'id': 'paymentExchangeRateInvoice',
        }),
    )
    payment_method = forms.ChoiceField(
        label='روش پرداخت',
        choices=Payment.PaymentMethod.choices,
        widget=forms.Select(attrs={'class': 'erp-form-control'}),
    )
    payment_date = forms.DateField(
        label='تاریخ پرداخت',
        widget=forms.DateInput(attrs={
            'class': 'erp-form-control',
            'type': 'date',
            'dir': 'ltr',
        }),
    )
    notes = forms.CharField(
        label='یادداشت',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'erp-form-control',
            'placeholder': 'اختیاری...',
        }),
    )

    def __init__(self, *args, invoice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment_date'].initial = timezone.now().date()
        # Pre-select currency to match the invoice currency
        if invoice:
            self.fields['currency'].initial = invoice.currency

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('exchange_rate'):
            cleaned['exchange_rate'] = Decimal('1')
        return cleaned