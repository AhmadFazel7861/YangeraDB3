"""
AlertService — generates and manages system alerts.
Called on page load via context processor.
"""
from decimal import Decimal
from django.utils import timezone
from django.db import transaction

from .models import Alert


class AlertService:

    @staticmethod
    def refresh_alerts():
        """
        Main entry point. Regenerates all dynamic alerts.
        Called periodically or on dashboard load.
        Deletes old unread alerts of same type before creating new ones.
        """
        AlertService._check_low_stock()
        AlertService._check_expiring_batches()
        AlertService._check_customer_debts()
        AlertService._check_supplier_debts()
        AlertService._check_backup_reminder()

    @staticmethod
    def get_unread_count():
        """Fast count of unread, undismissed alerts."""
        return Alert.objects.filter(
            is_read=False,
            is_dismissed=False,
            is_deleted=False,
        ).count()

    @staticmethod
    def get_recent_alerts(limit=10):
        """Get recent unread alerts for navbar dropdown."""
        return Alert.objects.filter(
            is_dismissed=False,
            is_deleted=False,
        ).order_by('-created_at')[:limit]

    @staticmethod
    @transaction.atomic
    def mark_read(alert_id, user=None):
        """Mark a single alert as read."""
        try:
            alert = Alert.objects.get(pk=alert_id, is_deleted=False)
            alert.is_read = True
            alert.read_by = user
            alert.read_at = timezone.now()
            alert.save(update_fields=[
                'is_read', 'read_by', 'read_at', 'updated_at'
            ])
            return True
        except Alert.DoesNotExist:
            return False

    @staticmethod
    @transaction.atomic
    def mark_all_read(user=None):
        """Mark all unread alerts as read."""
        Alert.objects.filter(
            is_read=False,
            is_dismissed=False,
            is_deleted=False,
        ).update(
            is_read=True,
            read_by=user,
            read_at=timezone.now(),
        )

    @staticmethod
    @transaction.atomic
    def dismiss(alert_id):
        """Dismiss (hide) an alert permanently."""
        try:
            alert = Alert.objects.get(pk=alert_id, is_deleted=False)
            alert.is_dismissed = True
            alert.save(update_fields=['is_dismissed', 'updated_at'])
            return True
        except Alert.DoesNotExist:
            return False

    # ══════════════════════════════════════════════════════════
    # PRIVATE: CHECK METHODS
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _check_low_stock():
        """Generate alerts for low/out-of-stock products."""
        try:
            from apps.inventory.models import Product
            from django.db.models import F

            # Clear existing stock alerts
            Alert.objects.filter(
                alert_type__in=[
                    Alert.AlertType.LOW_STOCK,
                    Alert.AlertType.OUT_OF_STOCK,
                ],
                is_dismissed=False,
                is_read=False,
            ).delete()

            # Out of stock
            out_stock = Product.objects.filter(
                is_deleted=False,
                is_active=True,
                current_stock__lte=0,
            )
            for product in out_stock:
                Alert.objects.create(
                    alert_type=Alert.AlertType.OUT_OF_STOCK,
                    severity=Alert.Severity.CRITICAL,
                    title=f'محصول ناموجود: {product.name}',
                    message=(
                        f'موجودی «{product.name}» به صفر رسیده است. '
                        f'سفارش جدید دهید.'
                    ),
                    reference_id=str(product.pk),
                    reference_url=f'/inventory/products/{product.pk}/',
                )

            # Low stock
            low_stock = Product.objects.filter(
                is_deleted=False,
                is_active=True,
                minimum_stock__gt=0,
                current_stock__gt=0,
                current_stock__lte=F('minimum_stock'),
            )
            for product in low_stock:
                Alert.objects.create(
                    alert_type=Alert.AlertType.LOW_STOCK,
                    severity=Alert.Severity.WARNING,
                    title=f'موجودی کم: {product.name}',
                    message=(
                        f'موجودی «{product.name}» به '
                        f'{product.current_stock:,.3f} رسیده است. '
                        f'حداقل: {product.minimum_stock:,.3f}'
                    ),
                    reference_id=str(product.pk),
                    reference_url=f'/inventory/products/{product.pk}/',
                )
        except Exception:
            pass

    @staticmethod
    def _check_expiring_batches():
        """Generate alerts for expiring/expired batches."""
        try:
            from apps.warehouse.services import WarehouseValuationService

            Alert.objects.filter(
                alert_type__in=[
                    Alert.AlertType.EXPIRY_WARNING,
                    Alert.AlertType.EXPIRED,
                ],
                is_dismissed=False,
                is_read=False,
            ).delete()

            # Expiring soon
            expiring = WarehouseValuationService.get_expiring_batches(30)
            for batch in expiring:
                Alert.objects.create(
                    alert_type=Alert.AlertType.EXPIRY_WARNING,
                    severity=Alert.Severity.WARNING,
                    title=f'انقضای نزدیک: {batch.product.name}',
                    message=(
                        f'بچ {batch.batch_number} از محصول '
                        f'«{batch.product.name}» در '
                        f'{batch.days_until_expiry} روز دیگر منقضی می‌شود. '
                        f'موجودی: {batch.remaining_quantity:,.3f} '
                        f'{batch.product.unit.abbreviation}'
                    ),
                    reference_id=str(batch.pk),
                    reference_url=f'/warehouse/{batch.warehouse.pk}/',
                )

            # Already expired
            expired = WarehouseValuationService.get_expired_batches()
            for batch in expired:
                Alert.objects.create(
                    alert_type=Alert.AlertType.EXPIRED,
                    severity=Alert.Severity.CRITICAL,
                    title=f'محصول منقضی: {batch.product.name}',
                    message=(
                        f'بچ {batch.batch_number} از محصول '
                        f'«{batch.product.name}» منقضی شده است! '
                        f'موجودی باقی‌مانده: {batch.remaining_quantity:,.3f}'
                    ),
                    reference_id=str(batch.pk),
                    reference_url=f'/warehouse/{batch.warehouse.pk}/',
                )
        except Exception:
            pass

    @staticmethod
    def _check_customer_debts():
        """Generate alerts for high customer debts."""
        try:
            from apps.customers.models import Customer
            from django.db.models import Sum

            Alert.objects.filter(
                alert_type=Alert.AlertType.CUSTOMER_DEBT,
                is_dismissed=False,
                is_read=False,
            ).delete()

            # Alert for customers with significant debt
            customers = Customer.objects.filter(
                is_deleted=False,
                is_active=True,
                total_debt__gt=0,
            ).order_by('-total_debt')[:20]

            for customer in customers:
                Alert.objects.create(
                    alert_type=Alert.AlertType.CUSTOMER_DEBT,
                    severity=(
                        Alert.Severity.CRITICAL
                        if customer.total_debt > 50000
                        else Alert.Severity.WARNING
                    ),
                    title=f'بدهی مشتری: {customer.name}',
                    message=(
                        f'مشتری «{customer.name}» '
                        f'{customer.total_debt:,.0f} افغانی بدهکار است.'
                    ),
                    reference_id=str(customer.pk),
                    reference_url=f'/customers/{customer.pk}/',
                )
        except Exception:
            pass

    @staticmethod
    def _check_supplier_debts():
        """Generate alerts for supplier debts we owe."""
        try:
            from apps.suppliers.models import Supplier

            Alert.objects.filter(
                alert_type=Alert.AlertType.SUPPLIER_DEBT,
                is_dismissed=False,
                is_read=False,
            ).delete()

            suppliers = Supplier.objects.filter(
                is_deleted=False,
                is_active=True,
                total_debt__gt=0,
            ).order_by('-total_debt')[:10]

            for supplier in suppliers:
                Alert.objects.create(
                    alert_type=Alert.AlertType.SUPPLIER_DEBT,
                    severity=(
                        Alert.Severity.CRITICAL
                        if supplier.total_debt > 100000
                        else Alert.Severity.WARNING
                    ),
                    title=f'بدهی به تامین‌کننده: {supplier.name}',
                    message=(
                        f'ما {supplier.total_debt:,.0f} افغانی به '
                        f'«{supplier.name}» بدهکار هستیم.'
                    ),
                    reference_id=str(supplier.pk),
                    reference_url=f'/suppliers/{supplier.pk}/',
                )
        except Exception:
            pass

    @staticmethod
    def _check_backup_reminder():
        """Remind user to take backup if no backup in 7 days."""
        try:
            from datetime import timedelta

            Alert.objects.filter(
                alert_type=Alert.AlertType.BACKUP_REMINDER,
                is_dismissed=False,
                is_read=False,
            ).delete()

            # Check last backup (Phase 12 will implement actual backup tracking)
            # For now, create a daily reminder
            today = timezone.now().date()
            last_backup_alert = Alert.objects.filter(
                alert_type=Alert.AlertType.BACKUP_REMINDER,
            ).order_by('-created_at').first()

            if not last_backup_alert or (
                today - last_backup_alert.created_at.date()
            ).days >= 1:
                Alert.objects.create(
                    alert_type=Alert.AlertType.BACKUP_REMINDER,
                    severity=Alert.Severity.INFO,
                    title='یادآوری: گرفتن بکاپ',
                    message=(
                        'لطفاً از دیتابیس سیستم بکاپ بگیرید. '
                        'بکاپ منظم از از دست رفتن اطلاعات جلوگیری می‌کند.'
                    ),
                    reference_url='/backups/',
                )
        except Exception:
            pass