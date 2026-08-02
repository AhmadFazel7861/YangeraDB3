from django.contrib import admin
from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'username', 'action',
        'module', 'description', 'ip_address'
    ]
    list_filter = ['action', 'module', 'created_at']
    search_fields = ['username', 'description', 'object_repr']
    readonly_fields = [
        'id', 'created_at', 'user', 'username',
        'action', 'module', 'description',
        'model_name', 'object_id', 'object_repr',
        'ip_address', 'user_agent', 'extra_data',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser