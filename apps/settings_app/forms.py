from django import forms
from .models import BusinessSettings


class BusinessSettingsForm(forms.ModelForm):
    class Meta:
        model = BusinessSettings
        fields = [
            'business_name', 'business_name_en',
            'phone1', 'phone2', 'address', 'email',
            'logo', 'default_currency',
            'invoice_footer_text', 'invoice_show_fifo_cost',
            'backup_reminder_days', 'log_retention_days',
            'credit_warning_amount',
        ]
        widgets = {
            'business_name': forms.TextInput(attrs={
                'class': 'erp-form-control',
            }),
            'business_name_en': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'dir': 'ltr',
            }),
            'phone1': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'dir': 'ltr',
            }),
            'phone2': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'dir': 'ltr',
            }),
            'address': forms.Textarea(attrs={
                'class': 'erp-form-control',
                'rows': 2,
            }),
            'email': forms.EmailInput(attrs={
                'class': 'erp-form-control',
                'dir': 'ltr',
            }),
            'logo': forms.ClearableFileInput(attrs={
                'class': 'erp-form-control',
                'accept': 'image/*',
            }),
            'default_currency': forms.Select(
                choices=[('AFN', 'افغانی'), ('USD', 'دالر')],
                attrs={'class': 'erp-form-control'},
            ),
            'invoice_footer_text': forms.Textarea(attrs={
                'class': 'erp-form-control',
                'rows': 2,
            }),
            'invoice_show_fifo_cost': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'backup_reminder_days': forms.NumberInput(attrs={
                'class': 'erp-form-control',
                'dir': 'ltr',
                'min': '1',
            }),
            'log_retention_days': forms.NumberInput(attrs={
                'class': 'erp-form-control',
                'dir': 'ltr',
                'min': '7',
            }),
            'credit_warning_amount': forms.NumberInput(attrs={
                'class': 'erp-form-control',
                'dir': 'ltr',
                'step': '1000',
            }),
        }
        labels = {
            'business_name': 'نام تجاری',
            'business_name_en': 'نام انگلیسی',
            'phone1': 'تلفن اول',
            'phone2': 'تلفن دوم',
            'address': 'آدرس',
            'email': 'ایمیل',
            'logo': 'لوگو فروشگاه',
            'default_currency': 'ارز پیش‌فرض',
            'invoice_footer_text': 'متن پایین فاکتور',
            'invoice_show_fifo_cost': 'نمایش قیمت تمام شده در فاکتور',
            'backup_reminder_days': 'یادآوری بکاپ هر چند روز',
            'log_retention_days': 'نگهداری لاگ (روز)',
            'credit_warning_amount': 'مبلغ هشدار بدهی (افغانی)',
        }