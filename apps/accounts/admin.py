from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'get_full_name', 'role', 'phone', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'is_staff']
    fieldsets = UserAdmin.fieldsets + (
        ('اطلاعات اضافی', {'fields': ('role', 'phone', 'last_login_ip')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('اطلاعات اضافی', {'fields': ('role', 'phone')}),
    )
    search_fields = ['username', 'first_name', 'last_name', 'phone']
    ordering = ['-created_at']