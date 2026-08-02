"""
Loans App Forms
"""
from decimal import Decimal
from django import forms
from django.utils import timezone

from apps.core.jalali import to_jalali_str, jalali_str_to_gregorian

from .models import LoanPerson, LoanTransaction


class LoanPersonForm(forms.ModelForm):
    class Meta:
        model = LoanPerson
        fields = ['name', 'phone', 'notes', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'نام شخص',
                'autofocus': True,
            }),
            'phone': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'تلفن (اختیاری)',
                'dir': 'ltr',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'erp-form-control',
                'rows': 3,
                'placeholder': 'یادداشت (اختیاری)',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
        labels = {
            'name': 'نام',
            'phone': 'تلفن',
            'notes': 'یادداشت',
            'is_active': 'فعال',
        }

    def clean_name(self):
        return self.cleaned_data['name'].strip()


class GiveLoanForm(forms.Form):
    """Form for recording money lent out (قرضه داده شده)."""

    currency = forms.ChoiceField(
        choices=LoanTransaction.Currency.choices,
        label='ارز',
        widget=forms.Select(attrs={
            'class': 'erp-form-control',
            'id': 'giveCurrencySelect',
        }),
        initial='AFN',
    )
    amount = forms.DecimalField(
        max_digits=18, decimal_places=4,
        min_value=Decimal('0.0001'),
        label='مبلغ',
        widget=forms.NumberInput(attrs={
            'class': 'erp-form-control',
            'placeholder': '0',
            'step': 'any',
        }),
    )
    payment_method = forms.ChoiceField(
        choices=LoanTransaction.PaymentMethod.choices,
        label='روش پرداخت',
        widget=forms.Select(attrs={
            'class': 'erp-form-control',
            'id': 'giveMethodSelect',
        }),
        initial='cash',
    )
    banker_id = forms.CharField(
        required=False,
        label='صراف',
        widget=forms.Select(attrs={
            'class': 'erp-form-control',
            'id': 'giveBankerSelect',
        }),
    )
    # ── Jalali date field ──
    # This MUST be forms.CharField with forms.HiddenInput() — NOT DateField
    # with DateInput(type="date"). The three visible dropdowns in the
    # template (day/month/year) are what the user actually interacts with;
    # this hidden field just carries the combined "YYYY/MM/DD" Jalali string
    # to the server. clean_transaction_date() below converts it to a real
    # Python date object before it reaches the view. (Same pattern as
    # SupplierPaymentForm.payment_date.)
    transaction_date = forms.CharField(
        label='تاریخ',
        widget=forms.HiddenInput(attrs={'id': 'id_give_transaction_date'}),
    )
    notes = forms.CharField(
        required=False,
        label='یادداشت',
        widget=forms.Textarea(attrs={
            'class': 'erp-form-control',
            'rows': 2,
            'placeholder': 'یادداشت (اختیاری)',
        }),
    )

    def __init__(self, *args, **kwargs):
        self.banker_queryset = kwargs.pop('banker_queryset', None)
        super().__init__(*args, **kwargs)
        if not self.data.get('transaction_date'):
            self.initial['transaction_date'] = to_jalali_str(timezone.now().date())
        choices = [('', '— صراف را انتخاب کنید —')]
        if self.banker_queryset is not None:
            choices += [(str(b.pk), b.name) for b in self.banker_queryset]
        self.fields['banker_id'].widget.choices = choices

    def clean_transaction_date(self):
        raw = self.cleaned_data.get('transaction_date', '').strip()
        if not raw:
            raise forms.ValidationError('تاریخ را وارد کنید.')
        try:
            return jalali_str_to_gregorian(raw)
        except ValueError as e:
            raise forms.ValidationError(str(e))

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get('payment_method')
        banker_id = cleaned.get('banker_id')
        if method == 'saraf':
            if not banker_id:
                self.add_error('banker_id', 'برای روش صراف، انتخاب صراف اجباری است.')
            # UUID string is passed as-is — Django ORM resolves it correctly
        else:
            cleaned['banker_id'] = None
        return cleaned


class RepaymentForm(forms.Form):
    """Form for recording a repayment received (بازپرداخت قرضه)."""

    currency = forms.ChoiceField(
        choices=LoanTransaction.Currency.choices,
        label='ارز',
        widget=forms.Select(attrs={
            'class': 'erp-form-control',
            'id': 'repCurrencySelect',
        }),
        initial='AFN',
    )
    amount = forms.DecimalField(
        max_digits=18, decimal_places=4,
        min_value=Decimal('0.0001'),
        label='مبلغ',
        widget=forms.NumberInput(attrs={
            'class': 'erp-form-control',
            'placeholder': '0',
            'step': 'any',
        }),
    )
    payment_method = forms.ChoiceField(
        choices=LoanTransaction.PaymentMethod.choices,
        label='روش دریافت',
        widget=forms.Select(attrs={
            'class': 'erp-form-control',
            'id': 'repMethodSelect',
        }),
        initial='cash',
    )
    banker_id = forms.CharField(
        required=False,
        label='صراف',
        widget=forms.Select(attrs={
            'class': 'erp-form-control',
            'id': 'repBankerSelect',
        }),
    )
    # ── Jalali date field ── (same pattern as GiveLoanForm.transaction_date)
    transaction_date = forms.CharField(
        label='تاریخ',
        widget=forms.HiddenInput(attrs={'id': 'id_rep_transaction_date'}),
    )
    notes = forms.CharField(
        required=False,
        label='یادداشت',
        widget=forms.Textarea(attrs={
            'class': 'erp-form-control',
            'rows': 2,
            'placeholder': 'یادداشت (اختیاری)',
        }),
    )

    def __init__(self, *args, **kwargs):
        self.banker_queryset = kwargs.pop('banker_queryset', None)
        super().__init__(*args, **kwargs)
        if not self.data.get('transaction_date'):
            self.initial['transaction_date'] = to_jalali_str(timezone.now().date())
        choices = [('', '— صراف را انتخاب کنید —')]
        if self.banker_queryset is not None:
            choices += [(str(b.pk), b.name) for b in self.banker_queryset]
        self.fields['banker_id'].widget.choices = choices

    def clean_transaction_date(self):
        raw = self.cleaned_data.get('transaction_date', '').strip()
        if not raw:
            raise forms.ValidationError('تاریخ را وارد کنید.')
        try:
            return jalali_str_to_gregorian(raw)
        except ValueError as e:
            raise forms.ValidationError(str(e))

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get('payment_method')
        banker_id = cleaned.get('banker_id')
        if method == 'saraf':
            if not banker_id:
                self.add_error('banker_id', 'برای روش صراف، انتخاب صراف اجباری است.')
            # UUID string is passed as-is — Django ORM resolves it correctly
        else:
            cleaned['banker_id'] = None
        return cleaned