from django import forms
from .models import Category, Unit, Product


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'مثال: روغنیات، حبوبات، لبنیات',
                'autofocus': True,
            }),
            'description': forms.Textarea(attrs={
                'class': 'erp-form-control',
                'rows': 3,
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

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        qs = Category.objects.filter(name=name, is_deleted=False)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('این دسته‌بندی قبلاً ثبت شده است.')
        return name


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ['name', 'abbreviation', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'مثال: کیلوگرم، لیتر، عدد',
                'autofocus': True,
            }),
            'abbreviation': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'مثال: kg، L، عدد',
                'dir': 'ltr',
                'style': 'max-width: 150px;',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
        labels = {
            'name': 'نام واحد',
            'abbreviation': 'مخفف',
            'is_active': 'فعال',
        }

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        qs = Unit.objects.filter(name=name, is_deleted=False)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('این واحد قبلاً ثبت شده است.')
        return name


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'code', 'name', 'name_en',
            'category', 'unit',
            'sale_price', 'sale_price_usd',
            'minimum_stock', 'maximum_stock',
            'has_expiry', 'expiry_warning_days',
            'is_active', 'notes',
        ]
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'خودکار تولید می‌شود (اختیاری)',
                'dir': 'ltr',
            }),
            'name': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'نام محصول به دری',
                'autofocus': True,
            }),
            'name_en': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'Product name in English (optional)',
                'dir': 'ltr',
            }),
            
            'category': forms.Select(attrs={
                'class': 'erp-form-control',
            }),
            'unit': forms.Select(attrs={
                'class': 'erp-form-control',
            }),
            'sale_price': forms.NumberInput(attrs={
                'class': 'erp-form-control',
                'placeholder': '0',
                'min': '0',
                'step': '1',
                'dir': 'ltr',
            }),
            'sale_price_usd': forms.NumberInput(attrs={
                'class': 'erp-form-control',
                'placeholder': '0.00',
                'min': '0',
                'step': '0.01',
                'dir': 'ltr',
            }),
            'minimum_stock': forms.NumberInput(attrs={
                'class': 'erp-form-control',
                'placeholder': '0',
                'min': '0',
                'dir': 'ltr',
            }),
            'maximum_stock': forms.NumberInput(attrs={
                'class': 'erp-form-control',
                'placeholder': '0',
                'min': '0',
                'dir': 'ltr',
            }),
            'expiry_warning_days': forms.NumberInput(attrs={
                'class': 'erp-form-control',
                'min': '1',
                'dir': 'ltr',
            }),
            'has_expiry': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_has_expiry',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'erp-form-control',
                'rows': 3,
                'placeholder': 'یادداشت اختیاری...',
            }),
        }
        labels = {
            'code': 'کد محصول',
            'name': 'نام محصول',
            'name_en': 'نام انگلیسی',
            'category': 'دسته‌بندی',
            'unit': 'واحد اندازه‌گیری',
            'sale_price': 'قیمت فروش (افغانی)',
            'sale_price_usd': 'قیمت فروش (دالر)',
            'minimum_stock': 'حداقل موجودی',
            'maximum_stock': 'حداکثر موجودی',
            'has_expiry': 'تاریخ انقضا دارد؟',
            'expiry_warning_days': 'روزهای هشدار قبل از انقضا',
            'is_active': 'فعال',
            'notes': 'یادداشت',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active categories and units
        self.fields['category'].queryset = Category.objects.filter(
            is_active=True, is_deleted=False
        ).order_by('name')
        self.fields['unit'].queryset = Unit.objects.filter(
            is_active=True, is_deleted=False
        ).order_by('name')
        self.fields['category'].empty_label = '-- دسته‌بندی را انتخاب کنید --'
        self.fields['unit'].empty_label = '-- واحد را انتخاب کنید --'
