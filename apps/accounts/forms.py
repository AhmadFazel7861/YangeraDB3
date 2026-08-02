from django import forms
from django.contrib.auth.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    """Styled login form for the ERP system."""

    username = forms.CharField(
        label='نام کاربری',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'نام کاربری را وارد کنید',
            'autofocus': True,
            'autocomplete': 'username',
            'dir': 'ltr',
        })
    )
    password = forms.CharField(
        label='رمز عبور',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': '••••••',
            'autocomplete': 'current-password',
            'dir': 'ltr',
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        label='مرا به خاطر بسپار',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )