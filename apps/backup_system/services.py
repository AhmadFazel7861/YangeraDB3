"""
BackupService — SQLite backup and restore engine.
"""
import os
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.backup_system.models import BackupRecord


class BackupService:

    @staticmethod
    def create_backup(user=None, notes: str = '') -> 'BackupRecord':
        from apps.backup_system.models import BackupRecord

        backup_dir = Path(settings.BACKUP_DIR)
        backup_dir.mkdir(parents=True, exist_ok=True)

        db_path = settings.DATABASES['default']['NAME']
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'YangEraDB_backup_{timestamp}.sqlite3'
        backup_path = backup_dir / filename

        try:
            src_conn = sqlite3.connect(str(db_path))
            dst_conn = sqlite3.connect(str(backup_path))
            with dst_conn:
                src_conn.backup(dst_conn, pages=100)
            src_conn.close()
            dst_conn.close()

            checksum = BackupService._calculate_checksum(backup_path)
            file_size = backup_path.stat().st_size

            record = BackupRecord.objects.create(
                filename=filename,
                file_path=str(backup_path),
                file_size=file_size,
                status=BackupRecord.Status.SUCCESS,
                notes=notes,
                created_by=user,
                checksum=checksum,
            )

            try:
                from apps.activity_logs.services import ActivityLogService
                ActivityLogService.log_backup(record, user=user)
            except Exception:
                pass

            BackupService._cleanup_old_backups()

            try:
                from apps.alerts.models import Alert
                Alert.objects.filter(
                    alert_type='backup',
                    is_dismissed=False,
                ).update(is_dismissed=True)
            except Exception:
                pass

            return record

        except Exception as e:
            try:
                BackupRecord.objects.create(
                    filename=filename,
                    file_path=str(backup_path),
                    file_size=0,
                    status=BackupRecord.Status.FAILED,
                    notes=f'خطا: {str(e)}',
                    created_by=user,
                )
            except Exception:
                pass
            raise ValidationError(f'خطا در ایجاد بکاپ: {str(e)}')

    @staticmethod
    def restore_backup(record: 'BackupRecord', user=None) -> bool:
        """
        Restore database from a backup file.

        IMPORTANT: We update the record BEFORE restoring, because after
        the restore the old DB is replaced and the record's pk may not
        exist in the restored DB — causing 'did not affect any rows'.
        """
        from apps.backup_system.models import BackupRecord

        if not record.file_exists:
            raise ValidationError('فایل بکاپ یافت نشد.')

        if record.checksum:
            current_checksum = BackupService._calculate_checksum(
                Path(record.file_path)
            )
            if current_checksum != record.checksum:
                raise ValidationError(
                    'فایل بکاپ تغییر کرده یا خراب است. بازیابی لغو شد.'
                )

        db_path = Path(settings.DATABASES['default']['NAME'])

        try:
            # Step 1: Safety backup of current DB
            BackupService.create_backup(
                user=user,
                notes='بکاپ خودکار قبل از بازیابی'
            )

            # Step 2: Mark record as restored BEFORE replacing the DB
            # so the UPDATE hits the current live database successfully.
            BackupRecord.objects.filter(pk=record.pk).update(
                status=BackupRecord.Status.RESTORED,
                restored_at=timezone.now(),
                restored_by=user,
            )

            # Step 3: Restore using SQLite Online Backup API
            src_conn = sqlite3.connect(record.file_path)
            dst_conn = sqlite3.connect(str(db_path))
            with dst_conn:
                src_conn.backup(dst_conn, pages=100)
            src_conn.close()
            dst_conn.close()

            try:
                from apps.activity_logs.services import ActivityLogService
                ActivityLogService.log_restore(record, user=user)
            except Exception:
                pass

            return True

        except Exception as e:
            raise ValidationError(f'خطا در بازیابی: {str(e)}')

    @staticmethod
    def validate_backup_file(file_path: str) -> dict:
        try:
            conn = sqlite3.connect(file_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()

            required = ['accounts_user', 'inventory_product', 'sales_invoice']
            missing = [t for t in required if t not in tables]

            if missing:
                return {
                    'valid': False,
                    'error': f'جدول‌های مورد نیاز یافت نشد: {", ".join(missing)}',
                    'tables': tables,
                }

            size = Path(file_path).stat().st_size
            return {
                'valid': True,
                'tables': tables,
                'table_count': len(tables),
                'size': size,
                'size_display': BackupService._format_size(size),
                'error': None,
            }

        except sqlite3.DatabaseError as e:
            return {'valid': False, 'error': f'فایل یک دیتابیس معتبر SQLite نیست: {str(e)}', 'tables': []}
        except Exception as e:
            return {'valid': False, 'error': str(e), 'tables': []}

    @staticmethod
    def get_db_stats() -> dict:
        db_path = Path(settings.DATABASES['default']['NAME'])
        try:
            size = db_path.stat().st_size if db_path.exists() else 0
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            conn.close()
            return {
                'size': size,
                'size_display': BackupService._format_size(size),
                'table_count': len(tables),
                'db_path': str(db_path),
                'exists': db_path.exists(),
            }
        except Exception as e:
            return {'size': 0, 'size_display': '—', 'table_count': 0, 'error': str(e)}

    @staticmethod
    def _calculate_checksum(file_path: Path) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f'{size} B'
        elif size < 1024 * 1024:
            return f'{size / 1024:.1f} KB'
        else:
            return f'{size / (1024 * 1024):.2f} MB'

    @staticmethod
    def _cleanup_old_backups():
        from apps.backup_system.models import BackupRecord
        keep = getattr(settings, 'BACKUP_KEEP_LAST', 30)
        old_records = BackupRecord.objects.filter(
            status=BackupRecord.Status.SUCCESS,
            is_deleted=False,
        ).order_by('-created_at')[keep:]

        for record in old_records:
            try:
                if os.path.exists(record.file_path):
                    os.remove(record.file_path)
                record.is_deleted = True
                record.deleted_at = timezone.now()
                record.save(update_fields=['is_deleted', 'deleted_at'])
            except Exception:
                pass