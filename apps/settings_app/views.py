"""Settings Views — Phase 14"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import BusinessSettings
from .forms import BusinessSettingsForm


@login_required
def settings_view(request):
    settings_obj = BusinessSettings.get_solo()
    form = BusinessSettingsForm(
        request.POST or None,
        request.FILES or None,
        instance=settings_obj,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'تنظیمات با موفقیت ذخیره شد.')
        return redirect('settings_app:settings')

    return render(request, 'settings_app/settings.html', {
        'page_title': 'تنظیمات سیستم',
        'form': form,
        'settings_obj': settings_obj,
    })