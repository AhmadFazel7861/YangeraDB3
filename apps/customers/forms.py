from django import forms
from django.utils import timezone
from .models import Customer, CustomerPayment
from decimal import Decimal
from apps.core.jalali import to_jalali_str, jalali_str_to_gregorian


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            'name', 'phone', 'phone2', 'address',
            'opening_balance', 'opening_balance_usd',
            'credit_limit', 'credit_limit_usd',
            'is_active', 'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'erp-form-control', 'placeholder': 'نام مشتری', 'autofocus': True}),
            'phone': forms.TextInput(attrs={'class': 'erp-form-control', 'placeholder': '07xxxxxxxx', 'dir': 'ltr'}),
            'phone2': forms.TextInput(attrs={'class': 'erp-form-control', 'placeholder': '07xxxxxxxx', 'dir': 'ltr'}),
            'address': forms.Textarea(attrs={'class': 'erp-form-control', 'rows': 2}),
            'opening_balance': forms.NumberInput(attrs={'class': 'erp-form-control', 'dir': 'ltr', 'step': '0.01', 'min': '0', 'placeholder': '0'}),
            'opening_balance_usd': forms.NumberInput(attrs={'class': 'erp-form-control', 'dir': 'ltr', 'step': '0.01', 'min': '0', 'placeholder': '0'}),
            'credit_limit': forms.NumberInput(attrs={'class': 'erp-form-control', 'dir': 'ltr', 'step': '0.01', 'min': '0', 'placeholder': '0'}),
            'credit_limit_usd': forms.NumberInput(attrs={'class': 'erp-form-control', 'dir': 'ltr', 'step': '0.01', 'min': '0', 'placeholder': '0'}),
            'notes': forms.Textarea(attrs={'class': 'erp-form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'نام مشتری', 'phone': 'تلفن اول', 'phone2': 'تلفن دوم',
            'address': 'آدرس',
            'opening_balance': 'بدهی اولیه (افغانی)',
            'opening_balance_usd': 'بدهی اولیه (دالر)',
            'credit_limit': 'حد اعتبار (افغانی)',
            'credit_limit_usd': 'حد اعتبار (دالر)',
            'is_active': 'فعال', 'notes': 'یادداشت',
        }


class CustomerEditForm(CustomerForm):
    """
    Same as CustomerForm but excludes opening_balance fields —
    those are set once at creation and managed by the accounting service.
    """
    class Meta(CustomerForm.Meta):
        fields = [
            'name', 'phone', 'phone2', 'address',
            'credit_limit', 'credit_limit_usd',
            'is_active', 'notes',
        ]

class PaymentReceiveForm(forms.Form):
    """
    Receive payment from customer.
    If USD + exchange_rate provided: auto-converts to clear AFN debt,
    remainder stays as USD advance.
    """
    CURRENCY_CHOICES = [('AFN', 'افغانی ؋'), ('USD', 'دالر $')]

    currency = forms.ChoiceField(
        label='واحد پول',
        choices=CURRENCY_CHOICES,
        initial='AFN',
        widget=forms.Select(attrs={'class': 'erp-form-control', 'id': 'paymentCurrency'}),
    )
    amount = forms.DecimalField(
        label='مبلغ دریافتی',
        min_value=Decimal('0.01'),
        max_digits=16, decimal_places=4,
        widget=forms.NumberInput(attrs={
            'class': 'erp-form-control', 'placeholder': '0',
            'dir': 'ltr', 'step': '0.01', 'autofocus': True,
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
            'dir': 'ltr', 'step': '0.01',
            'id': 'paymentExchangeRate',
        }),
    )
    payment_method = forms.ChoiceField(
        label='روش پرداخت',
        choices=CustomerPayment.PaymentMethod.choices,
        widget=forms.Select(attrs={'class': 'erp-form-control', 'id': 'paymentMethodSelect'}),
    )
    banker_id = forms.CharField(
        label='صراف', required=False,
        widget=forms.Select(attrs={'class': 'erp-form-control', 'id': 'bankerSelectPayment'}),
    )
    # ── Jalali date field ──
    # Changed from forms.DateField to forms.CharField because the value now
    # arrives as a Jalali string ("1405/04/11") from the dropdown pickers in
    # the template, not a native <input type="date"> Gregorian value.
    # clean_payment_date() below converts the string to a real Python date
    # object before it reaches the view — so CustomerAccountingService still
    # receives a normal date, exactly as before. This field remains REQUIRED
    # (unlike expiry_date on the warehouse form) since a payment must always
    # have a date.
    payment_date = forms.CharField(
        label='تاریخ',
        widget=forms.HiddenInput(),
    )
    notes = forms.CharField(
        label='یادداشت', required=False,
        widget=forms.TextInput(attrs={'class': 'erp-form-control', 'placeholder': 'اختیاری...'}),
    )

    def __init__(self, *args, bankers=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment_date'].initial = to_jalali_str(timezone.now().date())
        banker_choices = [('', '-- صراف را انتخاب کنید --')]
        if bankers:
            for b in bankers:
                banker_choices.append((str(b.pk), b.name))
        self.fields['banker_id'].widget = forms.Select(
            choices=banker_choices,
            attrs={'class': 'erp-form-control', 'id': 'bankerSelectPayment'},
        )

    def clean_payment_date(self):
        raw = self.cleaned_data.get('payment_date', '').strip()
        if not raw:
            raise forms.ValidationError('تاریخ را وارد کنید.')
        try:
            return jalali_str_to_gregorian(raw)
        except ValueError as e:
            raise forms.ValidationError(str(e))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('payment_method') == 'saraf' and not cleaned.get('banker_id'):
            raise forms.ValidationError('برای پرداخت از طریق صراف، صراف را انتخاب کنید.')
        if not cleaned.get('exchange_rate'):
            cleaned['exchange_rate'] = Decimal('1')
        return cleaned


class AdvanceAddForm(forms.Form):
    """
    Add advance payment — stores in chosen currency as-is, no conversion.
    """
    CURRENCY_CHOICES = [('AFN', 'افغانی ؋'), ('USD', 'دالر $')]

    currency = forms.ChoiceField(
        label='واحد پول',
        choices=CURRENCY_CHOICES,
        initial='AFN',
        widget=forms.Select(attrs={'class': 'erp-form-control', 'id': 'advanceCurrency'}),
    )
    amount = forms.DecimalField(
        label='مبلغ پیش‌پرداخت',
        min_value=Decimal('0.01'),
        max_digits=16, decimal_places=4,
        widget=forms.NumberInput(attrs={
            'class': 'erp-form-control', 'placeholder': '0',
            'dir': 'ltr', 'step': '0.01',
        }),
    )
    payment_method = forms.ChoiceField(
        label='روش پرداخت',
        choices=CustomerPayment.PaymentMethod.choices,
        widget=forms.Select(attrs={'class': 'erp-form-control', 'id': 'advanceMethodSelect'}),
    )
    banker_id = forms.CharField(
        label='صراف', required=False,
        widget=forms.Select(attrs={'class': 'erp-form-control', 'id': 'bankerSelectAdvance'}),
    )
    # ── Jalali date field — same pattern as PaymentReceiveForm above ──
    payment_date = forms.CharField(
        label='تاریخ',
        widget=forms.HiddenInput(),
    )
    notes = forms.CharField(
        label='یادداشت', required=False,
        widget=forms.TextInput(attrs={'class': 'erp-form-control', 'placeholder': 'اختیاری...'}),
    )

    def __init__(self, *args, bankers=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment_date'].initial = to_jalali_str(timezone.now().date())
        banker_choices = [('', '-- صراف را انتخاب کنید --')]
        if bankers:
            for b in bankers:
                banker_choices.append((str(b.pk), b.name))
        self.fields['banker_id'].widget = forms.Select(
            choices=banker_choices,
            attrs={'class': 'erp-form-control', 'id': 'bankerSelectAdvance'},
        )

    def clean_payment_date(self):
        raw = self.cleaned_data.get('payment_date', '').strip()
        if not raw:
            raise forms.ValidationError('تاریخ را وارد کنید.')
        try:
            return jalali_str_to_gregorian(raw)
        except ValueError as e:
            raise forms.ValidationError(str(e))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('payment_method') == 'saraf' and not cleaned.get('banker_id'):
            raise forms.ValidationError('برای پرداخت از طریق صراف، صراف را انتخاب کنید.')
        return cleaned