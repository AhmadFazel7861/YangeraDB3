"""Alerts Views — Phase 11"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator

from .models import Alert
from .services import AlertService


@login_required
def alert_list(request):
    """Full alert page with filters."""
    # Refresh alerts on page load
    AlertService.refresh_alerts()

    alert_type = request.GET.get('type', '')
    severity   = request.GET.get('severity', '')
    show_read  = request.GET.get('show_read', '')

    qs = Alert.objects.filter(
        is_deleted=False,
        is_dismissed=False,
    )

    if alert_type:
        qs = qs.filter(alert_type=alert_type)
    if severity:
        qs = qs.filter(severity=severity)
    if not show_read:
        qs = qs.filter(is_read=False)

    # Counts by type
    counts = {
        'total_unread': Alert.objects.filter(
            is_read=False, is_dismissed=False, is_deleted=False
        ).count(),
        'critical': Alert.objects.filter(
            is_read=False, is_dismissed=False,
            is_deleted=False, severity='critical'
        ).count(),
        'warning': Alert.objects.filter(
            is_read=False, is_dismissed=False,
            is_deleted=False, severity='warning'
        ).count(),
    }

    paginator = Paginator(qs.order_by('-created_at'), 25)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'alerts/alert_list.html', {
        'page_title': 'هشدارها',
        'alerts': page,
        'alert_type': alert_type,
        'severity': severity,
        'show_read': show_read,
        'counts': counts,
        'alert_types': Alert.AlertType.choices,
        'severity_choices': Alert.Severity.choices,
        'total': paginator.count,
    })


@login_required
@require_POST
def mark_read(request, pk):
    AlertService.mark_read(pk, user=request.user)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    return redirect('alerts:alert_list')


@login_required
@require_POST
def mark_all_read(request):
    AlertService.mark_all_read(user=request.user)
    messages.success(request, 'همه هشدارها خوانده شدند.')
    return redirect('alerts:alert_list')


@login_required
@require_POST
def dismiss(request, pk):
    AlertService.dismiss(pk)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    return redirect('alerts:alert_list')


@login_required
def get_alert_count(request):
    """AJAX: Get unread alert count for navbar badge."""
    AlertService.refresh_alerts()
    count = AlertService.get_unread_count()
    recent = AlertService.get_recent_alerts(5)
    return JsonResponse({
        'count': count,
        'alerts': [
            {
                'id': str(a.pk),
                'title': a.title,
                'severity': a.severity,
                'url': a.reference_url,
                'time': a.created_at.strftime('%H:%M'),
            }
            for a in recent
        ],
    })


@login_required
def refresh_alerts(request):
    """Manually refresh all alerts."""
    AlertService.refresh_alerts()
    count = AlertService.get_unread_count()
    messages.info(request, f'{count} هشدار فعال وجود دارد.')
    return redirect('alerts:alert_list')