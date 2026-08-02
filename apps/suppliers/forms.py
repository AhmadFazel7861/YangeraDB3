from django import forms
from django.utils import timezone
from decimal import Decimal
from .models import Supplier, SupplierPayment
from apps.core.jalali import to_jalali_str, jalali_str_to_gregorian


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            'name', 'company', 'phone', 'phone2',
            'address', 'opening_balance', 'opening_balance_usd',
            'is_active', 'notes', 'customer',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'نام تامین‌کننده',
                'autofocus': True,
            }),
            'company': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'نام شرکت (اختیاری)',
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
            }),
            'opening_balance': forms.NumberInput(attrs={
                'class': 'erp-form-control',
                'dir': 'ltr',
                'step': '1',
                'min': '0',
                'placeholder': '0',
                'id': 'id_opening_balance',
            }),
            'opening_balance_usd': forms.NumberInput(attrs={
                'class': 'erp-form-control',
                'dir': 'ltr',
                'step': '0.0001',
                'min': '0',
                'placeholder': '0.00',
                'id': 'id_opening_balance_usd',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'erp-form-control',
                'rows': 2,
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'customer': forms.Select(attrs={
                'class': 'erp-form-control',
            }),
        }
        labels = {
            'name': 'نام تامین‌کننده',
            'company': 'شرکت',
            'phone': 'تلفن اول',
            'phone2': 'تلفن دوم',
            'address': 'آدرس',
            'opening_balance': 'بدهی اولیه ما به تامین‌کننده (افغانی)',
            'opening_balance_usd': 'بدهی اولیه ما به تامین‌کننده (دالر)',
            'is_active': 'فعال',
            'notes': 'یادداشت',
            'customer': 'حساب مشتری مرتبط (اختیاری — برای حساب مشترک)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.customers.models import Customer
        qs = Customer.objects.filter(
            is_active=True, is_deleted=False
        ).order_by('name')
        if self.instance and self.instance.pk and self.instance.customer_id:
            pass
        else:
            qs = qs.filter(supplier_account__isnull=True)
        self.fields['customer'].queryset = qs
        self.fields['customer'].required = False
        self.fields['customer'].empty_label = '-- بدون حساب مشترک --'
        self.fields['opening_balance'].required = False
        self.fields['opening_balance_usd'].required = False


class SupplierPaymentForm(forms.Form):
    CURRENCY_CHOICES = [('AFN', 'افغانی ؋'), ('USD', 'دالر $')]

    currency = forms.ChoiceField(
        label='واحد پول',
        choices=CURRENCY_CHOICES,
        initial='AFN',
        widget=forms.Select(attrs={
            'class': 'erp-form-control',
            'id': 'supplierPaymentCurrency',
        }),
    )
    amount = forms.DecimalField(
        label='مبلغ پرداختی',
        min_value=Decimal('0.01'),
        max_digits=16, decimal_places=4,
        widget=forms.NumberInput(attrs={
            'class': 'erp-form-control',
            'dir': 'ltr', 'step': '0.01',
            'placeholder': '0', 'autofocus': True,
        }),
    )
    payment_method = forms.ChoiceField(
        label='روش پرداخت',
        choices=SupplierPayment.PaymentMethod.choices,
        widget=forms.Select(attrs={
            'class': 'erp-form-control',
            'id': 'supplierPaymentMethod',
        }),
    )
    banker_id = forms.CharField(
        label='صراف', required=False,
        widget=forms.Select(attrs={
            'class': 'erp-form-control',
            'id': 'supplierPaymentBanker',
        }),
    )
    # ── Jalali date field ──
    # This MUST be forms.CharField with forms.HiddenInput() — NOT DateField
    # with DateInput(type="date"). The three visible dropdowns in the
    # template (day/month/year) are what the user actually interacts with;
    # this hidden field just carries the combined "YYYY/MM/DD" Jalali string
    # to the server. clean_payment_date() below converts it to a real Python
    # date object before it reaches the view.
    payment_date = forms.CharField(
        label='تاریخ',
        widget=forms.HiddenInput(),
    )
    notes = forms.CharField(
        label='یادداشت', required=False,
        widget=forms.TextInput(attrs={
            'class': 'erp-form-control', 'placeholder': 'اختیاری...',
        }),
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
            attrs={'class': 'erp-form-control', 'id': 'supplierPaymentBanker'},
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