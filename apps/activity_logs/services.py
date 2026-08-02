"""
ActivityLogService — centralized logging engine.
"""
from django.utils import timezone
from django.conf import settings
 
 
class ActivityLogService:
 
    @staticmethod
    def log(
        action: str,
        module: str,
        description: str,
        user=None,
        model_name: str = '',
        object_id: str = '',
        object_repr: str = '',
        ip_address: str = None,
        user_agent: str = '',
        extra_data: dict = None,
        request=None,
    ):
        """
        Create an activity log entry.
        Always silently fails — never breaks the main operation.
        """
        if not getattr(settings, 'ACTIVITY_LOG_ENABLED', True):
            return
 
        try:
            from .models import ActivityLog
 
            # Extract user info from request if provided
            if request and not user:
                user = getattr(request, 'user', None)
                if user and not user.is_authenticated:
                    user = None
 
            if request and not ip_address:
                ip_address = ActivityLogService._get_ip(request)
            if request and not user_agent:
                user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
 
            username = ''
            if user:
                try:
                    username = user.username
                except Exception:
                    pass
 
            ActivityLog.objects.create(
                user=user if user and getattr(user, 'is_authenticated', False) else None,
                username=username,
                action=action,
                module=module,
                description=description,
                model_name=model_name,
                object_id=str(object_id),
                object_repr=str(object_repr)[:300],
                ip_address=ip_address,
                user_agent=user_agent[:500],
                extra_data=extra_data or {},
            )
        except Exception:
            pass  # Never let logging break the application
 
    @staticmethod
    def log_invoice_created(invoice, user=None, request=None):
        ActivityLogService.log(
            action='create',
            module='sales',
            description=(
                f'فاکتور فروش {invoice.invoice_number} '
                f'برای مشتری «{invoice.customer.name}» '
                f'به مبلغ {invoice.total_amount:,.0f} ؋ ثبت شد.'
            ),
            user=user,
            model_name='Invoice',
            object_id=str(invoice.pk),
            object_repr=str(invoice),
            request=request,
        )
 
    @staticmethod
    def log_invoice_cancelled(invoice, user=None, request=None):
        ActivityLogService.log(
            action='cancel',
            module='sales',
            description=(
                f'فاکتور فروش {invoice.invoice_number} '
                f'لغو شد و موجودی برگشت داده شد.'
            ),
            user=user,
            model_name='Invoice',
            object_id=str(invoice.pk),
            object_repr=str(invoice),
            request=request,
        )
 
    @staticmethod
    def log_payment(payment_type, amount, reference, user=None, request=None):
        ActivityLogService.log(
            action='payment',
            module='sales',
            description=(
                f'پرداخت {amount:,.0f} ؋ — {payment_type}: {reference}'
            ),
            user=user,
            request=request,
        )
 
    @staticmethod
    def log_stock_adjustment(product, qty, movement_type, user=None, request=None):
        ActivityLogService.log(
            action='adjust',
            module='inventory',
            description=(
                f'تعدیل موجودی «{product.name}»: '
                f'{qty:+.3f} ({movement_type})'
            ),
            user=user,
            model_name='Product',
            object_id=str(product.pk),
            object_repr=product.name,
            request=request,
        )
 
    @staticmethod
    def log_purchase_created(invoice, user=None, request=None):
        ActivityLogService.log(
            action='create',
            module='purchases',
            description=(
                f'فاکتور خرید {invoice.invoice_number} '
                f'از تامین‌کننده «{invoice.supplier.name}» '
                f'به مبلغ {invoice.total_amount:,.0f} ؋ ثبت شد.'
            ),
            user=user,
            model_name='PurchaseInvoice',
            object_id=str(invoice.pk),
            object_repr=str(invoice),
            request=request,
        )
 
    @staticmethod
    def log_login(user, request=None):
        ActivityLogService.log(
            action='login',
            module='accounts',
            description=f'کاربر «{user.username}» وارد سیستم شد.',
            user=user,
            model_name='User',
            object_id=str(user.pk),
            object_repr=user.username,
            request=request,
        )
 
    @staticmethod
    def log_logout(user, request=None):
        ActivityLogService.log(
            action='logout',
            module='accounts',
            description=f'کاربر «{user.username}» از سیستم خارج شد.',
            user=user,
            model_name='User',
            object_id=str(user.pk),
            object_repr=user.username,
            request=request,
        )
 
    @staticmethod
    def log_backup(backup_record, user=None, request=None):
        ActivityLogService.log(
            action='backup',
            module='backups',
            description=(
                f'بکاپ «{backup_record.filename}» '
                f'({backup_record.file_size_display}) ایجاد شد.'
            ),
            user=user,
            model_name='BackupRecord',
            object_id=str(backup_record.pk),
            object_repr=backup_record.filename,
            request=request,
        )
 
    @staticmethod
    def log_restore(backup_record, user=None, request=None):
        ActivityLogService.log(
            action='restore',
            module='backups',
            description=(
                f'دیتابیس از بکاپ «{backup_record.filename}» '
                f'بازیابی شد.'
            ),
            user=user,
            model_name='BackupRecord',
            object_id=str(backup_record.pk),
            object_repr=backup_record.filename,
            request=request,
        )
 
    @staticmethod
    def _get_ip(request) -> str:
        """Extract real IP from request."""
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')
 
    @staticmethod
    def get_user_activity(user, limit=50):
        from .models import ActivityLog
        return ActivityLog.objects.filter(
            user=user
        ).order_by('-created_at')[:limit]
 
    @staticmethod
    def get_recent_activity(limit=100):
        from .models import ActivityLog
        return ActivityLog.objects.select_related(
            'user'
        ).order_by('-created_at')[:limit]
 