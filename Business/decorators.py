import functools
from django.shortcuts import render
from Business.models import ServiceLock


def check_lock(service_name):
    """
    Decorator factory. Wraps a sub-admin view and shows the "locked" page
    instead of running the view if the service (or the whole platform) is locked.

    Usage: @check_lock('buy_logs')
    """
    def decorator(view_func):
        @functools.wraps(view_func)  # keeps view name/docstring intact for Django's URL resolver
        def wrapper(request, *args, **kwargs):
            locked, reason = ServiceLock.is_service_locked(service_name)
            print(f"[check_lock] service={service_name} locked={locked} reason={reason!r}")
            if locked:
               return render(request, "admin/subadmin/service_locked.html", {
                  "reason": reason,
                  "service": service_name,
                }, status=423)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator