"""
Core abstract models — used across all apps.
"""
import uuid
from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base with UUID, created_at, updated_at."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')

    class Meta:
        abstract = True
        ordering = ['-created_at']


class SoftDeleteModel(models.Model):
    """Abstract soft-delete support."""
    is_deleted = models.BooleanField(default=False, verbose_name='حذف شده')
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name='تاریخ حذف')

    class Meta:
        abstract = True


class BaseModel(TimeStampedModel, SoftDeleteModel):
    """Full base model: UUID + timestamps + soft delete."""
    class Meta:
        abstract = True
        ordering = ['-created_at']