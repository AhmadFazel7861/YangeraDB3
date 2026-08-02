from decimal import Decimal
from django import forms
from django.utils import timezone
from .models import Banker, BankerTransaction
from apps.core.jalali import to_jalali_str, jalali_str_to_gregorian


class BankerForm(forms.ModelForm):
    class Meta:
        model = Banker
        fields = ['name', 'phone', 'phone2', 'address', 'notes', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'نام صراف',
                'autofocus': True,
            }),
            'phone': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'dir': 'ltr',
                'placeholder': '07xxxxxxxx',
            }),
            'phone2': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'dir': 'ltr',
                'placeholder': '07xxxxxxxx',
            }),
            'address': forms.Textarea(attrs={
                'class': 'erp-form-control',
                'rows': 2,
                'placeholder': 'آدرس صراف',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'erp-form-control',
                'rows': 2,
                'placeholder': 'یادداشت...',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
        labels = {
            'name': 'نام صراف',
            'phone': 'تلفن اول',
            'phone2': 'تلفن دوم',
            'address': 'آدرس',
            'notes': 'یادداشت',
            'is_active': 'فعال',
        }


class BankerTransactionForm(forms.Form):
    """Form for recording cash given to / received from banker."""

    banker = forms.ModelChoiceField(
        label='صراف',
        queryset=Banker.objects.filter(is_active=True, is_deleted=False),
        widget=forms.Select(attrs={'class': 'erp-form-control'}),
        empty_label='-- صراف را انتخاب کنید --',
    )
    tx_type = forms.ChoiceField(
        label='نوع تراکنش',
        choices=BankerTransaction.TxType.choices,
        widget=forms.Select(attrs={'class': 'erp-form-control'}),
    )
    currency = forms.ChoiceField(
        label='ارز',
        choices=BankerTransaction.Currency.choices,
        widget=forms.Select(attrs={
            'class': 'erp-form-control',
            'id': 'id_currency',
        }),
    )
    amount = forms.DecimalField(
        label='مبلغ',
        min_value=Decimal('0.0001'),
        max_digits=18, decimal_places=4,
        widget=forms.NumberInput(attrs={
            'class': 'erp-form-control',
            'dir': 'ltr',
            'step': '0.01',
            'placeholder': '0',
            'id': 'id_amount',
        }),
    )
    transaction_date = forms.CharField(
        label='تاریخ',
        widget=forms.HiddenInput(),
    )
    reference = forms.CharField(
        label='شماره مرجع',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'erp-form-control',
            'dir': 'ltr',
            'placeholder': 'اختیاری',
        }),
    )
    notes = forms.CharField(
        label='یادداشت',
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'erp-form-control',
            'rows': 2,
            'placeholder': 'یادداشت اختیاری...',
        }),
    )    

    def __init__(self, *args, **kwargs):
        banker_pk = kwargs.pop('banker_pk', None)
        super().__init__(*args, **kwargs)
        self.fields['transaction_date'].initial = to_jalali_str(timezone.now().date())
        if banker_pk:
            try:
                self.fields['banker'].initial = Banker.objects.get(pk=banker_pk)
            except Banker.DoesNotExist:
                pass

    def clean_transaction_date(self):
        raw = self.cleaned_data.get('transaction_date', '')
        try:
            return jalali_str_to_gregorian(raw)
        except ValueError as e:
            raise forms.ValidationError(str(e))


class BankerTransferForm(forms.Form):
    """Transfer money from one صراف to another — same currency only."""

    from_banker = forms.ModelChoiceField(
        label='از صراف',
        queryset=Banker.objects.filter(is_active=True, is_deleted=False),
        widget=forms.Select(attrs={'class': 'erp-form-control'}),
        empty_label='-- صراف مبدا --',
    )
    to_banker = forms.ModelChoiceField(
        label='به صراف',
        queryset=Banker.objects.filter(is_active=True, is_deleted=False),
        widget=forms.Select(attrs={'class': 'erp-form-control'}),
        empty_label='-- صراف مقصد --',
    )
    currency = forms.ChoiceField(
        label='ارز',
        choices=BankerTransaction.Currency.choices,
        widget=forms.Select(attrs={'class': 'erp-form-control'}),
    )
    amount = forms.DecimalField(
        label='مبلغ',
        min_value=Decimal('0.0001'),
        max_digits=18, decimal_places=4,
        widget=forms.NumberInput(attrs={
            'class': 'erp-form-control',
            'dir': 'ltr',
            'step': '0.01',
            'placeholder': '0',
        }),
    )
    transaction_date = forms.CharField(
        label='تاریخ',
        widget=forms.HiddenInput(),
    )
    reference = forms.CharField(
        label='شماره مرجع',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'erp-form-control',
            'dir': 'ltr',
            'placeholder': 'اختیاری',
        }),
    )
    notes = forms.CharField(
        label='یادداشت',
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'erp-form-control',
            'rows': 2,
            'placeholder': 'یادداشت اختیاری...',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['transaction_date'].initial = to_jalali_str(timezone.now().date())

    def clean_transaction_date(self):
        raw = self.cleaned_data.get('transaction_date', '')
        try:
            return jalali_str_to_gregorian(raw)
        except ValueError as e:
            raise forms.ValidationError(str(e))

    def clean(self):
        cleaned = super().clean()
        from_banker = cleaned.get('from_banker')
        to_banker = cleaned.get('to_banker')
        if from_banker and to_banker and from_banker.pk == to_banker.pk:
            raise forms.ValidationError('صراف مبدا و مقصد نمی‌توانند یکسان باشند.')
        return cleaned