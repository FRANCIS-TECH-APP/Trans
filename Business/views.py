import json
import uuid
from datetime import date

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.conf import settings
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.core.paginator import Paginator

from .models import (
    User, Shipment, ContactInfo, ShipmentImage,
    TransitCheckpoint, Payment,
)


# ════════════════════════════════════════════════════════
#  DECORATORS
# ════════════════════════════════════════════════════════

def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("admin-login")
        if request.user.role not in (User.Role.ADMIN, User.Role.STAFF):
            messages.error(request, "Access denied.")
            return redirect("admin-login")
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


# ════════════════════════════════════════════════════════
#  PUBLIC — TRACKING PORTAL
# ════════════════════════════════════════════════════════

def home(request):
    return render(request, "public/home.html")
def tracking_search(request):
    if request.method == "POST":
        tracking_id = request.POST.get("tracking_id", "").strip().upper()
        shipment = Shipment.objects.filter(tracking_id=tracking_id).first()

        if shipment:
            return redirect("tracking-detail", tracking_id=shipment.tracking_id)
        else:
            messages.error(request, "No shipment found with that tracking ID.")
            return redirect("home")  # or wherever your track form lives

    return redirect("home")


def tracking_detail(request, tracking_id):
    shipment = get_object_or_404(
        Shipment.objects
            .select_related("sender", "receiver", "payment", "created_by")
            .prefetch_related("checkpoints", "images"),
        tracking_id=tracking_id.upper()
    )

    checkpoints = shipment.checkpoints.order_by("timestamp")

    map_points = json.dumps([
        {
            "lat":      float(cp.latitude),
            "lng":      float(cp.longitude),
            "location": cp.location,
            "event":    cp.get_event_type_display(),
            "time":     cp.timestamp.strftime("%d %b %Y, %H:%M"),
        }
        for cp in checkpoints
        if cp.latitude is not None and cp.longitude is not None
    ])

    context = {
        "shipment":    shipment,
        "checkpoints": checkpoints,
        "map_points":  map_points,
        "payment":     getattr(shipment, "payment", None),
        "images":      shipment.images.all(),
    }
    return render(request, "public/tracking_detail.html", context)


# ════════════════════════════════════════════════════════
#  ADMIN AUTH
# ════════════════════════════════════════════════════════

def admin_login(request):
    if request.user.is_authenticated and request.user.role in (User.Role.ADMIN, User.Role.STAFF):
        return redirect("admin-dashboard")

    if request.method == "POST":
        email    = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        user     = authenticate(request, email=email, password=password)

        if user and user.role in (User.Role.ADMIN, User.Role.STAFF):
            login(request, user)
            return redirect(request.GET.get("next", "admin-dashboard"))

        messages.error(request, "Invalid credentials or insufficient permissions.")

    return render(request, "admin/portal_login.html")


@login_required
def admin_logout(request):
    logout(request)
    return redirect("admin-login")


# ════════════════════════════════════════════════════════
#  ADMIN DASHBOARD
# ════════════════════════════════════════════════════════

@admin_required
def admin_dashboard(request):
    total_shipments = Shipment.objects.count()
    in_transit      = Shipment.objects.filter(status=Shipment.Status.IN_TRANSIT).count()
    delivered       = Shipment.objects.filter(status=Shipment.Status.DELIVERED).count()
    on_hold         = Shipment.objects.filter(status=Shipment.Status.HELD).count()

    total_revenue = Payment.objects.filter(
        status=Payment.Status.PAID
    ).aggregate(total=Sum("amount_paid"))["total"] or 0

    pending_payments = Payment.objects.filter(
        status__in=[Payment.Status.UNPAID, Payment.Status.PENDING]
    ).count()

    recent_shipments = Shipment.objects.select_related(
        "sender", "receiver"
    ).order_by("-created_at")[:10]

    context = {
        "total_shipments":  total_shipments,
        "in_transit":       in_transit,
        "delivered":        delivered,
        "on_hold":          on_hold,
        "total_revenue":    total_revenue,
        "pending_payments": pending_payments,
        "recent_shipments": recent_shipments,
    }
    return render(request, "admin/dashboard.html", context)


# ════════════════════════════════════════════════════════
#  ADMIN — SHIPMENT CRUD
# ════════════════════════════════════════════════════════

@admin_required
def shipment_list(request):
    qs = Shipment.objects.select_related("sender", "receiver").order_by("-created_at")

    query  = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")

    if query:
        qs = qs.filter(
            Q(tracking_id__icontains=query)
            | Q(sender__full_name__icontains=query)
            | Q(sender__email__icontains=query)
            | Q(receiver__full_name__icontains=query)
            | Q(receiver__email__icontains=query)
        )
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj":       page_obj,
        "query":          query,
        "status_filter":  status,
        "status_choices": Shipment.Status.choices,
    }
    return render(request, "admin/shipment_list.html", context)


@admin_required
def shipment_create(request):
    if request.method == "POST":
        p = request.POST

        sender = ContactInfo.objects.create(
            full_name   = p.get("sender_name", ""),
            email       = p.get("sender_email", ""),
            phone       = p.get("sender_phone", ""),
            address     = p.get("sender_address", ""),
            city        = p.get("sender_city", ""),
            state       = p.get("sender_state", ""),
            country     = p.get("sender_country", ""),
            postal_code = p.get("sender_postal", ""),
            company     = p.get("sender_company", ""),
        )

        receiver = ContactInfo.objects.create(
            full_name   = p.get("receiver_name", ""),
            email       = p.get("receiver_email", ""),
            phone       = p.get("receiver_phone", ""),
            address     = p.get("receiver_address", ""),
            city        = p.get("receiver_city", ""),
            state       = p.get("receiver_state", ""),
            country     = p.get("receiver_country", ""),
            postal_code = p.get("receiver_postal", ""),
            company     = p.get("receiver_company", ""),
        )

        shipment = Shipment.objects.create(
            created_by           = request.user,
            sender               = sender,
            receiver             = receiver,
            shipment_type        = p.get("shipment_type", Shipment.ShipmentType.STANDARD),
            description          = p.get("description", ""),
            weight_kg            = p.get("weight_kg") or None,
            dimensions           = p.get("dimensions", ""),
            quantity             = p.get("quantity", 1),
            declared_value       = p.get("declared_value") or None,
            currency             = p.get("currency", "NGN"),
            status               = p.get("status", Shipment.Status.CREATED),
            origin_country       = p.get("origin_country", ""),
            destination_country  = p.get("destination_country", ""),
            estimated_delivery   = p.get("estimated_delivery") or None,
            special_instructions = p.get("special_instructions", ""),
            internal_notes       = p.get("internal_notes", ""),
        )

        Payment.objects.create(
            shipment = shipment,
            amount   = p.get("payment_amount", 0),
            currency = p.get("payment_currency", "NGN"),
            method   = p.get("payment_method", ""),
            status   = p.get("payment_status", Payment.Status.UNPAID),
            reason   = p.get("payment_reason", ""),
            due_date = p.get("payment_due_date") or None,
        )

        for img_file in request.FILES.getlist("images"):
            ShipmentImage.objects.create(
                shipment   = shipment,
                image      = img_file,
                caption    = "",
                is_primary = False,
            )
        first_img = shipment.images.first()
        if first_img:
            first_img.is_primary = True
            first_img.save()

        messages.success(request, f"Shipment created. Tracking ID: {shipment.tracking_id}")
        return redirect("shipment-detail", pk=shipment.pk)

    context = {
        "shipment_types":    Shipment.ShipmentType.choices,
        "shipment_statuses": Shipment.Status.choices,
        "payment_methods":   Payment.Method.choices,
        "payment_statuses":  Payment.Status.choices,
    }
    return render(request, "admin/shipment_form.html", context)


@admin_required
def shipment_detail(request, pk):
    shipment = get_object_or_404(
        Shipment.objects
            .select_related("sender", "receiver", "payment", "created_by")
            .prefetch_related("checkpoints__added_by", "images"),
        pk=pk
    )
    checkpoints = shipment.checkpoints.order_by("timestamp")
    map_points  = json.dumps([
        {
            "lat":      float(cp.latitude),
            "lng":      float(cp.longitude),
            "event":    cp.get_event_type_display(),
            "location": cp.location,
            "time":     cp.timestamp.strftime("%d %b %Y, %H:%M"),
        }
        for cp in checkpoints
        if cp.latitude and cp.longitude
    ])

    context = {
        "shipment":    shipment,
        "checkpoints": checkpoints,
        "map_points":  map_points,
        "event_types": TransitCheckpoint.EventType.choices,
    }
    return render(request, "admin/shipment_detail.html", context)


@admin_required
def shipment_edit(request, pk):
    shipment = get_object_or_404(Shipment, pk=pk)
    payment  = getattr(shipment, "payment", None)

    if request.method == "POST":
        p = request.POST

        shipment.shipment_type        = p.get("shipment_type", shipment.shipment_type)
        shipment.description          = p.get("description", shipment.description)
        shipment.weight_kg            = p.get("weight_kg") or shipment.weight_kg
        shipment.dimensions           = p.get("dimensions", shipment.dimensions)
        shipment.quantity             = p.get("quantity", shipment.quantity)
        shipment.status               = p.get("status", shipment.status)
        shipment.estimated_delivery   = p.get("estimated_delivery") or shipment.estimated_delivery
        shipment.actual_delivery      = p.get("actual_delivery") or shipment.actual_delivery
        shipment.special_instructions = p.get("special_instructions", shipment.special_instructions)
        shipment.internal_notes       = p.get("internal_notes", shipment.internal_notes)
        shipment.save()

        for party, prefix in [(shipment.sender, "sender"), (shipment.receiver, "receiver")]:
            for field in ["full_name", "email", "phone", "address", "city", "state", "country"]:
                val = p.get(f"{prefix}_{field}")
                if val:
                    setattr(party, field, val)
            party.save()

        if payment:
            payment.amount      = p.get("payment_amount", payment.amount)
            payment.status      = p.get("payment_status", payment.status)
            payment.method      = p.get("payment_method", payment.method)
            payment.reason      = p.get("payment_reason", payment.reason)
            payment.amount_paid = p.get("amount_paid", payment.amount_paid)
            payment.due_date    = p.get("payment_due_date") or payment.due_date
            if payment.status == Payment.Status.PAID and not payment.paid_at:
                payment.paid_at = timezone.now()
            payment.save()

        for img_file in request.FILES.getlist("images"):
            ShipmentImage.objects.create(shipment=shipment, image=img_file)

        messages.success(request, "Shipment updated successfully.")
        return redirect("shipment-detail", pk=shipment.pk)

    context = {
        "shipment":          shipment,
        "payment":           payment,
        "shipment_types":    Shipment.ShipmentType.choices,
        "shipment_statuses": Shipment.Status.choices,
        "payment_methods":   Payment.Method.choices,
        "payment_statuses":  Payment.Status.choices,
    }
    return render(request, "admin/shipment_form.html", context)


@admin_required
@require_POST
def shipment_delete(request, pk):
    shipment    = get_object_or_404(Shipment, pk=pk)
    tracking_id = shipment.tracking_id
    shipment.delete()
    messages.success(request, f"Shipment {tracking_id} deleted.")
    return redirect("shipment-list")


# ════════════════════════════════════════════════════════
#  ADMIN — TRANSIT CHECKPOINTS
# ════════════════════════════════════════════════════════

@admin_required
@require_POST
def checkpoint_add(request, shipment_pk):
    shipment = get_object_or_404(Shipment, pk=shipment_pk)
    p        = request.POST

    checkpoint = TransitCheckpoint.objects.create(
        shipment    = shipment,
        event_type  = p["event_type"],
        location    = p["location"],
        city        = p.get("city", ""),
        country     = p.get("country", ""),
        latitude    = p.get("latitude") or None,
        longitude   = p.get("longitude") or None,
        description = p.get("description", ""),
        timestamp   = p.get("timestamp") or timezone.now(),
        added_by    = request.user,
    )

    status_map = {
        TransitCheckpoint.EventType.PICKUP:           Shipment.Status.PICKED_UP,
        TransitCheckpoint.EventType.DEPARTED:         Shipment.Status.IN_TRANSIT,
        TransitCheckpoint.EventType.IN_TRANSIT:       Shipment.Status.IN_TRANSIT,
        TransitCheckpoint.EventType.ARRIVED:          Shipment.Status.IN_TRANSIT,
        TransitCheckpoint.EventType.CUSTOMS_IN:       Shipment.Status.AT_CUSTOMS,
        TransitCheckpoint.EventType.CUSTOMS_CLEARED:  Shipment.Status.IN_TRANSIT,
        TransitCheckpoint.EventType.OUT_FOR_DELIVERY: Shipment.Status.OUT_FOR_DELIVERY,
        TransitCheckpoint.EventType.DELIVERED:        Shipment.Status.DELIVERED,
        TransitCheckpoint.EventType.HELD:             Shipment.Status.HELD,
    }
    new_status = status_map.get(checkpoint.event_type)
    if new_status and shipment.status != new_status:
        shipment.status = new_status
        if new_status == Shipment.Status.DELIVERED:
            shipment.actual_delivery = date.today()
        shipment.save()

    messages.success(request, f"Checkpoint added: {checkpoint.get_event_type_display()} at {checkpoint.location}")
    return redirect("shipment-detail", pk=shipment_pk)


@admin_required
@require_POST
def checkpoint_delete(request, pk):
    cp          = get_object_or_404(TransitCheckpoint, pk=pk)
    shipment_pk = cp.shipment.pk
    cp.delete()
    messages.success(request, "Checkpoint removed.")
    return redirect("shipment-detail", pk=shipment_pk)


# ════════════════════════════════════════════════════════
#  ADMIN — IMAGES
# ════════════════════════════════════════════════════════

@admin_required
@require_POST
def image_delete(request, pk):
    img         = get_object_or_404(ShipmentImage, pk=pk)
    shipment_pk = img.shipment.pk
    img.image.delete(save=False)
    img.delete()
    messages.success(request, "Image removed.")
    return redirect("shipment-detail", pk=shipment_pk)


@admin_required
@require_POST
def image_set_primary(request, pk):
    img = get_object_or_404(ShipmentImage, pk=pk)
    ShipmentImage.objects.filter(shipment=img.shipment).update(is_primary=False)
    img.is_primary = True
    img.save()
    return redirect("shipment-detail", pk=img.shipment.pk)


# ════════════════════════════════════════════════════════
#  ADMIN — PAYMENT MANAGEMENT
# ════════════════════════════════════════════════════════

@admin_required
def payment_list(request):
    qs = Payment.objects.select_related(
        "shipment__sender", "shipment__receiver"
    ).order_by("-created_at")

    status = request.GET.get("status", "")
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj":       page_obj,
        "status_choices": Payment.Status.choices,
        "status_filter":  status,
    }
    return render(request, "admin/payment_list.html", context)


@admin_required
@require_POST
def payment_update(request, pk):
    payment    = get_object_or_404(Payment, pk=pk)
    p          = request.POST

    payment.status            = p.get("status", payment.status)
    payment.method            = p.get("method", payment.method)
    payment.amount_paid       = p.get("amount_paid", payment.amount_paid)
    payment.payment_reference = p.get("payment_reference", payment.payment_reference)
    payment.notes             = p.get("notes", payment.notes)

    if payment.status == Payment.Status.PAID and not payment.paid_at:
        payment.paid_at = timezone.now()
    payment.save()

    messages.success(request, "Payment updated.")
    return redirect("shipment-detail", pk=payment.shipment.pk)


@admin_required
@require_POST
def payment_send_reminder(request, pk):
    # Email removed — just redirect with a message
    messages.info(request, "Email reminders have been disabled.")
    payment = get_object_or_404(Payment, pk=pk)
    return redirect("shipment-detail", pk=payment.shipment.pk)


# ════════════════════════════════════════════════════════
#  ADMIN — REPORTS
# ════════════════════════════════════════════════════════

@admin_required
def reports(request):
    status_counts = (
        Shipment.objects
        .values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )

    revenue_paid = Payment.objects.filter(
        status=Payment.Status.PAID
    ).aggregate(total=Sum("amount_paid"))["total"] or 0

    revenue_outstanding = Payment.objects.filter(
        status__in=[Payment.Status.UNPAID, Payment.Status.PENDING, Payment.Status.PARTIAL]
    ).aggregate(total=Sum("amount"))["total"] or 0

    top_routes = (
        Shipment.objects
        .values("origin_country", "destination_country")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    context = {
        "status_counts":       status_counts,
        "revenue_paid":        revenue_paid,
        "revenue_outstanding": revenue_outstanding,
        "top_routes":          top_routes,
    }
    return render(request, "admin/reports.html", context)


# ════════════════════════════════════════════════════════
#  API ENDPOINTS
# ════════════════════════════════════════════════════════

@require_GET
def api_track(request, tracking_id):
    shipment  = get_object_or_404(
        Shipment.objects.select_related("sender", "receiver")
                        .prefetch_related("checkpoints"),
        tracking_id=tracking_id.upper()
    )
    latest_cp = shipment.checkpoints.order_by("-timestamp").first()

    data = {
        "tracking_id":  shipment.tracking_id,
        "status":       shipment.status,
        "status_label": shipment.get_status_display(),
        "origin":       shipment.origin_country,
        "destination":  shipment.destination_country,
        "est_delivery": str(shipment.estimated_delivery) if shipment.estimated_delivery else None,
        "latest_checkpoint": {
            "event":    latest_cp.get_event_type_display(),
            "location": latest_cp.location,
            "time":     latest_cp.timestamp.isoformat(),
        } if latest_cp else None,
    }
    return JsonResponse(data)


@require_GET
@admin_required
def api_shipment_checkpoints(request, pk):
    shipment    = get_object_or_404(Shipment, pk=pk)
    checkpoints = shipment.checkpoints.order_by("timestamp")

    data = [
        {
            "id":          str(cp.id),
            "event":       cp.get_event_type_display(),
            "location":    cp.location,
            "city":        cp.city,
            "country":     cp.country,
            "lat":         float(cp.latitude)  if cp.latitude  else None,
            "lng":         float(cp.longitude) if cp.longitude else None,
            "timestamp":   cp.timestamp.isoformat(),
            "description": cp.description,
        }
        for cp in checkpoints
    ]
    return JsonResponse({"checkpoints": data})



# ══════════════════════════════════════════════════════
#  ADD THESE VIEWS TO YOUR EXISTING views.py
# ══════════════════════════════════════════════════════
from Business.models import SiteSettings, Testimonial


# ── PUBLIC HOME ───────────────────────────────────────

def home(request):
    """
    Public homepage — pulls all content from database.
    Admin controls everything via Site Settings and Testimonials.
    """
    site         = SiteSettings.get()
    testimonials = Testimonial.objects.filter(is_active=True).order_by("sort_order")

    return render(request, "public/home.html", {
        "site":         site,
        "testimonials": testimonials,
    })


# ── ADMIN SITE SETTINGS ───────────────────────────────

@admin_required
def admin_site_settings(request):
    """
    GET  /admin-portal/site-settings/   → form pre-filled with current settings
    POST /admin-portal/site-settings/   → save changes

    Controls: company name, tagline, hero subtitle, contact details,
              phone numbers, emails, address, social links, stats, footer.
    """
    site = SiteSettings.get()

    if request.method == "POST":
        p = request.POST

        site.company_name    = p.get("company_name",    site.company_name)
        site.tagline         = p.get("tagline",         site.tagline)
        site.hero_subtitle   = p.get("hero_subtitle",   site.hero_subtitle)
        site.hero_image_url  = p.get("hero_image_url",  site.hero_image_url)

        site.phone_primary   = p.get("phone_primary",   site.phone_primary)
        site.phone_secondary = p.get("phone_secondary", site.phone_secondary)
        site.email_support   = p.get("email_support",   site.email_support)
        site.email_info      = p.get("email_info",      site.email_info)
        site.whatsapp_number = p.get("whatsapp_number", site.whatsapp_number)
        site.address         = p.get("address",         site.address)
        site.google_maps_url = p.get("google_maps_url", site.google_maps_url)

        site.twitter_url     = p.get("twitter_url",     site.twitter_url)
        site.instagram_url   = p.get("instagram_url",   site.instagram_url)
        site.linkedin_url    = p.get("linkedin_url",    site.linkedin_url)
        site.facebook_url    = p.get("facebook_url",    site.facebook_url)

        site.stat_deliveries  = p.get("stat_deliveries",  site.stat_deliveries)
        site.stat_satisfaction= p.get("stat_satisfaction",site.stat_satisfaction)
        site.stat_support     = p.get("stat_support",     site.stat_support)

        site.copyright_text  = p.get("copyright_text",  site.copyright_text)
        site.save()

        messages.success(request, "Site settings saved successfully.")
        return redirect("admin-site-settings")

    return render(request, "admin/site_settings.html", {"site": site})


# ── ADMIN TESTIMONIALS ────────────────────────────────

@admin_required
def admin_testimonials(request):
    """
    GET  /admin-portal/testimonials/   → list all + add form
    POST /admin-portal/testimonials/   → create new testimonial
    """
    if request.method == "POST":
        p = request.POST
        t = Testimonial(
            name       = p.get("name", ""),
            role       = p.get("role", ""),
            avatar_url = p.get("avatar_url", ""),
            content    = p.get("content", ""),
            rating     = int(p.get("rating", 5)),
            sort_order = int(p.get("sort_order", 0)),
            is_active  = "is_active" in p,
        )
        if "avatar" in request.FILES:
            t.avatar = request.FILES["avatar"]
        t.save()
        messages.success(request, f"Testimonial from {t.name} added.")
        return redirect("admin-testimonials")

    testimonials = Testimonial.objects.all().order_by("sort_order")
    return render(request, "admin/testimonials.html", {
        "testimonials": testimonials,
        "edit_obj":     None,
    })


@admin_required
def admin_testimonial_edit(request, pk):
    """
    GET  /admin-portal/testimonials/<pk>/edit/  → pre-filled edit form
    POST /admin-portal/testimonials/<pk>/edit/  → save changes
    """
    t = get_object_or_404(Testimonial, pk=pk)

    if request.method == "POST":
        p = request.POST
        t.name       = p.get("name", t.name)
        t.role       = p.get("role", t.role)
        t.avatar_url = p.get("avatar_url", t.avatar_url)
        t.content    = p.get("content", t.content)
        t.rating     = int(p.get("rating", t.rating))
        t.sort_order = int(p.get("sort_order", t.sort_order))
        t.is_active  = "is_active" in p
        if "avatar" in request.FILES:
            t.avatar = request.FILES["avatar"]
        t.save()
        messages.success(request, f"Testimonial from {t.name} updated.")
        return redirect("admin-testimonials")

    testimonials = Testimonial.objects.all().order_by("sort_order")
    return render(request, "admin/testimonials.html", {
        "testimonials": testimonials,
        "edit_obj":     t,
    })


@admin_required
@require_POST
def admin_testimonial_delete(request, pk):
    """
    POST /admin-portal/testimonials/<pk>/delete/
    """
    t = get_object_or_404(Testimonial, pk=pk)
    name = t.name
    t.delete()
    messages.success(request, f"Testimonial from {name} deleted.")
    return redirect("admin-testimonials")






# ══════════════════════════════════════════════════════════════════
#  ADD TO Business/views.py
#
#  Assumes:
#   - request.user.sub_admin_profile is the SubAdminProfile
#   - request.user.account is the Account NGN wallet (OneToOne)
#   - You already have an approval check pattern elsewhere; the
#     `sub_admin_required` decorator below is a self-contained
#     version — delete it and import your existing one instead if
#     you already have one in Business/decorators.py.
# ══════════════════════════════════════════════════════════════════

from functools import wraps
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import BuyLogs, BuyLogDetails, Purchase, Account, SubAdminProfile


def sub_admin_required(view_func):
    """Only approved sub-admins may browse or buy logs."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        profile = getattr(request.user, "sub_admin_profile", None)
        if profile is None or profile.approval_status != SubAdminProfile.ApprovalStatus.APPROVED:
            messages.error(request, "Your sub-admin account isn't approved yet.")
            return redirect("sub-admin-dashboard")
        return view_func(request, *args, **kwargs)
    return wrapper


from .models import BuyLogs, BuyLogDetails, Purchase, Account, SubAdminProfile, Category


@sub_admin_required
def browse_logs(request):
    """List active log products, optionally filtered by category."""
    category_slug = request.GET.get("category")

    products = BuyLogs.objects.filter(active=True).select_related("category")
    if category_slug:
        products = products.filter(category__slug=category_slug)

    context = {
        "products": products,
        "categories": Category.objects.filter(is_active=True),
        "selected_category": category_slug,
        "wallet_balance": request.user.account.balance,
    }
    return render(request, "buy_logs/browse.html", context)



@sub_admin_required
def log_detail(request, pk):
    product = get_object_or_404(BuyLogs, pk=pk, active=True)
    context = {
        "product": product,
        "wallet_balance": request.user.account.balance,
    }
    return render(request, "buy_logs/detail.html", context)


@sub_admin_required
def purchase_log(request, pk):
    """
    POST-only. Atomically: lock the buyer's wallet, lock one unsold
    log for this product, check balance, debit, mark sold, record
    the Purchase — all or nothing.
    """
    if request.method != "POST":
        return redirect("buy-logs-detail", pk=pk)

    product = get_object_or_404(BuyLogs, pk=pk, active=True)

    try:
        with transaction.atomic():
            account = Account.objects.select_for_update().get(user=request.user)

            if account.balance < product.price:
                messages.error(request, "Insufficient wallet balance for this purchase.")
                return redirect("buy-logs-detail", pk=pk)

            log = (
                BuyLogDetails.objects
                .select_for_update(skip_locked=True)
                .filter(product=product, sold=False)
                .order_by("created_at")
                .first()
            )
            if log is None:
                messages.error(request, "This product is out of stock right now.")
                return redirect("buy-logs-detail", pk=pk)

            account.balance -= product.price
            account.save(update_fields=["balance", "updated_at"])

            log.sold = True
            log.sold_at = timezone.now()
            log.save(update_fields=["sold", "sold_at"])

            purchase = Purchase.objects.create(
                buyer=request.user,
                product=product,
                log=log,
                account=account,
                amount=product.price,
            )
    except Account.DoesNotExist:
        messages.error(request, "No wallet found on your account.")
        return redirect("buy-logs-detail", pk=pk)

    messages.success(request, f"Purchased {product.title}. Check your purchase history for credentials.")
    return redirect("buy-logs-receipt", pk=purchase.pk)


@sub_admin_required
def my_purchases(request):
    purchases = (
        Purchase.objects
        .filter(buyer=request.user)
        .select_related("product", "log")
    )
    return render(request, "buy_logs/my_purchases.html", {"purchases": purchases})


@sub_admin_required
def purchase_receipt(request, pk):
    """Reveal the credentials for one purchase — buyer-only."""
    purchase = get_object_or_404(
        Purchase.objects.select_related("product", "log"),
        pk=pk, buyer=request.user,
    )
    return render(request, "buy_logs/receipt.html", {"purchase": purchase})




from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import DashboardAdvert

def admin_advert_list(request):
    adverts = DashboardAdvert.objects.all()
    active_count = sum(1 for a in adverts if a.is_currently_active())
    context = {
        "adverts": adverts,
        "active_count": active_count,
        "inactive_count": adverts.count() - active_count,
    }
    return render(request, "admin/advert_list.html", context)

def _save_advert_from_post(request, advert=None):
    advert = advert or DashboardAdvert()
    advert.title = request.POST.get("title", "").strip()
    advert.subtitle = request.POST.get("subtitle", "").strip()
    advert.cta_text = request.POST.get("cta_text", "Learn More").strip()
    advert.cta_url = request.POST.get("cta_url", "").strip()
    advert.background_start = request.POST.get("background_start", "#3B82F6")
    advert.background_end = request.POST.get("background_end", "#1E3A8A")
    advert.order = int(request.POST.get("order") or 0)
    advert.is_active = "is_active" in request.POST
    advert.start_date = request.POST.get("start_date") or None
    advert.end_date = request.POST.get("end_date") or None
    if request.FILES.get("image"):
        advert.image = request.FILES["image"]
    advert.save()
    return advert

def admin_advert_create(request):
    if request.method == "POST":
        _save_advert_from_post(request)
        messages.success(request, "Advert created.")
        return redirect("admin-advert-list")
    return render(request, "admin/advert_form.html", {"advert": None})

def admin_advert_edit(request, pk):
    advert = get_object_or_404(DashboardAdvert, pk=pk)
    if request.method == "POST":
        _save_advert_from_post(request, advert)
        messages.success(request, "Advert updated.")
        return redirect("admin-advert-list")
    return render(request, "admin/advert_form.html", {"advert": advert})

def admin_advert_toggle(request, pk):
    advert = get_object_or_404(DashboardAdvert, pk=pk)
    advert.is_active = not advert.is_active
    advert.save()
    messages.success(request, f"Advert {'activated' if advert.is_active else 'paused'}.")
    return redirect("admin-advert-list")

def admin_advert_delete(request, pk):
    advert = get_object_or_404(DashboardAdvert, pk=pk)
    advert.delete()
    messages.success(request, "Advert deleted.")
    return redirect("admin-advert-list")

def admin_advert_edit(request, pk):
    advert = get_object_or_404(DashboardAdvert, pk=pk)
    if request.method == "POST":
        _save_advert_from_post(request, advert)
        messages.success(request, "Advert updated.")
        return redirect("admin-advert-list")
    return render(request, "admin/advert_form.html", {"advert": advert})



from django.shortcuts import render

def error_404(request, exception):
    return render(request, "404.html", status=404)

def error_500(request):
    return render(request, "500.html", status=500)

def error_403(request, exception):
    return render(request, "403.html", status=403)

def error_400(request, exception):
    return render(request, "400.html", status=400)




# ══════════════════════════════════════════════════════════════════
#  ADD TO Business/views.py (admin-panel side, alongside admin_dashboard)
#  Two worked examples of the generic_list.html / generic_form.html
#  pattern — copy-paste-adjust for the rest of your model list.
# ══════════════════════════════════════════════════════════════════

from django.urls import reverse
from .models import Account, Category


# ── ACCOUNTS — read-only list (wallets shouldn't be hand-edited) ───

@admin_required
def admin_account_list(request):
    query = request.GET.get("q", "").strip()
    qs = Account.objects.select_related("user").order_by("-created_at")
    if query:
        qs = qs.filter(
            Q(account_number__icontains=query)
            | Q(user__email__icontains=query)
            | Q(user__full_name__icontains=query)
        )

    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get("page"))

    rows = [
        {
            "account_number": a.account_number,
            "user":           getattr(a.user, "full_name", "—"),
            "email":          getattr(a.user, "email", "—"),
            "balance":        f"₦{a.balance:,.2f}",
            "created":        a.created_at.strftime("%d %b %Y"),
            # no edit/delete — deliberately read-only
        }
        for a in page_obj
    ]

    context = {
        "page_title":  "Accounts",
        "singular_name": "Account",
        "add_url":     None,                       # hides the "Add" button
        "query":       query,
        "columns": [
            {"key": "account_number", "label": "Account #", "type": "mono"},
            {"key": "user",           "label": "User"},
            {"key": "email",          "label": "Email"},
            {"key": "balance",        "label": "Balance"},
            {"key": "created",        "label": "Created"},
        ],
        "rows": rows,
        "row_actions_enabled": False,
        "page_obj": page_obj,
    }
    return render(request, "admin/generic_list.html", context)


# ── CATEGORIES — full add/edit/delete CRUD ──────────────────────────

@admin_required
def admin_category_list(request):
    qs = Category.objects.all().order_by("order", "name")
    rows = [
        {
            "name":       c.name,
            "slug":       c.slug,
            "order":      c.order,
            "is_active":  {"text": "Active", "class": "b-green"} if c.is_active else {"text": "Inactive", "class": "b-gray"},
            "edit_url":   reverse("admin-category-edit", args=[c.pk]),
            "delete_url": reverse("admin-category-delete", args=[c.pk]),
        }
        for c in qs
    ]
    context = {
        "page_title": "Categories",
        "singular_name": "Category",
        "add_url": reverse("admin-category-create"),
        "columns": [
            {"key": "name",  "label": "Name"},
            {"key": "slug",  "label": "Slug", "type": "mono"},
            {"key": "order", "label": "Order"},
            {"key": "is_active", "label": "Status", "type": "badge"},
        ],
        "rows": rows,
        "row_actions_enabled": True,
    }
    return render(request, "admin/generic_list.html", context)


def _category_field_groups(category=None):
    return [
        {
            "title": None,
            "fields": [
                {"name": "name", "label": "Name", "value": category.name if category else "", "required": True},
                {"name": "icon", "label": "Icon (Font Awesome class)", "value": category.icon if category else ""},
                {"name": "order", "label": "Sort Order", "type": "number", "value": category.order if category else 0},
                {"name": "is_active", "label": "Active", "type": "checkbox", "help": "Visible to sub-admins", "value": category.is_active if category else True},
            ],
        },
    ]


@admin_required
def admin_category_create(request):
    if request.method == "POST":
        Category.objects.create(
            name=request.POST.get("name", "").strip(),
            icon=request.POST.get("icon", "").strip(),
            order=int(request.POST.get("order") or 0),
            is_active="is_active" in request.POST,
        )
        messages.success(request, "Category created.")
        return redirect("admin-category-list")

    context = {
        "page_title": "Add Category",
        "singular_name": "Category",
        "list_url": reverse("admin-category-list"),
        "is_edit": False,
        "field_groups": _category_field_groups(),
    }
    return render(request, "admin/generic_form.html", context)


@admin_required
def admin_category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        category.name = request.POST.get("name", category.name).strip()
        category.icon = request.POST.get("icon", category.icon).strip()
        category.order = int(request.POST.get("order") or category.order)
        category.is_active = "is_active" in request.POST
        category.save()
        messages.success(request, "Category updated.")
        return redirect("admin-category-list")

    context = {
        "page_title": f"Edit — {category.name}",
        "singular_name": "Category",
        "list_url": reverse("admin-category-list"),
        "is_edit": True,
        "field_groups": _category_field_groups(category),
    }
    return render(request, "admin/generic_form.html", context)


@admin_required
@require_POST
def admin_category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    name = category.name
    category.delete()
    messages.success(request, f"Category '{name}' deleted.")
    return redirect("admin-category-list")


# ══════════════════════════════════════════════════════════════════
#  urls.py additions for the two examples above:
#
#  path("accounts/", admin_account_list, name="admin-account-list"),
#  path("categories/", admin_category_list, name="admin-category-list"),
#  path("categories/create/", admin_category_create, name="admin-category-create"),
#  path("categories/<pk>/edit/", admin_category_edit, name="admin-category-edit"),
#  path("categories/<pk>/delete/", admin_category_delete, name="admin-category-delete"),
# ══════════════════════════════════════════════════════════════════





# ══════════════════════════════════════════════════════
#  ADD THESE TO YOUR admin views file (wherever your
#  custom admin views live — e.g. views.py or admin_views.py)
# ══════════════════════════════════════════════════════

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from Business.models import BuyLogs, BuyLogDetails, Category


# ── helper ────────────────────────────────────────────
def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin-login')
        if getattr(request.user, 'role', '') not in ('admin', 'staff'):
            messages.error(request, 'Access denied.')
            return redirect('admin-login')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


# ── LOG PRODUCT LIST ──────────────────────────────────
@admin_required
def log_list(request):
    """
    GET /admin-portal/logs/
    Lists all BuyLogs products with search, category filter,
    status filter, and pagination.
    """
    qs = BuyLogs.objects.select_related('category').annotate(
        total_stock=Count('details'),
        available=Count('details', filter=Q(details__sold=False)),
    ).order_by('category__name', 'title')

    query    = request.GET.get('q', '').strip()
    cat_id   = request.GET.get('category', '')
    status   = request.GET.get('status', '')   # 'active' | 'inactive' | ''

    if query:
        qs = qs.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        )
    if cat_id:
        qs = qs.filter(category_id=cat_id)
    if status == 'active':
        qs = qs.filter(active=True)
    elif status == 'inactive':
        qs = qs.filter(active=False)

    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))

    categories = Category.objects.filter(is_active=True).order_by('order', 'name')

    # Summary stats
    total_products   = BuyLogs.objects.count()
    total_stock      = BuyLogDetails.objects.count()
    available_stock  = BuyLogDetails.objects.filter(sold=False).count()
    total_categories = Category.objects.count()

    context = {
        'page_obj':        page_obj,
        'query':           query,
        'cat_id':          cat_id,
        'status':          status,
        'categories':      categories,
        'total_products':  total_products,
        'total_stock':     total_stock,
        'available_stock': available_stock,
        'total_categories':total_categories,
    }
    return render(request, 'admin/logs/log_list.html', context)


# ── LOG PRODUCT CREATE ────────────────────────────────
@admin_required
def log_create(request):
    """
    GET  /admin-portal/logs/create/  → blank form
    POST /admin-portal/logs/create/  → create product
    """
    categories = Category.objects.filter(is_active=True).order_by('order', 'name')

    if request.method == 'POST':
        p = request.POST
        try:
            product = BuyLogs.objects.create(
                category_id = p.get('category'),
                title       = p.get('title', '').strip(),
                description = p.get('description', '').strip(),
                price       = p.get('price', 0),
                active      = 'active' in p,
                image       = request.FILES.get('image'),
            )
            messages.success(request, f'"{product.title}" created successfully.')
            return redirect('admin-log-detail', pk=product.pk)
        except Exception as e:
            messages.error(request, f'Error creating product: {e}')

    return render(request, 'admin/logs/log_form.html', {
        'categories': categories,
        'action':     'Create',
    })


# ── LOG PRODUCT DETAIL ────────────────────────────────
@admin_required
def log_detail(request, pk):
    """
    GET /admin-portal/logs/<pk>/
    Shows product info + all detail (credential) rows.
    Admin can add/delete individual credential rows here.
    """
    product = get_object_or_404(
        BuyLogs.objects.select_related('category').annotate(
            total_stock=Count('details'),
            available=Count('details', filter=Q(details__sold=False)),
        ),
        pk=pk
    )
    details  = product.details.all().order_by('-id')
    paginator = Paginator(details, 30)
    page_obj  = paginator.get_page(request.GET.get('page'))

    context = {
        'product': product,
        'page_obj': page_obj,
        'detail_fields': _get_detail_fields(),
    }
    return render(request, 'admin/logs/log_detail.html', context)


# ── LOG PRODUCT EDIT ──────────────────────────────────
@admin_required
def log_edit(request, pk):
    """
    GET  /admin-portal/logs/<pk>/edit/  → pre-filled form
    POST /admin-portal/logs/<pk>/edit/  → save changes
    """
    product    = get_object_or_404(BuyLogs, pk=pk)
    categories = Category.objects.filter(is_active=True).order_by('order', 'name')

    if request.method == 'POST':
        p = request.POST
        product.category_id = p.get('category', product.category_id)
        product.title       = p.get('title', product.title).strip()
        product.description = p.get('description', product.description).strip()
        product.price       = p.get('price', product.price)
        product.active      = 'active' in p
        if request.FILES.get('image'):
            product.image = request.FILES['image']
        product.save()
        messages.success(request, f'"{product.title}" updated.')
        return redirect('admin-log-detail', pk=product.pk)

    return render(request, 'admin/logs/log_form.html', {
        'product':    product,
        'categories': categories,
        'action':     'Edit',
    })


# ── LOG PRODUCT DELETE ────────────────────────────────
@admin_required
@require_POST
def log_delete(request, pk):
    product = get_object_or_404(BuyLogs, pk=pk)
    name    = product.title
    product.delete()
    messages.success(request, f'"{name}" deleted.')
    return redirect('admin-log-list')


# ── LOG PRODUCT TOGGLE ACTIVE ─────────────────────────
@admin_required
@require_POST
def log_toggle_active(request, pk):
    product        = get_object_or_404(BuyLogs, pk=pk)
    product.active = not product.active
    product.save()
    state = 'activated' if product.active else 'deactivated'
    messages.success(request, f'"{product.title}" {state}.')
    return redirect('admin-log-detail', pk=pk)


# ── DETAIL ROW (CREDENTIAL) ADD ───────────────────────
@admin_required
@require_POST
def log_detail_add(request, product_pk):
    """
    POST /admin-portal/logs/<pk>/details/add/
    Adds a new credential row to a product.
    Accepts dynamic key/value pairs from the form.
    """
    product = get_object_or_404(BuyLogs, pk=product_pk)
    p       = request.POST

    # Collect all field_ prefixed POST values dynamically
    data = {}
    for key, val in p.items():
        if key.startswith('field_') and val.strip():
            field_name = key[6:]   # strip 'field_' prefix
            data[field_name] = val.strip()

    if not data:
        messages.error(request, 'No credential data provided.')
        return redirect('admin-log-detail', pk=product_pk)

    try:
        BuyLogDetails.objects.create(product=product, **data)
        messages.success(request, 'Credential row added.')
    except Exception as e:
        messages.error(request, f'Error: {e}')

    return redirect('admin-log-detail', pk=product_pk)


# ── DETAIL ROW DELETE ─────────────────────────────────
@admin_required
@require_POST
def log_detail_delete(request, pk):
    detail      = get_object_or_404(BuyLogDetails, pk=pk)
    product_pk  = detail.product.pk
    detail.delete()
    messages.success(request, 'Credential row deleted.')
    return redirect('admin-log-detail', pk=product_pk)


# ── DETAIL ROW MARK SOLD ──────────────────────────────
@admin_required
@require_POST
def log_detail_mark_sold(request, pk):
    detail      = get_object_or_404(BuyLogDetails, pk=pk)
    product_pk  = detail.product.pk
    detail.sold = not detail.sold
    detail.save()
    state = 'sold' if detail.sold else 'available'
    messages.success(request, f'Row marked as {state}.')
    return redirect('admin-log-detail', pk=product_pk)


# ── BULK UPLOAD DETAILS ───────────────────────────────
@admin_required
@require_POST
def log_detail_bulk(request, product_pk):
    """
    POST /admin-portal/logs/<pk>/details/bulk/
    Accepts textarea with one credential per line.
    Format: field1:value1 | field2:value2 | field3:value3
    Example: email:user@gmail.com | password:abc123 | recovery:backup@gmail.com
    """
    product = get_object_or_404(BuyLogs, pk=product_pk)
    raw     = request.POST.get('bulk_data', '').strip()

    if not raw:
        messages.error(request, 'No data provided.')
        return redirect('admin-log-detail', pk=product_pk)

    lines   = [l.strip() for l in raw.splitlines() if l.strip()]
    created = 0
    errors  = 0

    for line in lines:
        try:
            data = {}
            parts = [p.strip() for p in line.split('|')]
            for part in parts:
                if ':' in part:
                    k, v = part.split(':', 1)
                    data[k.strip()] = v.strip()
            if data:
                BuyLogDetails.objects.create(product=product, **data)
                created += 1
        except Exception:
            errors += 1

    if created:
        messages.success(request, f'{created} credential row{"s" if created != 1 else ""} added.')
    if errors:
        messages.warning(request, f'{errors} row{"s" if errors != 1 else ""} failed — check format.')

    return redirect('admin-log-detail', pk=product_pk)


# ── CATEGORY LIST ─────────────────────────────────────
@admin_required
def log_category_list(request):
    """
    GET /admin-portal/logs/categories/
    """
    categories = Category.objects.annotate(
        product_count=Count('products')
    ).order_by('order', 'name')

    return render(request, 'admin/logs/category_list.html', {
        'categories': categories,
    })


# ── CATEGORY CREATE/EDIT ──────────────────────────────
@admin_required
def log_category_form(request, pk=None):
    """
    GET/POST /admin-portal/logs/categories/create/
    GET/POST /admin-portal/logs/categories/<pk>/edit/
    """
    category = get_object_or_404(Category, pk=pk) if pk else None

    if request.method == 'POST':
        p    = request.POST
        name = p.get('name', '').strip()
        if not name:
            messages.error(request, 'Name is required.')
        else:
            if category:
                category.name      = name
                category.icon      = p.get('icon', category.icon)
                category.order     = p.get('order', category.order)
                category.is_active = 'is_active' in p
                category.save()
                messages.success(request, f'Category "{category.name}" updated.')
            else:
                category = Category.objects.create(
                    name      = name,
                    icon      = p.get('icon', ''),
                    order     = p.get('order', 0),
                    is_active = 'is_active' in p,
                )
                messages.success(request, f'Category "{category.name}" created.')
            return redirect('admin-log-category-list')

    return render(request, 'admin/logs/category_form.html', {
        'category': category,
        'action':   'Edit' if category else 'Create',
    })


# ── CATEGORY DELETE ───────────────────────────────────
@admin_required
@require_POST
def log_category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    name     = category.name
    category.delete()
    messages.success(request, f'Category "{name}" deleted.')
    return redirect('admin-log-category-list')


# ── HELPER ────────────────────────────────────────────
def _get_detail_fields():
    """
    Returns the actual field names on BuyLogDetails
    (excluding system fields) for the add-row form.
    """
    exclude = {'id', 'product', 'sold', 'created_at', 'updated_at'}
    return [
        f.name for f in BuyLogDetails._meta.get_fields()
        if hasattr(f, 'column') and f.name not in exclude
    ]
