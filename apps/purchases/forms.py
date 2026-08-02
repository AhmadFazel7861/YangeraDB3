from django import forms
from django.utils import timezone
from decimal import Decimal
from apps.suppliers.models import Supplier, SupplierPayment
from apps.warehouse.models import Warehouse


class PurchasePaymentForm(forms.Form):
    CURRENCY_CHOICES = [('AFN', 'افغانی ؋'), ('USD', 'دالر $')]

    currency = forms.ChoiceField(
        label='واحد پول',
        choices=CURRENCY_CHOICES,
        initial='AFN',
        widget=forms.Select(attrs={
            'class': 'erp-form-control',
            'id': 'purchasePaymentCurrency',
        }),
    )
    amount = forms.DecimalField(
        label='مبلغ پرداختی',
        min_value=Decimal('0.01'),
        max_digits=16, decimal_places=4,
        widget=forms.NumberInput(attrs={
            'class': 'erp-form-control',
            'dir': 'ltr', 'step': '0.01', 'placeholder': '0',
        }),
    )
    payment_method = forms.ChoiceField(
        label='روش پرداخت',
        choices=SupplierPayment.PaymentMethod.choices,
        widget=forms.Select(attrs={
            'class': 'erp-form-control',
            'id': 'purchasePaymentMethod',
        }),
    )
    banker_id = forms.CharField(
        label='صراف',
        required=False,
        widget=forms.Select(attrs={
            'class': 'erp-form-control',
            'id': 'purchasePaymentBanker',
        }),
    )
    payment_date = forms.DateField(
        label='تاریخ',
        widget=forms.DateInput(attrs={
            'class': 'erp-form-control',
            'type': 'date', 'dir': 'ltr',
        }),
    )
    notes = forms.CharField(
        label='یادداشت', required=False,
        widget=forms.TextInput(attrs={
            'class': 'erp-form-control',
            'placeholder': 'اختیاری...',
        }),
    )

    def __init__(self, *args, bankers=None, invoice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment_date'].initial = timezone.now().date()
        # Pre-select currency to match invoice currency
        if invoice:
            self.fields['currency'].initial = getattr(invoice, 'currency', 'AFN')
        # Populate banker choices
        banker_choices = [('', '-- صراف را انتخاب کنید --')]
        if bankers:
            for b in bankers:
                banker_choices.append((str(b.pk), b.name))
        self.fields['banker_id'].widget = forms.Select(
            choices=banker_choices,
            attrs={'class': 'erp-form-control', 'id': 'purchasePaymentBanker'},
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('payment_method') == 'saraf' and not cleaned.get('banker_id'):
            raise forms.ValidationError('برای پرداخت از طریق صراف، صراف را انتخاب کنید.')
        return cleaned