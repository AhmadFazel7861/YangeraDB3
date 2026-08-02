from django.contrib import admin
from .models import BackupRecord


@admin.register(BackupRecord)
class BackupRecordAdmin(admin.ModelAdmin):
    list_display = [
        'filename', 'file_size_display',
        'status', 'created_by', 'created_at'
    ]
    list_filter = ['status']
    readonly_fields = [
        'filename', 'file_path', 'file_size',
        'checksum', 'created_at', 'updated_at'
    ]