"""
Cancels + refunds any PENDING foreign numbers whose expires_at has
passed. Run this on a schedule (e.g. every 5 minutes) so numbers
expire even if nobody has the Foreign Numbers page open.

Usage:
    python manage.py expire_foreign_numbers
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from Business.models import ForeignNumber
from Business.sub_admin_views import _expire_stale_foreign_numbers


class Command(BaseCommand):
    help = "Cancel and refund any pending foreign numbers past their expiry time."

    def handle(self, *args, **options):
        before_count = ForeignNumber.objects.filter(
            status=ForeignNumber.Status.PENDING,
            expires_at__isnull=False,
            expires_at__lte=timezone.now(),
        ).count()

        if before_count == 0:
            self.stdout.write("No expired foreign numbers found.")
            return

        _expire_stale_foreign_numbers()

        self.stdout.write(
            self.style.SUCCESS(f"Expired and refunded {before_count} foreign number(s).")
        )