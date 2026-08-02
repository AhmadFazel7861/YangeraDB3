"""
BusinessSettings — singleton model for system configuration.
"""
import uuid
from django.db import models
from apps.core.models import TimeStampedModel

# Fixed UUID used as the singleton PK — always the same row
SETTINGS_UUID = uuid.UUID('00000000-0000-0000-0000-000000000001')


class BusinessSettings(TimeStampedModel):
    """
    Singleton model — only one row ever exists.
    Stores all configurable business info.
    """
    # Business Identity
    business_name     = models.CharField(max_length=200, verbose_name='نام تجاری')
    business_name_en  = models.CharField(max_length=200, blank=True, verbose_name='نام انگلیسی')
    phone1            = models.CharField(max_length=20, blank=True, verbose_name='تلفن اول')
    phone2            = models.CharField(max_length=20, blank=True, verbose_name='تلفن دوم')
    address           = models.TextField(blank=True, verbose_name='آدرس')
    email             = models.EmailField(blank=True, verbose_name='ایمیل')
    website           = models.CharField(max_length=200, blank=True, verbose_name='وبسایت')

    # Logo
    logo = models.ImageField(
        upload_to='settings/',
        null=True, blank=True,
        verbose_name='لوگو'
    )

    # Financial
    default_currency  = models.CharField(
        max_length=10, default='AFN',
        verbose_name='ارز پیش‌فرض'
    )
    low_stock_threshold = models.IntegerField(
        default=10,
        verbose_name='آستانه موجودی کم (روزها)'
    )
    credit_warning_amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        default=50000,
        verbose_name='مبلغ هشدار بدهی'
    )

    # Invoice settings
    invoice_footer_text = models.TextField(
        blank=True,
        default='با تشکر از خرید شما',
        verbose_name='متن پایین فاکتور'
    )
    invoice_show_fifo_cost = models.BooleanField(
        default=False,
        verbose_name='نمایش قیمت تمام شده در فاکتور'
    )

    # System
    backup_reminder_days = models.IntegerField(
        default=1,
        verbose_name='یادآوری بکاپ (روز)'
    )
    log_retention_days = models.IntegerField(
        default=90,
        verbose_name='نگهداری لاگ (روز)'
    )
    designer_credit = models.CharField(
        max_length=100,
        default='YangEra',
        verbose_name='طراح'
    )

    class Meta:
        verbose_name = 'تنظیمات سیستم'
        verbose_name_plural = 'تنظیمات سیستم'
        db_table = 'settings_business'

    def __str__(self):
        return f'تنظیمات — {self.business_name}'

    def save(self, *args, **kwargs):
        # Force the singleton UUID so there is always exactly one row
        self.pk = SETTINGS_UUID
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        """Get or create the singleton settings object."""
        from django.conf import settings as django_settings
        obj, created = cls.objects.get_or_create(
            pk=SETTINGS_UUID,
            defaults={
                'business_name': getattr(
                    django_settings, 'BUSINESS_NAME',
                    'فروشگاه موادغذایی حسیب فیاض'
                ),
                'phone1': getattr(django_settings, 'BUSINESS_PHONE_1', ''),
                'phone2': getattr(django_settings, 'BUSINESS_PHONE_2', ''),
                'address': getattr(django_settings, 'BUSINESS_ADDRESS', ''),
            }
        )
        return obj