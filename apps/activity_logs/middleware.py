"""
Activity Log Middleware — captures important HTTP operations.
Only logs POST requests that mutate data (not GET).
"""
from .services import ActivityLogService


class ActivityLogMiddleware:
    """
    Lightweight middleware — logs important POST actions automatically.
    Fine-grained logging is done in services/views directly.
    """

    # URL patterns that trigger automatic logging
    LOG_PATTERNS = {
        '/accounts/login/': ('login', 'accounts', 'ورود به سیستم'),
        '/accounts/logout/': ('logout', 'accounts', 'خروج از سیستم'),
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only log successful POST requests
        if request.method == 'POST' and response.status_code in (200, 302):
            path = request.path
            if path in self.LOG_PATTERNS:
                action, module, description = self.LOG_PATTERNS[path]
                user = getattr(request, 'user', None)
                if user and getattr(user, 'is_authenticated', False):
                    ActivityLogService.log(
                        action=action,
                        module=module,
                        description=description,
                        user=user,
                        request=request,
                    )

        return response