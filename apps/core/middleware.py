import zoneinfo
from django.utils import timezone
from django.conf import settings


class TimezoneMiddleware:
    """Activate Afghanistan timezone for every request."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tz = zoneinfo.ZoneInfo(settings.TIME_ZONE)
        timezone.activate(tz)
        return self.get_response(request)


class ActivityLogMiddleware:
    """Placeholder for activity logging — implemented fully in Phase 13."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)