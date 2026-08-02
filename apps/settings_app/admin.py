from django.contrib import admin
from .models import BusinessSettings


@admin.register(BusinessSettings)
class BusinessSettingsAdmin(admin.ModelAdmin):
    list_display = ['business_name', 'phone1', 'default_currency']

    def has_add_permission(self, request):
        return not BusinessSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False