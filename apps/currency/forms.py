from django import forms
from django.utils import timezone
from .models import Currency, ExchangeRate


class ExchangeRateForm(forms.ModelForm):
    class Meta:
        model = ExchangeRate
        fields = [
            'currency', 'rate_date',
            'rate_to_afn', 'buy_rate', 'sell_rate', 'notes',
        ]
        widgets = {
            'currency': forms.Select(attrs={
                'class': 'erp-form-control',
            }),
            'rate_date': forms.DateInput(attrs={
                'class': 'erp-form-control',
                'type': 'date',
                'dir': 'ltr',
            }),
            'rate_to_afn': forms.NumberInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'مثال: 73.50',
                'dir': 'ltr',
                'step': '0.0001',
                'min': '0.0001',
            }),
            'buy_rate': forms.NumberInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'نرخ خرید (اختیاری)',
                'dir': 'ltr',
                'step': '0.0001',
            }),
            'sell_rate': forms.NumberInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'نرخ فروش (اختیاری)',
                'dir': 'ltr',
                'step': '0.0001',
            }),
            'notes': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'یادداشت اختیاری...',
            }),
        }
        labels = {
            'currency': 'ارز',
            'rate_date': 'تاریخ',
            'rate_to_afn': 'نرخ به افغانی (۱ واحد = ؟ افغانی)',
            'buy_rate': 'نرخ خرید',
            'sell_rate': 'نرخ فروش',
            'notes': 'یادداشت',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['currency'].queryset = Currency.objects.filter(
            is_active=True, is_deleted=False, is_base=False
        ).order_by('sort_order')
        self.fields['currency'].empty_label = '-- ارز را انتخاب کنید --'
        if not self.instance.pk:
            self.fields['rate_date'].initial = timezone.now().date()

    def clean(self):
        cleaned = super().clean()
        currency = cleaned.get('currency')
        rate_date = cleaned.get('rate_date')
        if currency and rate_date:
            qs = ExchangeRate.objects.filter(
                currency=currency,
                rate_date=rate_date,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    f'نرخ {currency.code} برای تاریخ {rate_date} '
                    f'قبلاً ثبت شده است. ویرایش کنید.'
                )
        return cleaned