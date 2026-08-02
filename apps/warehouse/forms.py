from django import forms
from .models import Warehouse, StockBatch
from apps.inventory.models import Product
from apps.core.jalali import jalali_str_to_gregorian


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['name', 'location', 'is_default', 'is_active', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'نام انبار',
                'autofocus': True,
            }),
            'location': forms.TextInput(attrs={
                'class': 'erp-form-control',
                'placeholder': 'آدرس یا موقعیت انبار',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'erp-form-control',
                'rows': 3,
            }),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'نام انبار',
            'location': 'موقعیت',
            'is_default': 'انبار پیشفرض',
            'is_active': 'فعال',
            'notes': 'یادداشت',
        }

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        # Check uniqueness only among non-deleted warehouses,
        # excluding the current instance when editing
        qs = Warehouse.objects.filter(name=name, is_deleted=False)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('انبار با این نام از قبل موجود است.')
        return name


class StockReceiveForm(forms.Form):
    """Form for manually receiving stock into a warehouse batch."""

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True, is_deleted=False),
        label='محصول',
        widget=forms.Select(attrs={'class': 'erp-form-control'}),
        empty_label='-- محصول را انتخاب کنید --',
    )
    warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True, is_deleted=False),
        label='انبار',
        widget=forms.Select(attrs={'class': 'erp-form-control'}),
        empty_label='-- انبار را انتخاب کنید --',
    )
    quantity = forms.DecimalField(
        label='مقدار',
        min_value=0,
        max_digits=12,
        decimal_places=3,
        widget=forms.NumberInput(attrs={
            'class': 'erp-form-control',
            'placeholder': '0',
            'step': '0.001',
            'dir': 'ltr',
        }),
    )
    unit_cost = forms.DecimalField(
        label='قیمت خرید فی واحد (افغانی)',
        required=False,  # ← FIXED: no longer required
        min_value=0,
        max_digits=14,
        decimal_places=2,
        initial=0,       # ← FIXED: defaults to 0
        widget=forms.NumberInput(attrs={
            'class': 'erp-form-control',
            'placeholder': '0',
            'step': '0.01',
            'dir': 'ltr',
        }),
    )
    unit_cost_usd = forms.DecimalField(
        label='قیمت خرید فی واحد (دالر)',
        required=False,
        min_value=0,
        max_digits=14,
        decimal_places=4,
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'erp-form-control',
            'placeholder': '0.00',
            'step': '0.0001',
            'dir': 'ltr',
        }),
    )
    # ── Jalali date fields ──
    # Changed from forms.DateField to forms.CharField because the value now
    # arrives as a Jalali string ("1405/04/11") from the dropdown pickers in
    # the template, not a native <input type="date"> Gregorian value.
    # clean_expiry_date() / clean_manufactured_date() below convert the
    # string to a real Python date object before it reaches the view —
    # so FIFOService.receive_stock() and StockBatch still receive a normal
    # date, exactly as before. Left blank = None, exactly as before.
    expiry_date = forms.CharField(
        label='تاریخ انقضا',
        required=False,
        widget=forms.HiddenInput(),
    )
    manufactured_date = forms.CharField(
        label='تاریخ تولید',
        required=False,
        widget=forms.HiddenInput(),
    )
    supplier_name = forms.CharField(
        label='نام تامین‌کننده',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'erp-form-control',
            'placeholder': 'اختیاری',
        }),
    )
    purchase_reference = forms.CharField(
        label='شماره فاکتور خرید',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'erp-form-control',
            'placeholder': 'اختیاری',
            'dir': 'ltr',
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

    def clean_expiry_date(self):
        raw = self.cleaned_data.get('expiry_date', '').strip()
        if not raw:
            return None
        try:
            return jalali_str_to_gregorian(raw)
        except ValueError as e:
            raise forms.ValidationError(str(e))

    def clean_manufactured_date(self):
        raw = self.cleaned_data.get('manufactured_date', '').strip()
        if not raw:
            return None
        try:
            return jalali_str_to_gregorian(raw)
        except ValueError as e:
            raise forms.ValidationError(str(e))

    def clean(self):
        cleaned = super().clean()
        exp = cleaned.get('expiry_date')
        mfg = cleaned.get('manufactured_date')
        if exp and mfg and exp <= mfg:
            raise forms.ValidationError('تاریخ انقضا باید بعد از تاریخ تولید باشد.')
        return cleaned