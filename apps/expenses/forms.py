from django import forms
from django.utils import timezone
from .models import ExpenseCategory, Expense
from apps.core.jalali import to_jalali_str, jalali_str_to_gregorian


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'مثال: کرایه، برق، معاش',
                'autofocus': True,
            }),
            'description': forms.Textarea(attrs={
                'class': 'erp-form-control',
                'rows': 2,
                'placeholder': 'توضیحات اختیاری...',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
        labels = {
            'name': 'نام دسته‌بندی',
            'description': 'توضیحات',
            'is_active': 'فعال',
        }


class ExpenseForm(forms.ModelForm):

    # Extra field — not on model directly, used in view logic
    banker_id = forms.UUIDField(required=False, widget=forms.HiddenInput())

    # ── Jalali date field ──
    # Overrides the ModelForm's auto-generated expense_date field (which
    # would otherwise be a DateField bound to the widget in Meta.widgets
    # below). The value now arrives as a Jalali string ("1405/04/11") from
    # the dropdown pickers in the template. clean_expense_date() converts
    # it to a real Python date before form.save() writes it to the model —
    # so Expense.expense_date still gets a normal date, exactly as before.
    expense_date = forms.CharField(
        label='تاریخ',
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = Expense
        fields = [
            'title', 'category', 'currency', 'amount',
            'expense_date', 'payment_method', 'banker',
            'saraf_paid_amount', 'paid_to', 'receipt_number', 'description',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'عنوان مصرف',
                'autofocus': True,
            }),
            'category': forms.Select(attrs={
                'class': 'erp-form-control',
            }),
            'currency': forms.Select(attrs={
                'class': 'erp-form-control',
                'id': 'currencySelect',
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'erp-form-control',
                'placeholder': '0',
                'dir': 'ltr',
                'step': '0.01',
                'min': '0.01',
                'id': 'amountInput',
            }),
            'payment_method': forms.Select(attrs={
                'class': 'erp-form-control',
                'id': 'paymentMethodSelect',
            }),
            'banker': forms.Select(attrs={
                'class': 'erp-form-control',
                'id': 'bankerSelect',
            }),
            'saraf_paid_amount': forms.NumberInput(attrs={
                'class': 'erp-form-control',
                'placeholder': '0 — اگر خالی بماند تمام مبلغ بدهی ثبت می‌شود',
                'dir': 'ltr',
                'step': '0.01',
                'min': '0',
                'id': 'sarafPaidAmount',
            }),
            'paid_to': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'نام شخص یا شرکت (اختیاری)',
            }),
            'receipt_number': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'شماره رسید (اختیاری)',
                'dir': 'ltr',
            }),
            'description': forms.Textarea(attrs={
                'class': 'erp-form-control',
                'rows': 3,
                'placeholder': 'توضیحات اختیاری...',
            }),
        }
        labels = {
            'title': 'عنوان مصرف',
            'category': 'دسته‌بندی',
            'currency': 'واحد پول',
            'amount': 'مبلغ',
            'expense_date': 'تاریخ',
            'payment_method': 'روش پرداخت',
            'banker': 'صراف',
            'saraf_paid_amount': 'مبلغ نقد پرداخت شده به صراف',
            'paid_to': 'پرداخت به',
            'receipt_number': 'شماره رسید',
            'description': 'توضیحات',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['category'].queryset = ExpenseCategory.objects.filter(
            is_active=True, is_deleted=False
        ).order_by('name')
        self.fields['category'].empty_label = '-- دسته‌بندی را انتخاب کنید --'

        from apps.banker.models import Banker
        self.fields['banker'].queryset = Banker.objects.filter(
            is_active=True, is_deleted=False
        ).order_by('name')
        self.fields['banker'].empty_label = '-- صراف را انتخاب کنید --'
        self.fields['banker'].required = False

        self.fields['saraf_paid_amount'].required = False

        if not self.instance.pk:
            self.fields['expense_date'].initial = to_jalali_str(timezone.now().date())
        else:
            self.fields['expense_date'].initial = to_jalali_str(self.instance.expense_date)

    def clean_expense_date(self):
        raw = self.cleaned_data.get('expense_date', '').strip()
        if not raw:
            raise forms.ValidationError('تاریخ را وارد کنید.')
        try:
            return jalali_str_to_gregorian(raw)
        except ValueError as e:
            raise forms.ValidationError(str(e))

    def clean(self):
        cleaned_data = super().clean()
        payment_method  = cleaned_data.get('payment_method')
        banker          = cleaned_data.get('banker')
        amount          = cleaned_data.get('amount') or 0
        saraf_paid      = cleaned_data.get('saraf_paid_amount') or 0

        if payment_method == 'saraf':
            if not banker:
                self.add_error('banker', 'برای پرداخت از طریق صراف، صراف را انتخاب کنید.')
            if saraf_paid < 0:
                self.add_error('saraf_paid_amount', 'مبلغ پرداخت شده نمی‌تواند منفی باشد.')
            if saraf_paid > amount:
                self.add_error(
                    'saraf_paid_amount',
                    'مبلغ پرداخت شده نمی‌تواند بیشتر از مبلغ کل مصرف باشد.'
                )

        return cleaned_data