"""
Decorators for activity logging in views.
"""
import functools
from .services import ActivityLogService


def log_activity(action, module, description_func=None):
    """
    Decorator to log view activity.

    Usage:
    @log_activity('create', 'sales', lambda req, *a, **kw: 'فاکتور جدید ثبت شد')
    def my_view(request, ...):
        ...
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            response = view_func(request, *args, **kwargs)

            # Only log on successful POST
            if (
                request.method == 'POST'
                and hasattr(response, 'status_code')
                and response.status_code in (200, 302)
            ):
                desc = (
                    description_func(request, *args, **kwargs)
                    if callable(description_func)
                    else str(description_func or action)
                )
                ActivityLogService.log(
                    action=action,
                    module=module,
                    description=desc,
                    user=getattr(request, 'user', None),
                    request=request,
                )

            return response
        return wrapper
    return decorator