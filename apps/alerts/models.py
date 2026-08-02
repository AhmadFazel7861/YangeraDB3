"""
Alert Models — Phase 11
"""
import uuid
from django.db import models
from django.conf import settings
from apps.core.models import BaseModel


class Alert(BaseModel):
    """
    System-generated alert for the user.
    Alerts are regenerated on each check — they are not permanent records.
    """

    class AlertType(models.TextChoices):
        LOW_STOCK      = 'low_stock',      'موجودی کم'
        OUT_OF_STOCK   = 'out_of_stock',   'ناموجود'
        EXPIRY_WARNING = 'expiry_warning', 'هشدار انقضا'
        EXPIRED        = 'expired',        'منقضی شده'
        CUSTOMER_DEBT  = 'customer_debt',  'بدهی مشتری'
        SUPPLIER_DEBT  = 'supplier_debt',  'بدهی تامین‌کننده'
        BACKUP_REMINDER = 'backup',        'یادآوری بکاپ'

    class Severity(models.TextChoices):
        INFO     = 'info',    'اطلاعات'
        WARNING  = 'warning', 'هشدار'
        CRITICAL = 'critical','بحرانی'

    alert_type = models.CharField(
        max_length=30,
        choices=AlertType.choices,
        verbose_name='نوع هشدار'
    )
    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.WARNING,
        verbose_name='شدت'
    )
    title = models.CharField(
        max_length=200,
        verbose_name='عنوان'
    )
    message = models.TextField(
        verbose_name='پیام'
    )
    # Reference to related object
    reference_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='شناسه مرجع'
    )
    reference_url = models.CharField(
        max_length=300,
        blank=True,
        verbose_name='لینک مرجع'
    )
    is_read = models.BooleanField(
        default=False,
        verbose_name='خوانده شده'
    )
    is_dismissed = models.BooleanField(
        default=False,
        verbose_name='رد شده'
    )
    read_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='read_alerts',
        verbose_name='خوانده شده توسط'
    )
    read_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name='زمان خواندن'
    )

    class Meta:
        verbose_name = 'هشدار'
        verbose_name_plural = 'هشدارها'
        db_table = 'alerts_alert'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['alert_type']),
            models.Index(fields=['severity']),
            models.Index(fields=['is_read']),
            models.Index(fields=['is_dismissed']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f'[{self.get_severity_display()}] {self.title}'

    @property
    def severity_color(self):
        return {
            'info':     'info',
            'warning':  'warning',
            'critical': 'danger',
        }.get(self.severity, 'info')

    @property
    def severity_icon(self):
        return {
            'info':     'bi-info-circle-fill',
            'warning':  'bi-exclamation-triangle-fill',
            'critical': 'bi-x-octagon-fill',
        }.get(self.severity, 'bi-bell-fill')