# ══════════════════════════════════════════════════════════════════
#  ADD TO Business/context_processors.py  (create the file if it
#  doesn't exist yet)
#
#  Makes `unread_notifications` available in every template without
#  each view having to pass it in manually — that's what your
#  base.html topbar's {% if unread_notifications %} relies on.
# ══════════════════════════════════════════════════════════════════

from .models import Notification, NotificationRead, User


def unread_notifications(request):
    """
    Returns the unread notification count for the logged-in sub-admin.
    Safe no-op for anonymous users, super admins, or staff — the bell
    dot only makes sense on the sub-admin side.
    """
    user = getattr(request, "user", None)

    if not user or not user.is_authenticated or user.role != User.Role.SUB_ADMIN:
        return {"unread_notifications": 0}

    unread_private = Notification.objects.filter(
        recipient=user, is_read=False
    ).count()

    read_public_ids = NotificationRead.objects.filter(
        user=user
    ).values_list("notification_id", flat=True)

    unread_public = Notification.objects.filter(
        is_public=True, recipient__isnull=True
    ).exclude(id__in=read_public_ids).count()

    return {"unread_notifications": unread_private + unread_public}