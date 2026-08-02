"""
Management command to clean old activity logs.
Run: python manage.py cleanup_logs
Or schedule with cron/task scheduler.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.conf import settings


class Command(BaseCommand):
    help = 'پاک کردن لاگ‌های قدیمی فعالیت'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=getattr(settings, 'ACTIVITY_LOG_RETENTION_DAYS', 90),
            help='تعداد روزهای نگهداری لاگ (پیش‌فرض: 90)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='فقط تعداد را نشان بده، حذف نکن',
        )

    def handle(self, *args, **options):
        from apps.activity_logs.models import ActivityLog

        days = options['days']
        dry_run = options['dry_run']
        cutoff = timezone.now() - timedelta(days=days)

        old_logs = ActivityLog.objects.filter(created_at__lt=cutoff)
        count = old_logs.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[Dry Run] {count} لاگ قدیمی‌تر از {days} روز یافت شد.'
                )
            )
        else:
            old_logs.delete()
            self.stdout.write(
                self.style.SUCCESS(
                    f'{count} لاگ قدیمی با موفقیت حذف شد.'
                )
            )