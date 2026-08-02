import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model for the ERP system.
    Extends Django's AbstractUser with role-based access.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Role(models.TextChoices):
        ADMIN = 'admin', 'مدیر سیستم'
        MANAGER = 'manager', 'مدیر'
        CASHIER = 'cashier', 'صندوقدار'
        WAREHOUSE = 'warehouse', 'انباردار'
        VIEWER = 'viewer', 'مشاهده‌گر'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CASHIER,
        verbose_name='نقش'
    )
    phone = models.CharField(max_length=15, blank=True, verbose_name='شماره تلفن')
    is_active = models.BooleanField(default=True, verbose_name='فعال')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = 'کاربر'
        verbose_name_plural = 'کاربران'
        db_table = 'accounts_user'

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.get_role_display()})'

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def display_name(self):
        return self.get_full_name() or self.username