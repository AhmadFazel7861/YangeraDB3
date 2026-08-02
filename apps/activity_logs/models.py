"""
Activity Log Models — Phase 13
"""
import uuid
from django.db import models
from django.conf import settings


class ActivityLog(models.Model):
    """
    Immutable audit log entry.
    Never edited after creation.
    """

    class Action(models.TextChoices):
        CREATE   = 'create',   'ایجاد'
        UPDATE   = 'update',   'ویرایش'
        DELETE   = 'delete',   'حذف'
        LOGIN    = 'login',    'ورود'
        LOGOUT   = 'logout',   'خروج'
        VIEW     = 'view',     'مشاهده'
        PRINT    = 'print',    'پرینت'
        EXPORT   = 'export',   'خروجی'
        PAYMENT  = 'payment',  'پرداخت'
        BACKUP   = 'backup',   'بکاپ'
        RESTORE  = 'restore',  'بازیابی'
        ADJUST   = 'adjust',   'تعدیل'
        CANCEL   = 'cancel',   'لغو'
        APPROVE  = 'approve',  'تایید'

    class Module(models.TextChoices):
        INVENTORY  = 'inventory',  'موجودی'
        WAREHOUSE  = 'warehouse',  'انبار'
        SALES      = 'sales',      'فروش'
        PURCHASES  = 'purchases',  'خریداری'
        CUSTOMERS  = 'customers',  'مشتریان'
        SUPPLIERS  = 'suppliers',  'تامین‌کنندگان'
        EXPENSES   = 'expenses',   'مصارف'
        CURRENCY   = 'currency',   'ارز'
        SARAFI     = 'sarafi',     'صرافی'
        ACCOUNTS   = 'accounts',   'حساب‌ها'
        BACKUPS    = 'backups',    'بکاپ'
        SYSTEM     = 'system',     'سیستم'

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name='زمان'
    )

    # Who
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='activity_logs',
        verbose_name='کاربر'
    )
    username = models.CharField(
        max_length=150, blank=True,
        verbose_name='نام کاربری'
    )

    # What
    action = models.CharField(
        max_length=20,
        choices=Action.choices,
        verbose_name='عملیات'
    )
    module = models.CharField(
        max_length=30,
        choices=Module.choices,
        verbose_name='ماژول'
    )
    description = models.TextField(
        verbose_name='توضیحات'
    )

    # Reference
    model_name = models.CharField(
        max_length=100, blank=True,
        verbose_name='مدل'
    )
    object_id = models.CharField(
        max_length=100, blank=True,
        verbose_name='شناسه شیء'
    )
    object_repr = models.CharField(
        max_length=300, blank=True,
        verbose_name='نمایش شیء'
    )

    # Context
    ip_address = models.GenericIPAddressField(
        null=True, blank=True,
        verbose_name='آدرس IP'
    )
    user_agent = models.CharField(
        max_length=500, blank=True,
        verbose_name='مرورگر'
    )
    extra_data = models.JSONField(
        default=dict, blank=True,
        verbose_name='اطلاعات اضافی'
    )

    class Meta:
        verbose_name = 'لاگ فعالیت'
        verbose_name_plural = 'لاگ‌های فعالیت'
        db_table = 'activity_log'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action']),
            models.Index(fields=['module']),
            models.Index(fields=['model_name', 'object_id']),
        ]

    def __str__(self):
        return (
            f'{self.username} | '
            f'{self.get_action_display()} | '
            f'{self.description[:50]}'
        )

    @property
    def action_color(self):
        return {
            'create':  'success',
            'update':  'warning',
            'delete':  'danger',
            'login':   'info',
            'logout':  'secondary',
            'payment': 'success',
            'backup':  'info',
            'restore': 'warning',
            'cancel':  'danger',
        }.get(self.action, 'gray')

    @property
    def action_icon(self):
        return {
            'create':  'bi-plus-circle-fill',
            'update':  'bi-pencil-fill',
            'delete':  'bi-trash-fill',
            'login':   'bi-box-arrow-in-right',
            'logout':  'bi-box-arrow-left',
            'payment': 'bi-cash-coin',
            'backup':  'bi-cloud-arrow-down-fill',
            'restore': 'bi-arrow-counterclockwise',
            'cancel':  'bi-x-circle-fill',
            'print':   'bi-printer-fill',
            'adjust':  'bi-sliders',
        }.get(self.action, 'bi-activity')