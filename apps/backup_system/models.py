"""
Backup Models — Phase 12
BackupRecord
"""
from decimal import Decimal
from django.db import models
from django.conf import settings
from apps.core.models import BaseModel


class BackupRecord(BaseModel):
    """Record of each backup operation."""

    class Status(models.TextChoices):
        SUCCESS  = 'success',  'موفق'
        FAILED   = 'failed',   'ناموفق'
        RESTORED = 'restored', 'بازیابی شده'

    filename = models.CharField(
        max_length=255,
        verbose_name='نام فایل'
    )
    file_path = models.CharField(
        max_length=500,
        verbose_name='مسیر فایل'
    )
    file_size = models.BigIntegerField(
        default=0,
        verbose_name='حجم فایل (بایت)'
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUCCESS,
        verbose_name='وضعیت'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='یادداشت'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='backups_created',
        verbose_name='توسط'
    )
    restored_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name='زمان بازیابی'
    )
    restored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='backups_restored',
        verbose_name='بازیابی توسط'
    )
    checksum = models.CharField(
        max_length=64,
        blank=True,
        verbose_name='چکسام SHA256'
    )

    class Meta:
        verbose_name = 'بکاپ'
        verbose_name_plural = 'بکاپ‌ها'
        db_table = 'backups_record'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.filename} — {self.created_at.strftime("%Y/%m/%d %H:%M")}'

    @property
    def file_size_display(self):
        """Human readable file size."""
        size = self.file_size
        if size < 1024:
            return f'{size} B'
        elif size < 1024 * 1024:
            return f'{size / 1024:.1f} KB'
        else:
            return f'{size / (1024 * 1024):.2f} MB'

    @property
    def file_exists(self):
        """Check if backup file still exists on disk."""
        import os
        return os.path.exists(self.file_path)