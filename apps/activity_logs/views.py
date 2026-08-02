"""Activity Log Views — Phase 13"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from .models import ActivityLog


@login_required
def log_list(request):
    """Full activity log with filters."""
    search     = request.GET.get('q', '').strip()
    action_f   = request.GET.get('action', '')
    module_f   = request.GET.get('module', '')
    user_f     = request.GET.get('user', '')
    date_from  = request.GET.get('date_from', '')
    date_to    = request.GET.get('date_to', '')

    qs = ActivityLog.objects.select_related('user').order_by('-created_at')

    if search:
        qs = qs.filter(
            Q(description__icontains=search) |
            Q(username__icontains=search) |
            Q(object_repr__icontains=search)
        )
    if action_f:
        qs = qs.filter(action=action_f)
    if module_f:
        qs = qs.filter(module=module_f)
    if user_f:
        qs = qs.filter(username__icontains=user_f)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    # Stats for last 7 days
    seven_days_ago = timezone.now() - timedelta(days=7)
    stats = ActivityLog.objects.filter(
        created_at__gte=seven_days_ago
    ).values('action').annotate(
        count=Count('id')
    ).order_by('-count')

    # Most active users
    active_users = ActivityLog.objects.filter(
        created_at__gte=seven_days_ago
    ).values('username').annotate(
        count=Count('id')
    ).order_by('-count')[:5]

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'activity_logs/log_list.html', {
        'page_title': 'لاگ فعالیت‌ها',
        'logs': page,
        'search': search,
        'action_f': action_f,
        'module_f': module_f,
        'user_f': user_f,
        'date_from': date_from,
        'date_to': date_to,
        'action_choices': ActivityLog.Action.choices,
        'module_choices': ActivityLog.Module.choices,
        'stats': stats,
        'active_users': active_users,
        'total': paginator.count,
    })