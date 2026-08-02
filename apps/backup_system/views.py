"""Backup Views — Phase 12"""
import os
from pathlib import Path

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import FileResponse, Http404
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import BackupRecord
from .services import BackupService


@login_required
def backup_list(request):
    """Main backup page."""
    backups = BackupRecord.objects.filter(
        is_deleted=False
    ).select_related('created_by', 'restored_by')

    db_stats = BackupService.get_db_stats()

    # Last successful backup
    last_backup = BackupRecord.objects.filter(
        status=BackupRecord.Status.SUCCESS,
        is_deleted=False,
    ).first()

    return render(request, 'backups/backup_list.html', {
        'page_title': 'بکاپ و بازیابی',
        'backups': backups,
        'db_stats': db_stats,
        'last_backup': last_backup,
    })


@login_required
@require_POST
def create_backup(request):
    """Create a new backup."""
    notes = request.POST.get('notes', '')
    try:
        record = BackupService.create_backup(
            user=request.user,
            notes=notes,
        )
        messages.success(
            request,
            f'بکاپ با موفقیت ایجاد شد: {record.filename} '
            f'({record.file_size_display})'
        )
    except Exception as e:
        messages.error(request, str(e))
    return redirect('backups:backup_list')


@login_required
def download_backup(request, pk):
    """Download a backup file."""
    record = get_object_or_404(BackupRecord, pk=pk, is_deleted=False)

    if not record.file_exists:
        messages.error(request, 'فایل بکاپ روی دیسک یافت نشد.')
        return redirect('backups:backup_list')

    try:
        response = FileResponse(
            open(record.file_path, 'rb'),
            content_type='application/octet-stream',
        )
        response['Content-Disposition'] = (
            f'attachment; filename="{record.filename}"'
        )
        response['Content-Length'] = record.file_size
        return response
    except Exception as e:
        messages.error(request, f'خطا در دانلود: {str(e)}')
        return redirect('backups:backup_list')


@login_required
@require_POST
def restore_backup(request, pk):
    """Restore database from a backup."""
    record = get_object_or_404(BackupRecord, pk=pk, is_deleted=False)

    # Require confirmation text
    confirm = request.POST.get('confirm_text', '')
    if confirm != 'بازیابی':
        messages.error(
            request,
            'تایید نادرست است. کلمه «بازیابی» را وارد کنید.'
        )
        return redirect('backups:backup_list')

    try:
        BackupService.restore_backup(record, user=request.user)
        messages.success(
            request,
            f'دیتابیس از بکاپ {record.filename} با موفقیت بازیابی شد. '
            f'لطفاً سیستم را ریستارت کنید.'
        )
    except Exception as e:
        messages.error(request, str(e))
    return redirect('backups:backup_list')


@login_required
@require_POST
def delete_backup(request, pk):
    """Delete a backup record and file."""
    record = get_object_or_404(BackupRecord, pk=pk, is_deleted=False)
    filename = record.filename

    try:
        if record.file_exists:
            os.remove(record.file_path)
        record.is_deleted = True
        record.deleted_at = timezone.now()
        record.save(update_fields=['is_deleted', 'deleted_at'])
        messages.success(request, f'بکاپ «{filename}» حذف شد.')
    except Exception as e:
        messages.error(request, str(e))

    return redirect('backups:backup_list')


@login_required
def upload_restore(request):
    """Upload a backup file and restore from it."""
    if request.method == 'POST':
        uploaded = request.FILES.get('backup_file')
        if not uploaded:
            messages.error(request, 'فایلی انتخاب نشده است.')
            return redirect('backups:backup_list')

        # Check file extension
        if not uploaded.name.endswith(('.sqlite3', '.db', '.sqlite')):
            messages.error(
                request,
                'فرمت فایل نامعتبر است. فقط فایل‌های SQLite قابل قبول هستند.'
            )
            return redirect('backups:backup_list')

        # Save temporarily
        import tempfile
        with tempfile.NamedTemporaryFile(
            suffix='.sqlite3', delete=False
        ) as tmp:
            for chunk in uploaded.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            # Validate
            validation = BackupService.validate_backup_file(tmp_path)
            if not validation['valid']:
                messages.error(
                    request,
                    f'فایل بکاپ معتبر نیست: {validation["error"]}'
                )
                os.unlink(tmp_path)
                return redirect('backups:backup_list')

            # Confirm text required
            confirm = request.POST.get('confirm_text', '')
            if confirm != 'بازیابی':
                # Show validation result, ask for confirmation
                return render(request, 'backups/confirm_restore.html', {
                    'page_title': 'تایید بازیابی',
                    'validation': validation,
                    'tmp_path': tmp_path,
                    'filename': uploaded.name,
                })

            # Move to backup dir and create record
            from pathlib import Path
            from django.conf import settings
            import shutil

            backup_dir = Path(settings.BACKUP_DIR)
            dest = backup_dir / f'upload_{uploaded.name}'
            shutil.move(tmp_path, str(dest))

            # Create record
            checksum = BackupService._calculate_checksum(dest)
            record = BackupRecord.objects.create(
                filename=uploaded.name,
                file_path=str(dest),
                file_size=dest.stat().st_size,
                status=BackupRecord.Status.SUCCESS,
                notes='آپلود دستی',
                created_by=request.user,
                checksum=checksum,
            )

            BackupService.restore_backup(record, user=request.user)
            messages.success(
                request,
                'دیتابیس با موفقیت بازیابی شد. لطفاً سیستم را ریستارت کنید.'
            )

        except Exception as e:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            messages.error(request, str(e))

    return redirect('backups:backup_list')