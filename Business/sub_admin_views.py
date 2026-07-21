import os
import json
import math
import uuid
import hmac
import hashlib
import logging
import requests
from io import BytesIO
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from decouple import config
from xhtml2pdf import pisa

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import (
    User, Shipment, ContactInfo, ShipmentImage,
    TransitCheckpoint, Payment,
    SubAdminProfile, PointsPurchase, PointsPricing,
    Account, ForeignNumber, WalletDeposit,
    Notification, NotificationRead, SubAdminSiteSettings,
    DashboardAdvert, DashboardAnnouncement, Testimonial, BrandGalleryImage,
    Invoice, InvoiceItem,SubAdminGalleryImage
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════
#  DECORATORS
# ════════════════════════════════════════════════════════

def sub_admin_login_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("sub-admin-login")
        if request.user.role != User.Role.SUB_ADMIN:
            return redirect("sub-admin-login")
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def sub_admin_approved_required(view_func):
    """Logged in + approved. Can browse but NOT create shipments."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("sub-admin-login")
        if request.user.role != User.Role.SUB_ADMIN:
            return redirect("sub-admin-login")
        try:
            profile = request.user.sub_admin_profile
        except SubAdminProfile.DoesNotExist:
            return redirect("sub-admin-login")

        if profile.approval_status == SubAdminProfile.ApprovalStatus.PENDING:
            return render(request, "admin/subadmin/pending_approval.html", {"profile": profile})
        if profile.approval_status == SubAdminProfile.ApprovalStatus.REJECTED:
            return render(request, "admin/subadmin/rejected.html", {"profile": profile})
        if profile.approval_status == SubAdminProfile.ApprovalStatus.SUSPENDED:
            return render(request, "admin/subadmin/suspended.html", {"profile": profile})
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def sub_admin_has_points(view_func):
    """Approved + enough points to create a shipment."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("sub-admin-login")
        if request.user.role != User.Role.SUB_ADMIN:
            return redirect("sub-admin-login")
        try:
            profile = request.user.sub_admin_profile
        except SubAdminProfile.DoesNotExist:
            return redirect("sub-admin-login")
        if profile.approval_status != SubAdminProfile.ApprovalStatus.APPROVED:
            return redirect("sub-admin-dashboard")
        if not profile.can_create_shipment():
            messages.warning(
                request,
                f"You need at least "
                f"{PointsPricing.get_current().points_per_shipment} point(s) to create a shipment. "
                f"You have {profile.points_balance}. Please top up."
            )
            return redirect("sub-admin-buy-points")
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def super_admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("admin-login")
        if request.user.role != User.Role.ADMIN:
            messages.error(request, "Super admin access required.")
            return redirect("admin-dashboard")
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


# ════════════════════════════════════════════════════════
#  AUTH
# ════════════════════════════════════════════════════════

def sub_admin_register(request):
    if request.user.is_authenticated and request.user.role == User.Role.SUB_ADMIN:
        return redirect("sub-admin-dashboard")

    # capture referral code from the link (?ref=A1B2C3D4), keep it
    # through the form via a hidden input named "ref_code"
    ref_code = request.GET.get("ref", "").strip().upper()

    if request.method == "POST":
        p         = request.POST
        email     = p.get("email", "").strip().lower()
        password  = p.get("password", "")
        password2 = p.get("password2", "")
        full_name = p.get("full_name", "").strip()
        phone     = p.get("phone", "").strip()
        company   = p.get("company_name", "").strip()
        address   = p.get("address", "").strip()
        ref_code  = p.get("ref_code", "").strip().upper()

        if password != password2:
            messages.error(request, "Passwords do not match.")
            return render(request, "admin/subadmin/register.html", {"post": p, "ref_code": ref_code})

        if User.objects.filter(email=email).exists():
            messages.error(request, "An account with this email already exists.")
            return render(request, "admin/subadmin/register.html", {"post": p, "ref_code": ref_code})

        user = User.objects.create_user(
            email     = email,
            password  = password,
            full_name = full_name,
            role      = User.Role.SUB_ADMIN,
            is_active = True,
        )

        # find referrer by code (if any)
        referrer = None
        if ref_code:
            referrer = SubAdminProfile.objects.filter(referral_code=ref_code).first()

        SubAdminProfile.objects.create(
            user         = user,
            phone        = phone,
            company_name = company,
            address      = address,
            referred_by  = referrer,
        )
        messages.success(request, "Registration successful! Awaiting admin approval.")
        return redirect("sub-admin-login")

    return render(request, "admin/subadmin/register.html", {"ref_code": ref_code})


def sub_admin_login(request):
    if request.user.is_authenticated and request.user.role == User.Role.SUB_ADMIN:
        return redirect("sub-admin-dashboard")

    if request.method == "POST":
        email    = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        user     = authenticate(request, email=email, password=password)
        if user and user.role == User.Role.SUB_ADMIN:
            login(request, user)
            return redirect("sub-admin-dashboard")
        messages.error(request, "Invalid email or password.")

    return render(request, "admin/subadmin/login.html")


@login_required
def sub_admin_logout(request):
    logout(request)
    return redirect("sub-admin-login")


# ════════════════════════════════════════════════════════
#  DASHBOARD
# ════════════════════════════════════════════════════════

@sub_admin_approved_required
def sub_admin_dashboard(request):
    profile  = request.user.sub_admin_profile
    pricing  = PointsPricing.get_current()
    recent   = Shipment.objects.filter(
        created_by=request.user
    ).select_related("sender", "receiver").order_by("-created_at")[:5]

    adverts = [
        a for a in DashboardAdvert.objects.filter(is_active=True)
        if a.is_currently_active()
    ]

    announcement = (
        DashboardAnnouncement.objects
        .filter(is_active=True)
        .order_by("-created_at")
        .first()
    )

    context = {
        "profile":       profile,
        "pricing":       pricing,
        "total":         Shipment.objects.filter(created_by=request.user).count(),
        "in_transit":    Shipment.objects.filter(created_by=request.user, status=Shipment.Status.IN_TRANSIT).count(),
        "delivered":     Shipment.objects.filter(created_by=request.user, status=Shipment.Status.DELIVERED).count(),
        "recent":        recent,
        "can_create":    profile.can_create_shipment(),
        "adverts":       adverts,
        "announcement":  announcement,
    }
    return render(request, "admin/subadmin/dashboard.html", context)


# ════════════════════════════════════════════════════════
#  POINTS — BUY & WEBHOOK
# ════════════════════════════════════════════════════════

@sub_admin_approved_required
def sub_admin_buy_points(request):
    profile  = request.user.sub_admin_profile
    pricing  = PointsPricing.get_current()
    history  = profile.point_purchases.order_by("-created_at")[:10]

    context = {
        "profile": profile,
        "pricing": pricing,
        "history": history,
    }
    return render(request, "admin/subadmin/buy_points.html", context)


@sub_admin_approved_required
@require_POST
def sub_admin_points_pay(request):
    """Initiate Paystack payment for points top-up."""
    profile  = request.user.sub_admin_profile
    pricing  = PointsPricing.get_current()

    try:
        quantity = int(request.POST.get("quantity", 1))
        if quantity < 1:
            raise ValueError
    except (ValueError, TypeError):
        messages.error(request, "Invalid quantity.")
        return redirect("sub-admin-buy-points")

    total_amount = pricing.price_per_point * quantity
    amount_kobo  = int(total_amount * 100)
    reference    = f"PTS-{request.user.pk}-{uuid.uuid4().hex[:10].upper()}"

    purchase = PointsPurchase.objects.create(
        sub_admin          = profile,
        points_bought      = quantity,
        amount_paid        = total_amount,
        currency           = pricing.currency,
        paystack_reference = reference,
        status             = PointsPurchase.Status.PENDING,
    )

    callback_url = request.build_absolute_uri(
    reverse("sub-admin-points-verify", args=[reference])
    )

    try:
        payload = {
            "email":        request.user.email,
            "amount":       amount_kobo,
            "reference":    reference,
            "callback_url": callback_url,
            "metadata": {
                "sub_admin_id": str(profile.pk),
                "points":       quantity,
                "type":         "points_purchase",
            },
        }
        resp = requests.post(
            "https://api.paystack.co/transaction/initialize",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                "Content-Type":  "application/json",
            },
            timeout=15,
        )
        data = resp.json()
        if not data.get("status"):
            raise Exception(data.get("message", "Paystack error"))

        purchase.paystack_access_code = data["data"]["access_code"]
        purchase.save()
        return redirect(data["data"]["authorization_url"])

    except Exception as e:
        purchase.status = PointsPurchase.Status.FAILED
        purchase.save()
        messages.error(request, f"Could not initiate payment: {e}")
        return redirect("sub-admin-buy-points")


def sub_admin_points_verify(request, reference):
    """Paystack redirects here after payment. Verify and credit points."""
    purchase = get_object_or_404(PointsPurchase, paystack_reference=reference)

    if purchase.status == PointsPurchase.Status.SUCCESS:
        messages.info(request, "This payment was already processed.")
        return redirect("sub-admin-buy-points")

    try:
        resp = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
            timeout=15,
        )
        data = resp.json()
        if data.get("status") and data["data"]["status"] == "success":
            _credit_points(purchase)
            messages.success(
                request,
                f"Payment confirmed! {purchase.points_bought} point(s) added to your account."
            )
        else:
            purchase.status = PointsPurchase.Status.FAILED
            purchase.save()
            messages.error(request, "Payment was not successful. Please try again.")
    except Exception as e:
        messages.error(request, f"Verification error: {e}")

    return redirect("sub-admin-buy-points")


def _credit_points(purchase):
    """Mark purchase successful and add points to sub-admin wallet."""
    purchase.status  = PointsPurchase.Status.SUCCESS
    purchase.paid_at = timezone.now()
    purchase.save()

    profile = purchase.sub_admin
    profile.points_balance += purchase.points_bought
    profile.save(update_fields=["points_balance"])


# ════════════════════════════════════════════════════════
#  SHIPMENTS
# ════════════════════════════════════════════════════════

@sub_admin_approved_required
def sub_admin_shipment_list(request):
    qs = Shipment.objects.filter(
        created_by=request.user
    ).select_related("sender", "receiver").order_by("-created_at")

    query  = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")

    if query:
        qs = qs.filter(
            Q(tracking_id__icontains=query)
            | Q(sender__full_name__icontains=query)
            | Q(receiver__full_name__icontains=query)
        )
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get("page"))
    profile   = request.user.sub_admin_profile

    context = {
        "page_obj":       page_obj,
        "query":          query,
        "status_filter":  status,
        "status_choices": Shipment.Status.choices,
        "profile":        profile,
        "can_create":     profile.can_create_shipment(),
        "pricing":        PointsPricing.get_current(),
    }
    return render(request, "admin/subadmin/shipment_list.html", context)


@sub_admin_has_points
def sub_admin_shipment_create(request):
    profile = request.user.sub_admin_profile
    pricing = PointsPricing.get_current()

    if request.method == "POST":
        p = request.POST

        # Re-check points on POST (race condition safety)
        if not profile.can_create_shipment():
            messages.error(request, "Insufficient points.")
            return redirect("sub-admin-buy-points")

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

        cost     = pricing.points_per_shipment
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
            status               = Shipment.Status.CREATED,
            origin_country       = p.get("origin_country", ""),
            destination_country  = p.get("destination_country", ""),
            estimated_delivery   = p.get("estimated_delivery") or None,
            special_instructions = p.get("special_instructions", ""),
            internal_notes       = p.get("internal_notes", ""),
            points_spent         = cost,
            driver_name           = p.get("driver_name", ""),
            driver_phone          = p.get("driver_phone", ""),
            driver_vehicle_info   = p.get("driver_vehicle_info", ""),
        )

        if request.FILES.get("driver_photo"):
            shipment.driver_photo = request.FILES["driver_photo"]
            shipment.save()

        Payment.objects.create(
            shipment = shipment,
            amount   = p.get("payment_amount", 0),
            currency = p.get("payment_currency", "NGN"),
            method   = p.get("payment_method", ""),
            status   = Payment.Status.UNPAID,
            reason   = p.get("payment_reason", ""),
            due_date = p.get("payment_due_date") or None,
        )

        for img_file in request.FILES.getlist("images"):
            ShipmentImage.objects.create(shipment=shipment, image=img_file)
        first_img = shipment.images.first()
        if first_img:
            first_img.is_primary = True
            first_img.save()

        # Deduct points AFTER shipment is saved successfully
        profile.deduct_points(cost)

        messages.success(
            request,
            f"Shipment created — Tracking ID: {shipment.tracking_id}. "
            f"{cost} point(s) deducted. Balance: {profile.points_balance} pts."
        )
        return redirect("sub-admin-shipment-list")

    context = {
        "shipment_types":    Shipment.ShipmentType.choices,
        "shipment_statuses": Shipment.Status.choices,
        "payment_methods":   Payment.Method.choices,
        "payment_statuses":  Payment.Status.choices,
        "pricing":           pricing,
        "profile":           profile,
    }
    return render(request, "admin/subadmin/shipment_form.html", context)


@sub_admin_approved_required
def sub_admin_shipment_detail(request, pk):
    shipment = get_object_or_404(
        Shipment.objects
            .select_related("sender", "receiver", "payment")
            .prefetch_related("checkpoints", "images"),
        pk=pk,
        created_by=request.user,
    )
    checkpoints = shipment.checkpoints.order_by("timestamp")
    map_points  = json.dumps([
        {
            "lat":      float(cp.latitude),
            "lng":      float(cp.longitude),
            "location": cp.location,
            "event":    cp.get_event_type_display(),
            "time":     cp.timestamp.strftime("%d %b %Y, %H:%M"),
        }
        for cp in checkpoints
        if cp.latitude and cp.longitude
    ])
    context = {
        "shipment":    shipment,
        "checkpoints": checkpoints,
        "map_points":  map_points,
        "payment":     getattr(shipment, "payment", None),
    }
    return render(request, "admin/subadmin/shipment_detail.html", context)


# ════════════════════════════════════════════════════════
#  SUPER ADMIN — SUB-ADMIN MANAGEMENT
# ════════════════════════════════════════════════════════

@super_admin_required
def manage_sub_admins(request):
    profiles = SubAdminProfile.objects.select_related(
        "user", "approved_by"
    ).order_by("-created_at")

    status_filter = request.GET.get("status", "")
    if status_filter:
        profiles = profiles.filter(approval_status=status_filter)

    paginator = Paginator(profiles, 20)
    page_obj  = paginator.get_page(request.GET.get("page"))
    pricing   = PointsPricing.get_current()

    context = {
        "page_obj":       page_obj,
        "status_filter":  status_filter,
        "status_choices": SubAdminProfile.ApprovalStatus.choices,
        "pricing":        pricing,
    }
    return render(request, "admin/manage_sub_admins.html", context)


@super_admin_required
@require_POST
def approve_sub_admin(request, pk):
    profile = get_object_or_404(SubAdminProfile, pk=pk)
    profile.approval_status = SubAdminProfile.ApprovalStatus.APPROVED
    profile.approved_by     = request.user
    profile.approved_at     = timezone.now()
    profile.save()
    messages.success(request, f"{profile.user.full_name} approved.")
    return redirect("manage-sub-admins")


@super_admin_required
@require_POST
def reject_sub_admin(request, pk):
    profile = get_object_or_404(SubAdminProfile, pk=pk)
    profile.approval_status  = SubAdminProfile.ApprovalStatus.REJECTED
    profile.rejection_reason = request.POST.get("rejection_reason", "")
    profile.save()
    messages.success(request, f"{profile.user.full_name} rejected.")
    return redirect("manage-sub-admins")


@super_admin_required
@require_POST
def suspend_sub_admin(request, pk):
    profile = get_object_or_404(SubAdminProfile, pk=pk)
    profile.approval_status = SubAdminProfile.ApprovalStatus.SUSPENDED
    profile.save()
    messages.success(request, f"{profile.user.full_name} suspended.")
    return redirect("manage-sub-admins")


@super_admin_required
@require_POST
def reinstate_sub_admin(request, pk):
    profile = get_object_or_404(SubAdminProfile, pk=pk)
    profile.approval_status = SubAdminProfile.ApprovalStatus.APPROVED
    profile.save()
    messages.success(request, f"{profile.user.full_name} reinstated.")
    return redirect("manage-sub-admins")


@super_admin_required
@require_POST
def set_points_pricing(request):
    """Super admin updates point costs and price per point."""
    pricing = PointsPricing.get_current()
    try:
        pricing.points_per_shipment          = int(request.POST.get("points_per_shipment", pricing.points_per_shipment))
        pricing.price_per_point              = Decimal(str(request.POST.get("price_per_point", pricing.price_per_point)))
        pricing.points_per_amendment         = int(request.POST.get("points_per_amendment", pricing.points_per_amendment))
        pricing.points_per_invoice           = int(request.POST.get("points_per_invoice", pricing.points_per_invoice))
        pricing.points_per_support_link      = int(request.POST.get("points_per_support_link", pricing.points_per_support_link))
        pricing.points_per_site_customization = int(request.POST.get("points_per_site_customization", pricing.points_per_site_customization))
        pricing.invoice_fee                  = Decimal(str(request.POST.get("invoice_fee", pricing.invoice_fee)))
        pricing.currency                     = request.POST.get("currency", pricing.currency)
        pricing.updated_by                   = request.user
        pricing.save()
        messages.success(
            request,
            f"Pricing updated: {pricing.points_per_shipment} pts/shipment | "
            f"{pricing.points_per_invoice} pts/invoice | "
            f"{pricing.points_per_site_customization} pts/landing-page | "
            f"{pricing.currency} {pricing.price_per_point}/pt | "
            f"{pricing.currency} {pricing.invoice_fee} invoice fee"
        )
    except (ValueError, TypeError, InvalidOperation):
        messages.error(request, "Invalid values.")
    return redirect("manage-sub-admins")


@super_admin_required
@require_POST
def admin_adjust_points(request, pk):
    """Super admin manually add or remove points from a sub-admin."""
    profile = get_object_or_404(SubAdminProfile, pk=pk)
    try:
        amount = int(request.POST.get("amount", 0))
        action = request.POST.get("action", "add")
        if action == "add":
            profile.points_balance += amount
            profile.save(update_fields=["points_balance"])
            messages.success(request, f"Added {amount} pts to {profile.user.full_name}. New balance: {profile.points_balance}.")
        elif action == "deduct":
            if profile.points_balance < amount:
                messages.error(request, "Cannot deduct more than current balance.")
            else:
                profile.points_balance -= amount
                profile.save(update_fields=["points_balance"])
                messages.success(request, f"Deducted {amount} pts from {profile.user.full_name}. New balance: {profile.points_balance}.")
    except (ValueError, TypeError):
        messages.error(request, "Invalid amount.")
    return redirect("sub-admin-detail", pk=pk)


@super_admin_required
def sub_admin_detail(request, pk):
    profile       = get_object_or_404(SubAdminProfile.objects.select_related("user"), pk=pk)
    shipments     = Shipment.objects.filter(created_by=profile.user).order_by("-created_at")[:20]
    purchases     = profile.point_purchases.order_by("-created_at")

    context = {
        "profile":   profile,
        "shipments": shipments,
        "purchases": purchases,
        "pricing":   PointsPricing.get_current(),
    }
    return render(request, "admin/sub_admin_detail.html", context)


def sub_admin_landing(request):
    if request.user.is_authenticated and request.user.role == User.Role.SUB_ADMIN:
        return redirect("sub-admin-dashboard")
    return render(request, "admin/subadmin/landing.html")


# ════════════════════════════════════════════════════════
#  CHECKPOINTS — sync shipment status from checkpoint events
# ════════════════════════════════════════════════════════

# Statuses that represent one of the 5 stepper stages shown on the
# public tracking page.
PROGRESS_STATUSES = {
    Shipment.Status.CREATED,
    Shipment.Status.PICKED_UP,
    Shipment.Status.IN_TRANSIT,
    Shipment.Status.AT_CUSTOMS,
    Shipment.Status.OUT_FOR_DELIVERY,
    Shipment.Status.DELIVERED,
}

# Same statuses, in stepper order — used to prevent status moving backward.
PROGRESS_ORDER = [
    Shipment.Status.CREATED,
    Shipment.Status.PICKED_UP,
    Shipment.Status.IN_TRANSIT,
    Shipment.Status.AT_CUSTOMS,
    Shipment.Status.OUT_FOR_DELIVERY,
    Shipment.Status.DELIVERED,
]

CHECKPOINT_TO_STATUS = {
    TransitCheckpoint.EventType.PICKUP:           Shipment.Status.PICKED_UP,
    TransitCheckpoint.EventType.DEPARTED:         Shipment.Status.IN_TRANSIT,
    TransitCheckpoint.EventType.ARRIVED:          Shipment.Status.IN_TRANSIT,
    TransitCheckpoint.EventType.IN_TRANSIT:       Shipment.Status.IN_TRANSIT,
    TransitCheckpoint.EventType.CUSTOMS_IN:       Shipment.Status.AT_CUSTOMS,
    TransitCheckpoint.EventType.CUSTOMS_CLEARED:  Shipment.Status.AT_CUSTOMS,
    TransitCheckpoint.EventType.OUT_FOR_DELIVERY: Shipment.Status.OUT_FOR_DELIVERY,
    TransitCheckpoint.EventType.DELIVERED:        Shipment.Status.DELIVERED,
    TransitCheckpoint.EventType.ATTEMPTED:        Shipment.Status.OUT_FOR_DELIVERY,
    TransitCheckpoint.EventType.HELD:             Shipment.Status.HELD,
    TransitCheckpoint.EventType.EXCEPTION:        None,  # no direct status mapping
}


def get_progress_status(shipment, checkpoints):
    """
    Returns the stepper-relevant status: the shipment's own status if
    it's one of the five progress stages, otherwise (held/returned/
    cancelled) falls back to the last progress stage reached, inferred
    from checkpoint history.
    """
    if shipment.status in PROGRESS_STATUSES:
        return shipment.status

    for cp in checkpoints.order_by("-timestamp"):
        mapped = CHECKPOINT_TO_STATUS.get(cp.event_type)
        if mapped in PROGRESS_STATUSES:
            return mapped

    return Shipment.Status.CREATED


@sub_admin_approved_required
@require_POST
def sub_admin_checkpoint_add(request, pk):
    shipment = get_object_or_404(Shipment, pk=pk, created_by=request.user)
    p = request.POST

    TransitCheckpoint.objects.create(
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

    # ── Sync shipment.status from the checkpoint event_type ──────
    new_status = CHECKPOINT_TO_STATUS.get(p["event_type"])
    if new_status:
        if new_status in PROGRESS_STATUSES and shipment.status in PROGRESS_STATUSES:
            # Only move forward along the stepper, never backward
            if PROGRESS_ORDER.index(new_status) > PROGRESS_ORDER.index(shipment.status):
                shipment.status = new_status
                shipment.save(update_fields=["status"])
        else:
            # e.g. HELD — apply directly regardless of ordering
            shipment.status = new_status
            shipment.save(update_fields=["status"])
    # ───────────────────────────────────────────────────────────

    messages.success(request, "Checkpoint added.")
    return redirect("sub-admin-shipment-detail", pk=pk)


# ════════════════════════════════════════════════════════
#  SHIPMENT AMENDMENT
# ════════════════════════════════════════════════════════

@sub_admin_approved_required
def sub_admin_shipment_amend_form(request, pk):
    """Render the amendment form (GET)."""
    shipment = get_object_or_404(
        Shipment.objects.select_related("sender", "receiver", "payment"),
        pk=pk, created_by=request.user
    )
    profile = request.user.sub_admin_profile
    pricing = PointsPricing.get_current()

    context = {
        "shipment":           shipment,
        "profile":             profile,
        "pricing":             pricing,
        "cost":                pricing.points_per_amendment,
        "is_first_amendment":  shipment.amendment_count == 0,
        "shipment_types":      Shipment.ShipmentType.choices,
        "payment_methods":     Payment.Method.choices,
        "payment":             getattr(shipment, "payment", None),
    }
    return render(request, "admin/subadmin/shipment_amend.html", context)


@sub_admin_approved_required
@require_POST
def sub_admin_shipment_amend(request, pk):
    """Process the amendment form (POST) — same field set as shipment_create."""
    shipment = get_object_or_404(
        Shipment.objects.select_related("sender", "receiver"),
        pk=pk, created_by=request.user
    )
    profile  = request.user.sub_admin_profile
    pricing  = PointsPricing.get_current()
    cost     = pricing.points_per_amendment

    if profile.points_balance < cost:
        messages.error(
            request,
            f"You need {cost} point(s) to amend this shipment. "
            f"You have {profile.points_balance}."
        )
        return redirect("sub-admin-shipment-amend-form", pk=pk)

    p = request.POST

    # ── Update sender ──────────────────────────────────────────
    sender = shipment.sender
    sender.full_name   = p.get("sender_name", sender.full_name)
    sender.email       = p.get("sender_email", sender.email)
    sender.phone       = p.get("sender_phone", sender.phone)
    sender.address     = p.get("sender_address", sender.address)
    sender.city        = p.get("sender_city", sender.city)
    sender.state       = p.get("sender_state", sender.state)
    sender.country     = p.get("sender_country", sender.country)
    sender.postal_code = p.get("sender_postal", sender.postal_code)
    sender.company     = p.get("sender_company", sender.company)
    sender.save()

    # ── Update receiver ─────────────────────────────────────────
    receiver = shipment.receiver
    receiver.full_name   = p.get("receiver_name", receiver.full_name)
    receiver.email       = p.get("receiver_email", receiver.email)
    receiver.phone       = p.get("receiver_phone", receiver.phone)
    receiver.address     = p.get("receiver_address", receiver.address)
    receiver.city        = p.get("receiver_city", receiver.city)
    receiver.state       = p.get("receiver_state", receiver.state)
    receiver.country     = p.get("receiver_country", receiver.country)
    receiver.postal_code = p.get("receiver_postal", receiver.postal_code)
    receiver.company     = p.get("receiver_company", receiver.company)
    receiver.save()

    # ── Update shipment fields ──────────────────────────────────
    shipment.shipment_type        = p.get("shipment_type", shipment.shipment_type)
    shipment.description          = p.get("description", shipment.description)
    shipment.weight_kg            = p.get("weight_kg") or None
    shipment.dimensions           = p.get("dimensions", shipment.dimensions)
    shipment.quantity             = p.get("quantity", shipment.quantity)
    shipment.declared_value       = p.get("declared_value") or None
    shipment.currency             = p.get("currency", shipment.currency)
    shipment.origin_country       = p.get("origin_country", shipment.origin_country)
    shipment.destination_country  = p.get("destination_country", shipment.destination_country)
    shipment.estimated_delivery   = p.get("estimated_delivery") or None
    shipment.special_instructions = p.get("special_instructions", shipment.special_instructions)
    shipment.internal_notes       = p.get("internal_notes", shipment.internal_notes)
    shipment.driver_name          = p.get("driver_name", shipment.driver_name)
    shipment.driver_phone         = p.get("driver_phone", shipment.driver_phone)
    shipment.driver_vehicle_info  = p.get("driver_vehicle_info", shipment.driver_vehicle_info)

    # ── Update payment (create if missing) ──────────────────────
    payment = getattr(shipment, "payment", None)
    if payment:
        payment.amount   = p.get("payment_amount", payment.amount)
        payment.currency = p.get("payment_currency", payment.currency)
        payment.method   = p.get("payment_method", payment.method)
        payment.reason   = p.get("payment_reason", payment.reason)
        payment.due_date = p.get("payment_due_date") or None
        payment.save()
    else:
        Payment.objects.create(
            shipment = shipment,
            amount   = p.get("payment_amount", 0),
            currency = p.get("payment_currency", "NGN"),
            method   = p.get("payment_method", ""),
            status   = Payment.Status.UNPAID,
            reason   = p.get("payment_reason", ""),
            due_date = p.get("payment_due_date") or None,
        )

    # ── Remove images the user checked off ──────────────────────
    remove_ids = request.POST.getlist("remove_images")
    if remove_ids:
        ShipmentImage.objects.filter(shipment=shipment, id__in=remove_ids).delete()

    # ── Add new images — NO LIMIT, every uploaded file is saved ──
    new_images = request.FILES.getlist("images")
    for img_file in new_images:
        ShipmentImage.objects.create(shipment=shipment, image=img_file)

    # Ensure exactly one primary image if any images remain
    if not shipment.images.filter(is_primary=True).exists():
        first_img = shipment.images.first()
        if first_img:
            first_img.is_primary = True
            first_img.save()

    # ── Deduct points and save ───────────────────────────────────
    profile.deduct_points(cost)
    shipment.amendment_count += 1
    shipment.points_spent    += cost
    shipment.save()

    messages.success(
        request,
        f"Shipment updated. {cost} point(s) deducted. "
        f"Balance: {profile.points_balance} pts. "
        f"{len(new_images)} new image(s) added"
        + (f", {len(remove_ids)} removed." if remove_ids else ".")
    )
    return redirect("sub-admin-shipment-detail", pk=pk)


# ════════════════════════════════════════════════════════
#  PROFILE
# ════════════════════════════════════════════════════════

@sub_admin_approved_required
def sub_admin_profile(request):
    profile = request.user.sub_admin_profile
    pricing = PointsPricing.get_current()

    if request.method == "POST":
        action = request.POST.get("action")

        # ── Update profile info (name, email, whatsapp) ──────────
        if action == "update_profile":
            full_name = request.POST.get("full_name", "").strip()
            email     = request.POST.get("email", "").strip().lower()
            whatsapp  = request.POST.get("whatsapp_number", "").strip()

            if email and email != request.user.email:
                if User.objects.filter(email=email).exclude(pk=request.user.pk).exists():
                    messages.error(request, "That email is already in use by another account.")
                    return redirect("sub-admin-profile")
                request.user.email = email

            if full_name:
                request.user.full_name = full_name
            request.user.save()

            profile.whatsapp_number = whatsapp
            profile.save(update_fields=["whatsapp_number"])

            messages.success(request, "Profile updated successfully.")
            return redirect("sub-admin-profile")

        # ── Avatar upload ─────────────────────────────────────────
        elif action == "update_avatar":
            avatar = request.FILES.get("avatar")
            if not avatar:
                messages.error(request, "Please choose an image to upload.")
                return redirect("sub-admin-profile")

            if not avatar.content_type.startswith("image/"):
                messages.error(request, "File must be an image.")
                return redirect("sub-admin-profile")

            profile.avatar = avatar
            profile.save(update_fields=["avatar"])
            messages.success(request, "Profile photo updated.")
            return redirect("sub-admin-profile")

        # ── Change password ───────────────────────────────────────
        elif action == "change_password":
            old_password     = request.POST.get("old_password", "")
            new_password     = request.POST.get("new_password", "")
            confirm_password = request.POST.get("confirm_password", "")

            if not request.user.check_password(old_password):
                messages.error(request, "Your current password is incorrect.")
            elif len(new_password) < 8:
                messages.error(request, "New password must be at least 8 characters.")
            elif new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
            else:
                request.user.set_password(new_password)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, "Password changed successfully.")

            return redirect("sub-admin-profile")

        # ── Delete account ────────────────────────────────────────
        elif action == "delete_account":
            user = request.user
            uid  = user.pk

            logout(request)

            # Anonymize instead of hard-deleting, so historical
            # shipments / payments keep a valid FK reference.
            user.full_name   = "Deleted User"
            user.email       = f"deleted_user_{uid}@transedge.invalid"
            user.is_active   = False
            user.set_unusable_password()
            user.save()

            messages.success(request, "Your account has been deleted.")
            return redirect("home")

    context = {
        "profile":       profile,
        "pricing":       pricing,
        "referral_link": profile.get_referral_link(request),
    }
    return render(request, "admin/subadmin/profile.html", context)


# ════════════════════════════════════════════════════════
#  SHIPMENT ADD-ONS
# ════════════════════════════════════════════════════════
from django.core.validators import validate_email
from django.core.exceptions import ValidationError


@sub_admin_approved_required
def sub_admin_shipment_addons(request, pk):
    """Manage optional add-ons for a shipment (e.g. support contact link/email)."""
    shipment = get_object_or_404(Shipment, pk=pk, created_by=request.user)
    profile  = request.user.sub_admin_profile
    pricing  = PointsPricing.get_current()

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "save_support_link":
            link_type = request.POST.get("support_link_type", "link").strip()
            if link_type not in ("link", "email"):
                link_type = "link"

            url   = request.POST.get("support_link_url", "").strip()
            label = request.POST.get("support_link_label", "").strip() or "Chat with Support"

            if not url:
                field_name = "email address" if link_type == "email" else "link/URL"
                messages.error(request, f"Please provide a {field_name}.")
                return redirect("sub-admin-shipment-addons", pk=pk)

            if link_type == "email":
                try:
                    validate_email(url)
                except ValidationError:
                    messages.error(request, "Please provide a valid email address.")
                    return redirect("sub-admin-shipment-addons", pk=pk)
            else:
                if not (url.startswith("http://") or url.startswith("https://")):
                    messages.error(request, "Link must start with http:// or https://")
                    return redirect("sub-admin-shipment-addons", pk=pk)

            cost = pricing.points_per_support_link
            if profile.points_balance < cost:
                messages.error(
                    request,
                    f"You need {cost} point(s) to set/update the support contact. "
                    f"You have {profile.points_balance}."
                )
                return redirect("sub-admin-buy-points")

            profile.deduct_points(cost)
            shipment.support_link_type   = link_type
            shipment.support_link_url    = url
            shipment.support_link_label  = label
            shipment.support_link_active = True
            shipment.save(update_fields=[
                "support_link_type",
                "support_link_url",
                "support_link_label",
                "support_link_active",
            ])

            contact_desc = "Support email" if link_type == "email" else "Support link"
            messages.success(
                request,
                f"{contact_desc} saved and activated. {cost} point(s) deducted. "
                f"Balance: {profile.points_balance} pts."
            )
            return redirect("sub-admin-shipment-addons", pk=pk)

        elif action == "toggle_support_link":
            # Free toggle — no charge, just show/hide on client page
            shipment.support_link_active = not shipment.support_link_active
            shipment.save(update_fields=["support_link_active"])
            state = "enabled" if shipment.support_link_active else "disabled"
            messages.success(request, f"Support contact {state}.")
            return redirect("sub-admin-shipment-addons", pk=pk)

    context = {
        "shipment": shipment,
        "profile":  profile,
        "pricing":  pricing,
    }
    return render(request, "admin/subadmin/shipment_addons.html", context)


# ════════════════════════════════════════════════════════
#  INVOICES
# ════════════════════════════════════════════════════════

@sub_admin_approved_required
def sub_admin_invoice_create(request, pk):
    shipment = get_object_or_404(Shipment, pk=pk, created_by=request.user)

    if hasattr(shipment, "invoice"):
        messages.info(request, "An invoice already exists for this shipment.")
        return redirect("sub-admin-invoice-detail", pk=shipment.invoice.pk)

    profile = request.user.sub_admin_profile
    pricing = PointsPricing.get_current()
    cost    = pricing.points_per_invoice

    if profile.points_balance < cost:
        messages.error(
            request,
            f"You need {cost} point(s) to create an invoice. "
            f"You have {profile.points_balance}. Please top up."
        )
        return redirect("sub-admin-buy-points")

    invoice = Invoice.objects.create(
        shipment        = shipment,
        created_by      = request.user,
        bill_to_name    = shipment.receiver.full_name,
        bill_to_email   = shipment.receiver.email,
        bill_to_address = f"{shipment.receiver.address}, {shipment.receiver.city}, {shipment.receiver.country}".strip(", "),
        currency        = shipment.currency,
        due_date        = timezone.now().date() + timedelta(days=7),
    )
    InvoiceItem.objects.create(
        invoice     = invoice,
        description = f"{shipment.get_shipment_type_display()} shipment — {shipment.tracking_id}",
        quantity    = 1,
        unit_price  = shipment.declared_value or 0,
    )

    if pricing.invoice_fee:
        InvoiceItem.objects.create(
            invoice     = invoice,
            description = "Invoice processing fee",
            quantity    = 1,
            unit_price  = pricing.invoice_fee,
        )

    invoice.recalculate_totals()

    # Deduct points AFTER invoice is fully created — mirrors shipment_create
    profile.deduct_points(cost)

    messages.success(
        request,
        f"Invoice {invoice.invoice_number} created. "
        f"{cost} point(s) deducted. Balance: {profile.points_balance} pts."
    )
    return redirect("sub-admin-invoice-detail", pk=invoice.pk)


@sub_admin_approved_required
def sub_admin_invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related("shipment", "shipment__sender", "shipment__receiver")
                       .prefetch_related("items"),
        pk=pk, shipment__created_by=request.user,
    )
    return render(request, "admin/subadmin/invoice_detail.html", {"invoice": invoice})


@sub_admin_approved_required
@require_POST
def sub_admin_invoice_update(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, shipment__created_by=request.user)
    p = request.POST

    invoice.bill_to_name    = p.get("bill_to_name", invoice.bill_to_name)
    invoice.bill_to_email   = p.get("bill_to_email", invoice.bill_to_email)
    invoice.bill_to_address = p.get("bill_to_address", invoice.bill_to_address)
    invoice.due_date        = p.get("due_date") or invoice.due_date

    tax_rate_raw = p.get("tax_rate")
    if tax_rate_raw:
        try:
            invoice.tax_rate = Decimal(tax_rate_raw)
        except InvalidOperation:
            messages.error(request, "Invalid tax rate.")
            return redirect("sub-admin-invoice-detail", pk=pk)

    discount_raw = p.get("discount_amount")
    if discount_raw:
        try:
            invoice.discount_amount = Decimal(discount_raw)
        except InvalidOperation:
            messages.error(request, "Invalid discount amount.")
            return redirect("sub-admin-invoice-detail", pk=pk)

    invoice.notes  = p.get("notes", invoice.notes)
    invoice.status = p.get("status", invoice.status)
    invoice.save()
    invoice.recalculate_totals()

    messages.success(request, "Invoice updated.")
    return redirect("sub-admin-invoice-detail", pk=pk)


@sub_admin_approved_required
@require_POST
def sub_admin_invoice_add_item(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, shipment__created_by=request.user)
    InvoiceItem.objects.create(
        invoice     = invoice,
        description = request.POST.get("description", ""),
        quantity    = request.POST.get("quantity") or 1,
        unit_price  = request.POST.get("unit_price") or 0,
    )
    invoice.recalculate_totals()
    messages.success(request, "Line item added.")
    return redirect("sub-admin-invoice-detail", pk=pk)


@sub_admin_approved_required
@require_POST
def sub_admin_invoice_remove_item(request, pk, item_pk):
    item = get_object_or_404(
        InvoiceItem, pk=item_pk, invoice__pk=pk, invoice__shipment__created_by=request.user
    )
    invoice = item.invoice
    item.delete()
    invoice.recalculate_totals()
    messages.success(request, "Line item removed.")
    return redirect("sub-admin-invoice-detail", pk=pk)


@sub_admin_approved_required
@require_POST
def sub_admin_invoice_mark_paid(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, shipment__created_by=request.user)
    invoice.mark_paid()
    messages.success(request, f"Invoice {invoice.invoice_number} marked as paid.")
    return redirect("sub-admin-invoice-detail", pk=pk)


@sub_admin_approved_required
def sub_admin_invoice_pdf(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related("shipment", "shipment__sender", "shipment__receiver")
                       .prefetch_related("items"),
        pk=pk, shipment__created_by=request.user,
    )
    html = render_to_string("admin/subadmin/invoice_pdf.html", {"invoice": invoice})

    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer, link_callback=link_callback)
    if result.err:
        messages.error(request, "Could not generate PDF.")
        return redirect("sub-admin-invoice-detail", pk=pk)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{invoice.invoice_number}.pdf"'
    return response


def link_callback(uri, rel):
    """
    Resolves static/media URLs to absolute filesystem paths so
    xhtml2pdf can embed images (logos, watermarks) in the PDF.
    """
    if uri.startswith(settings.STATIC_URL):
        path = os.path.join(settings.STATIC_ROOT or settings.BASE_DIR / "static", uri.replace(settings.STATIC_URL, ""))
    elif uri.startswith(settings.MEDIA_URL):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
    else:
        return uri  # already an absolute path or external URL

    if not os.path.isfile(path):
        raise Exception(f"Static/media file not found for PDF: {path}")
    return path


# ════════════════════════════════════════════════════════
#  5SIM FOREIGN NUMBERS
#  Sub-admin only. Uses Account (NGN wallet), separate from points.
# ════════════════════════════════════════════════════════

def get_or_create_account(user):
    account, _ = Account.objects.get_or_create(user=user)
    return account


def get_owner_account():
    """
    Optional revenue-tracking account. Returns None if unconfigured
    rather than blocking purchases — set SITE_OWNER_EMAIL in .env
    to enable it.
    """
    owner_email = config("SITE_OWNER_EMAIL", default="")
    if not owner_email:
        return None
    try:
        owner_user = User.objects.get(email=owner_email)
        return Account.objects.get(user=owner_user)
    except (User.DoesNotExist, Account.DoesNotExist):
        logger.warning(f"SITE_OWNER_EMAIL '{owner_email}' has no matching Account — skipping owner credit.")
        return None


FOREIGN_COUNTRIES = [
    "usa", "uk", "canada", "russia", "india", "indonesia",
    "afghanistan", "albania", "algeria", "angola", "argentina",
    "armenia", "australia", "austria", "azerbaijan", "bahrain",
    "bangladesh", "belarus", "belgium", "brazil", "bulgaria",
    "china", "egypt", "france", "germany", "ghana", "italy",
    "japan", "kenya", "malaysia", "mexico", "netherlands",
    "nigeria", "pakistan", "philippines", "poland", "saudi_arabia",
    "singapore", "south_africa", "spain", "sweden", "switzerland",
    "thailand", "turkey", "ukraine", "uae", "vietnam",
]

FOREIGN_COUNTRY_DISPLAY = {
    "usa":          ("United States",        "US", "🇺🇸"),
    "uk":           ("United Kingdom",       "GB", "🇬🇧"),
    "canada":       ("Canada",               "CA", "🇨🇦"),
    "russia":       ("Russia",               "RU", "🇷🇺"),
    "india":        ("India",                "IN", "🇮🇳"),
    "indonesia":    ("Indonesia",            "ID", "🇮🇩"),
    "afghanistan":  ("Afghanistan",          "AF", "🇦🇫"),
    "albania":      ("Albania",              "AL", "🇦🇱"),
    "algeria":      ("Algeria",              "DZ", "🇩🇿"),
    "angola":       ("Angola",               "AO", "🇦🇴"),
    "argentina":    ("Argentina",            "AR", "🇦🇷"),
    "armenia":      ("Armenia",              "AM", "🇦🇲"),
    "australia":    ("Australia",            "AU", "🇦🇺"),
    "austria":      ("Austria",              "AT", "🇦🇹"),
    "azerbaijan":   ("Azerbaijan",           "AZ", "🇦🇿"),
    "bahrain":      ("Bahrain",              "BH", "🇧🇭"),
    "bangladesh":   ("Bangladesh",           "BD", "🇧🇩"),
    "belarus":      ("Belarus",              "BY", "🇧🇾"),
    "belgium":      ("Belgium",              "BE", "🇧🇪"),
    "brazil":       ("Brazil",               "BR", "🇧🇷"),
    "bulgaria":     ("Bulgaria",             "BG", "🇧🇬"),
    "china":        ("China",                "CN", "🇨🇳"),
    "egypt":        ("Egypt",                "EG", "🇪🇬"),
    "france":       ("France",               "FR", "🇫🇷"),
    "germany":      ("Germany",              "DE", "🇩🇪"),
    "ghana":        ("Ghana",                "GH", "🇬🇭"),
    "italy":        ("Italy",                "IT", "🇮🇹"),
    "japan":        ("Japan",                "JP", "🇯🇵"),
    "kenya":        ("Kenya",                "KE", "🇰🇪"),
    "malaysia":     ("Malaysia",             "MY", "🇲🇾"),
    "mexico":       ("Mexico",               "MX", "🇲🇽"),
    "netherlands":  ("Netherlands",          "NL", "🇳🇱"),
    "nigeria":      ("Nigeria",              "NG", "🇳🇬"),
    "pakistan":     ("Pakistan",             "PK", "🇵🇰"),
    "philippines":  ("Philippines",          "PH", "🇵🇭"),
    "poland":       ("Poland",               "PL", "🇵🇱"),
    "saudi_arabia": ("Saudi Arabia",         "SA", "🇸🇦"),
    "singapore":    ("Singapore",            "SG", "🇸🇬"),
    "south_africa": ("South Africa",         "ZA", "🇿🇦"),
    "spain":        ("Spain",                "ES", "🇪🇸"),
    "sweden":       ("Sweden",               "SE", "🇸🇪"),
    "switzerland":  ("Switzerland",          "CH", "🇨🇭"),
    "thailand":     ("Thailand",             "TH", "🇹🇭"),
    "turkey":       ("Turkey",               "TR", "🇹🇷"),
    "ukraine":      ("Ukraine",              "UA", "🇺🇦"),
    "uae":          ("United Arab Emirates", "AE", "🇦🇪"),
    "vietnam":      ("Vietnam",              "VN", "🇻🇳"),
}

FOREIGN_SERVICES = [
    "whatsapp", "telegram", "google", "facebook",
    "instagram", "twitter", "tiktok", "snapchat",
    "discord", "netflix", "amazon", "microsoft",
    "apple", "uber", "airbnb", "spotify",
    "paypal", "linkedin", "viber", "line",
]

FOREIGN_SERVICE_DISPLAY = {
    "whatsapp":  ("WhatsApp",   "💬"),
    "telegram":  ("Telegram",   "✈️"),
    "google":    ("Google",     "🔍"),
    "facebook":  ("Facebook",   "📘"),
    "instagram": ("Instagram",  "📸"),
    "twitter":   ("Twitter/X",  "🐦"),
    "tiktok":    ("TikTok",     "🎵"),
    "snapchat":  ("Snapchat",   "👻"),
    "discord":   ("Discord",    "🎮"),
    "netflix":   ("Netflix",    "🎬"),
    "amazon":    ("Amazon",     "📦"),
    "microsoft": ("Microsoft",  "🪟"),
    "apple":     ("Apple",      "🍎"),
    "uber":      ("Uber",       "🚗"),
    "airbnb":    ("Airbnb",     "🏠"),
    "spotify":   ("Spotify",    "🎧"),
    "paypal":    ("PayPal",     "💳"),
    "linkedin":  ("LinkedIn",   "💼"),
    "viber":     ("Viber",      "📞"),
    "line":      ("Line",       "🟢"),
}

FIVESIM_COUNTRY_MAP = {
    "usa": "usa", "uk": "england", "canada": "canada", "russia": "russia",
    "india": "india", "indonesia": "indonesia", "afghanistan": "afghanistan",
    "albania": "albania", "algeria": "algeria", "angola": "angola",
    "argentina": "argentina", "armenia": "armenia", "australia": "australia",
    "austria": "austria", "azerbaijan": "azerbaijan", "bahrain": "bahrain",
    "bangladesh": "bangladesh", "belarus": "belarus", "belgium": "belgium",
    "brazil": "brazil", "bulgaria": "bulgaria", "china": "china",
    "egypt": "egypt", "france": "france", "germany": "germany",
    "ghana": "ghana", "italy": "italy", "japan": "japan", "kenya": "kenya",
    "malaysia": "malaysia", "mexico": "mexico", "netherlands": "netherlands",
    "nigeria": "nigeria", "pakistan": "pakistan", "philippines": "philippines",
    "poland": "poland", "saudi_arabia": "saudiarabia", "singapore": "singapore",
    "south_africa": "southafrica", "spain": "spain", "sweden": "sweden",
    "switzerland": "switzerland", "thailand": "thailand", "turkey": "turkey",
    "ukraine": "ukraine", "uae": "uae", "vietnam": "vietnam",
}

FIVESIM_SERVICE_MAP = {
    "whatsapp": "whatsapp", "telegram": "telegram", "google": "google",
    "facebook": "facebook", "instagram": "instagram", "twitter": "twitter",
    "tiktok": "tiktok", "snapchat": "snapchat", "discord": "discord",
    "netflix": "netflix", "amazon": "amazon", "microsoft": "microsoft",
    "apple": "apple", "uber": "uber", "airbnb": "airbnb", "spotify": "spotify",
    "paypal": "paypal", "linkedin": "linkedin", "viber": "viber", "line": "line",
}


def _ngn_price(usd_price):
    def clean(val):
        return str(val).split("#")[0].strip().strip('"').strip("'")
    try:
        rate   = Decimal(clean(config("USD_TO_NGN_RATE",      default="1600")))
        markup = Decimal(clean(config("FOREIGN_NUMBER_MARKUP", default="1.3")))
    except Exception as e:
        logger.error(f"_ngn_price config error: {e}")
        rate, markup = Decimal("1600"), Decimal("1.3")
    ngn = Decimal(str(usd_price)) * rate * markup
    return Decimal(str(math.ceil(float(ngn) / 10) * 10))


def _fivesim_headers():
    return {
        "Authorization": f"Bearer {config('FIVE_SIM_API_KEY').strip()}",
        "Accept": "application/json",
    }


def _fetch_5sim_prices(country=None, service=None):
    try:
        response = requests.get("https://5sim.net/v1/guest/prices", timeout=30)
        data     = response.json()
    except Exception as e:
        logger.error(f"5SIM price fetch error: {e}")
        return []
    prices    = []
    countries = [country] if country else FOREIGN_COUNTRIES
    services  = [service] if service  else FOREIGN_SERVICES
    for c in countries:
        fivesim_c = FIVESIM_COUNTRY_MAP.get(c, c)
        if fivesim_c not in data:
            continue
        for s in services:
            fivesim_s = FIVESIM_SERVICE_MAP.get(s, s)
            if fivesim_s not in data[fivesim_c]:
                continue
            for operator_name, operator_data in data[fivesim_c][fivesim_s].items():
                usd = operator_data.get("cost", 0)
                prices.append({
                    "country":   c,
                    "service":   s,
                    "operator":  operator_name,
                    "price_usd": usd,
                    "price_ngn": float(_ngn_price(usd)),
                    "price":     float(_ngn_price(usd)),
                    "count":     operator_data.get("count", 0),
                })
    return prices


@sub_admin_approved_required
def sub_admin_buy_foreign_number(request):
    account = get_or_create_account(request.user)
    selected_country = request.GET.get("country", "") or request.POST.get("country", "")
    selected_service = request.GET.get("service", "") or request.POST.get("service", "")
    prices = []
    if selected_country and selected_service:
        prices = _fetch_5sim_prices(
            country=selected_country if selected_country in FOREIGN_COUNTRIES else None,
            service=selected_service if selected_service in FOREIGN_SERVICES  else None,
        )

    if request.method == "POST":
        country = request.POST.get("country", "").strip().lower()
        service = request.POST.get("service", "").strip().lower()
        if not country or not service:
            messages.error(request, "Please select a country and service.")
            return redirect("sub-admin-buy-foreign-number")
        if country not in FOREIGN_COUNTRIES or service not in FOREIGN_SERVICES:
            messages.error(request, "Invalid country or service selected.")
            return redirect("sub-admin-buy-foreign-number")

        plan_prices = _fetch_5sim_prices(country=country, service=service)
        available   = [p for p in plan_prices if p["count"] > 0]
        if not available:
            messages.error(request, "No available numbers right now. Try another country or service.")
            url = reverse("sub-admin-buy-foreign-number")
            return redirect(f"{url}?country={country}&service={service}")

        cheapest       = min(available, key=lambda x: x["price_ngn"])
        selected_price = Decimal(str(cheapest["price_ngn"]))

        if account.balance < selected_price:
            messages.error(request, f"Insufficient balance. You need ₦{selected_price:,} for this number.")
            return redirect("sub-admin-buy-foreign-number")

        owner_account   = get_owner_account()
        is_owner_buying = owner_account is not None and account.pk == owner_account.pk

        with db_transaction.atomic():
            account.balance -= selected_price
            account.save()
            if owner_account and not is_owner_buying:
                owner_account.balance += selected_price
                owner_account.save()

        fivesim_country = FIVESIM_COUNTRY_MAP.get(country, country)
        fivesim_service = FIVESIM_SERVICE_MAP.get(service, service)

        try:
            buy_url  = f"https://5sim.net/v1/user/buy/activation/{fivesim_country}/any/{fivesim_service}"
            response = requests.get(buy_url, headers=_fivesim_headers(), timeout=30)

            if response.status_code == 200:
                data = response.json()
                ForeignNumber.objects.create(
                    user=request.user,
                    order_id=data.get("id"),
                    country=country,
                    service=service,
                    phone_number=data.get("phone"),
                    price=selected_price,
                    status=ForeignNumber.Status.PENDING,
                    provider="5sim",
                )
                messages.success(request, f"Number {data.get('phone')} purchased successfully!")
            else:
                with db_transaction.atomic():
                    account.balance += selected_price
                    account.save()
                    if owner_account and not is_owner_buying:
                        owner_account.balance -= selected_price
                        owner_account.save()
                err_msg = f"HTTP {response.status_code}"
                try:
                    err_data = response.json()
                    err_msg  = err_data.get("message") or err_data.get("error") or str(err_data)
                except Exception:
                    if response.text.strip():
                        err_msg = response.text.strip()
                logger.error(f"5SIM buy failed: HTTP {response.status_code} | {err_msg}")
                err_lower = str(err_msg).lower()
                if "no free phones" in err_lower or "no numbers" in err_lower:
                    messages.error(request, "No available numbers right now. Try another country or service.")
                elif "not enough" in err_lower and "balance" in err_lower:
                    messages.error(request, "5SIM provider balance is low. Contact support.")
                elif response.status_code == 401:
                    messages.error(request, "5SIM authentication error. Contact support.")
                else:
                    messages.error(request, f"Purchase failed ({response.status_code}): {err_msg}. Balance refunded.")

        except Exception as e:
            with db_transaction.atomic():
                account.balance += selected_price
                account.save()
                if owner_account and not is_owner_buying:
                    owner_account.balance -= selected_price
                    owner_account.save()
            logger.error(f"5SIM buy exception: {e}")
            messages.error(request, "Something went wrong. Your balance has been refunded.")

        url = reverse("sub-admin-buy-foreign-number")
        return redirect(f"{url}?country={country}&service={service}")

    numbers = ForeignNumber.objects.filter(
        user=request.user, provider="5sim"
    ).order_by("-created_at")

    context = {
        "account":          account,
        "countries":        FOREIGN_COUNTRIES,
        "services":         FOREIGN_SERVICES,
        "country_display":  FOREIGN_COUNTRY_DISPLAY,
        "service_display":  FOREIGN_SERVICE_DISPLAY,
        "numbers":          numbers,
        "prices":           prices,
        "selected_country": selected_country,
        "selected_service": selected_service,
    }
    return render(request, "admin/subadmin/buy_foreign_number.html", context)


@sub_admin_approved_required
def sub_admin_foreign_number_prices(request):
    country = request.GET.get("country", "").strip().lower()
    service = request.GET.get("service", "").strip().lower()
    if not country or not service:
        return JsonResponse({"prices": [], "error": "country and service required"})
    prices = _fetch_5sim_prices(
        country=country if country in FOREIGN_COUNTRIES else None,
        service=service if service  in FOREIGN_SERVICES  else None,
    )
    return JsonResponse({"prices": prices})


@sub_admin_approved_required
def sub_admin_cancel_foreign_number(request, order_id):
    try:
        foreign_number = ForeignNumber.objects.get(order_id=order_id, user=request.user)
    except ForeignNumber.DoesNotExist:
        messages.error(request, "Number not found.")
        return redirect("sub-admin-buy-foreign-number")

    if foreign_number.status == ForeignNumber.Status.CANCELLED:
        messages.error(request, "This number has already been cancelled.")
        return redirect("sub-admin-buy-foreign-number")

    try:
        response = requests.get(
            f"https://5sim.net/v1/user/cancel/{order_id}",
            headers=_fivesim_headers(),
            timeout=30,
        )
        if response.status_code != 200:
            messages.error(request, "Unable to cancel number. It may already be expired or cancelled.")
            return redirect("sub-admin-buy-foreign-number")

        refund_amount = abs(Decimal(str(foreign_number.price)))

        with db_transaction.atomic():
            fn = ForeignNumber.objects.select_for_update().get(pk=foreign_number.pk)
            if fn.status == ForeignNumber.Status.CANCELLED:
                messages.error(request, "This number was already cancelled.")
                return redirect("sub-admin-buy-foreign-number")

            account = Account.objects.select_for_update().get(user=request.user)
            owner_account = get_owner_account()

            fn.status = ForeignNumber.Status.CANCELLED
            fn.save()

            account.balance += refund_amount
            account.save()

            if owner_account and owner_account.pk != account.pk:
                owner_acc = Account.objects.select_for_update().get(pk=owner_account.pk)
                owner_acc.balance -= refund_amount
                owner_acc.save()

        messages.success(request, f"Number cancelled successfully. ₦{refund_amount:,.0f} refunded to your wallet.")

    except Exception as e:
        logger.exception("5SIM cancel error")
        messages.error(request, f"Cancellation failed: {str(e)}")

    return redirect("sub-admin-buy-foreign-number")


@sub_admin_approved_required
def sub_admin_check_sms_5sim(request, order_id):
    """Poll 5SIM for an incoming SMS code and save it to the ForeignNumber record."""
    try:
        foreign_number = ForeignNumber.objects.get(
            order_id=order_id, user=request.user, provider="5sim"
        )
    except ForeignNumber.DoesNotExist:
        return JsonResponse({"error": "Number not found."}, status=404)

    if foreign_number.sms_code:
        return JsonResponse({"status": "received", "sms_code": foreign_number.sms_code})

    try:
        response = requests.get(
            f"https://5sim.net/v1/user/check/{order_id}",
            headers=_fivesim_headers(),
            timeout=15,
        )
        data = response.json()
    except Exception as e:
        logger.error(f"5SIM check SMS error: {e}")
        return JsonResponse({"error": "Could not reach 5SIM."}, status=502)

    sms_list = data.get("sms", [])
    if sms_list:
        code = sms_list[-1].get("code") or sms_list[-1].get("text", "")
        foreign_number.sms_code = code
        foreign_number.status = ForeignNumber.Status.RECEIVED
        foreign_number.save()
        return JsonResponse({"status": "received", "sms_code": code})

    api_status = data.get("status", "PENDING").upper()
    return JsonResponse({"status": api_status, "sms_code": None})


# ════════════════════════════════════════════════════════
#  WALLET DEPOSIT (Paystack)
# ════════════════════════════════════════════════════════

@sub_admin_approved_required
def sub_admin_wallet_deposit(request):
    account = get_or_create_account(request.user)
    history = account.deposits.order_by("-created_at")[:10]
    context = {"account": account, "history": history}
    return render(request, "admin/subadmin/wallet_deposit.html", context)


@sub_admin_approved_required
@require_POST
def sub_admin_wallet_deposit_pay(request):
    """Initiate Paystack payment to fund the NGN wallet."""
    account = get_or_create_account(request.user)

    try:
        amount = Decimal(str(request.POST.get("amount", "0")))
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, TypeError):
        messages.error(request, "Enter a valid amount.")
        return redirect("sub-admin-wallet-deposit")

    amount_kobo = int(amount * 100)
    reference   = f"WAL-{request.user.pk}-{uuid.uuid4().hex[:10].upper()}"

    deposit = WalletDeposit.objects.create(
        account            = account,
        amount             = amount,
        currency           = "NGN",
        paystack_reference = reference,
        status             = WalletDeposit.Status.PENDING,
    )

    callback_url = request.build_absolute_uri(
        reverse("sub-admin-wallet-deposit-verify", args=[reference])
    )

    try:
        payload = {
            "email":        request.user.email,
            "amount":       amount_kobo,
            "reference":    reference,
            "callback_url": callback_url,
            "metadata": {
                "user_id": str(request.user.pk),
                "type":    "wallet_deposit",
            },
        }
        resp = requests.post(
            "https://api.paystack.co/transaction/initialize",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                "Content-Type":  "application/json",
            },
            timeout=15,
        )
        data = resp.json()
        if not data.get("status"):
            raise Exception(data.get("message", "Paystack error"))

        deposit.paystack_access_code = data["data"]["access_code"]
        deposit.save()
        return redirect(data["data"]["authorization_url"])

    except Exception as e:
        deposit.status = WalletDeposit.Status.FAILED
        deposit.save()
        messages.error(request, f"Could not initiate payment: {e}")
        return redirect("sub-admin-wallet-deposit")


def sub_admin_wallet_deposit_verify(request, reference):
    """Paystack redirects here after payment. Verify and credit the wallet."""
    deposit = get_object_or_404(WalletDeposit, paystack_reference=reference)

    if deposit.status == WalletDeposit.Status.SUCCESS:
        messages.info(request, "This payment was already processed.")
        return redirect("sub-admin-wallet-deposit")

    try:
        resp = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
            timeout=15,
        )
        data = resp.json()
        if data.get("status") and data["data"]["status"] == "success":
            _credit_wallet(deposit)
            messages.success(request, f"Payment confirmed! ₦{deposit.amount:,} added to your wallet.")
        else:
            deposit.status = WalletDeposit.Status.FAILED
            deposit.save()
            messages.error(request, "Payment was not successful. Please try again.")
    except Exception as e:
        messages.error(request, f"Verification error: {e}")

    return redirect("sub-admin-wallet-deposit")


def _credit_wallet(deposit):
    """Mark deposit successful and add NGN to the wallet — atomic + locked."""
    with db_transaction.atomic():
        deposit = WalletDeposit.objects.select_for_update().get(pk=deposit.pk)
        if deposit.status == WalletDeposit.Status.SUCCESS:
            return False
        account = Account.objects.select_for_update().get(pk=deposit.account_id)
        account.balance += deposit.amount
        account.save(update_fields=["balance"])
        deposit.status  = WalletDeposit.Status.SUCCESS
        deposit.paid_at = timezone.now()
        deposit.save(update_fields=["status", "paid_at"])
    return True


@csrf_exempt
def sub_admin_paystack_webhook(request):
    """Paystack webhook — handles charge.success for points AND wallet deposits."""
    if request.method != "POST":
        return HttpResponse(status=405)

    secret    = settings.PAYSTACK_SECRET_KEY.encode("utf-8")
    signature = request.headers.get("x-paystack-signature", "")
    computed  = hmac.new(secret, request.body, hashlib.sha512).hexdigest()

    if not hmac.compare_digest(computed, signature):
        return HttpResponse(status=400)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    if payload.get("event") == "charge.success":
        reference = payload["data"].get("reference", "")

        if reference.startswith("PTS-"):
            try:
                purchase = PointsPurchase.objects.get(paystack_reference=reference)
                if purchase.status != PointsPurchase.Status.SUCCESS:
                    _credit_points(purchase)
            except PointsPurchase.DoesNotExist:
                pass

        elif reference.startswith("WAL-"):
            try:
                deposit = WalletDeposit.objects.get(paystack_reference=reference)
                if deposit.status != WalletDeposit.Status.SUCCESS:
                    _credit_wallet(deposit)
            except WalletDeposit.DoesNotExist:
                pass

    return HttpResponse(status=200)


# ════════════════════════════════════════════════════════
#  NOTIFICATIONS
# ════════════════════════════════════════════════════════

@super_admin_required
def admin_notification_list(request):
    """List every notification ever sent, most recent first."""
    notifications = Notification.objects.select_related(
        "sender", "recipient"
    ).order_by("-created_at")

    target = request.GET.get("target", "")  # "" | "private" | "public"
    if target == "private":
        notifications = notifications.filter(recipient__isnull=False)
    elif target == "public":
        notifications = notifications.filter(is_public=True, recipient__isnull=True)

    paginator = Paginator(notifications, 25)
    page_obj  = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "target":   target,
        "sub_admins": SubAdminProfile.objects.select_related("user").filter(
            approval_status=SubAdminProfile.ApprovalStatus.APPROVED
        ).order_by("user__full_name"),
        "type_choices": Notification.Type.choices,
    }
    return render(request, "admin/notifications/list.html", context)


@super_admin_required
@require_POST
def admin_notification_create(request):
    """
    Send a notification either to:
      - one specific sub-admin  (target=single, recipient_id=<pk>)
      - all sub-admins at once  (target=broadcast)
    """
    p     = request.POST
    target = p.get("target", "single")
    title  = p.get("title", "").strip()
    body   = p.get("body", "").strip()
    ntype  = p.get("type", Notification.Type.INFO)
    link   = p.get("link", "").strip()
    link_label = p.get("link_label", "").strip() or "View"

    if not title or not body:
        messages.error(request, "Title and message are required.")
        return redirect("admin-notification-list")

    if ntype not in Notification.Type.values:
        ntype = Notification.Type.INFO

    if target == "broadcast":
        Notification.objects.create(
            sender=request.user,
            recipient=None,
            is_public=True,
            type=ntype,
            title=title,
            body=body,
            link=link,
            link_label=link_label,
        )
        messages.success(request, "Notification broadcast to all sub-admins.")

    else:
        recipient_id = p.get("recipient_id")
        if not recipient_id:
            messages.error(request, "Please select a sub-admin to notify.")
            return redirect("admin-notification-list")
        recipient = get_object_or_404(User, pk=recipient_id, role=User.Role.SUB_ADMIN)
        Notification.objects.create(
            sender=request.user,
            recipient=recipient,
            is_public=False,
            type=ntype,
            title=title,
            body=body,
            link=link,
            link_label=link_label,
        )
        messages.success(request, f"Notification sent to {recipient.full_name}.")

    return redirect("admin-notification-list")


@super_admin_required
@require_POST
def admin_notification_delete(request, pk):
    notification = get_object_or_404(Notification, pk=pk)
    notification.delete()
    messages.success(request, "Notification deleted.")
    return redirect("admin-notification-list")


def _visible_notifications_qs(user):
    """Private notifications addressed to this user + all public broadcasts."""
    return Notification.objects.filter(
        Q(recipient=user) | Q(is_public=True, recipient__isnull=True)
    ).order_by("-created_at")


@sub_admin_approved_required
def sub_admin_notifications(request):
    """Full notification inbox page for the logged-in sub-admin."""
    notifications = _visible_notifications_qs(request.user).select_related("sender")
    read_public_ids = set(
        NotificationRead.objects.filter(user=request.user).values_list("notification_id", flat=True)
    )

    items = []
    for n in notifications:
        is_read = n.is_read if n.recipient_id == request.user.pk else (n.id in read_public_ids)
        items.append({"notification": n, "is_read": is_read})

    paginator = Paginator(items, 20)
    page_obj  = paginator.get_page(request.GET.get("page"))

    return render(request, "admin/subadmin/notifications.html", {"page_obj": page_obj})


@sub_admin_approved_required
@require_POST
def sub_admin_notification_mark_read(request, pk):
    notification = get_object_or_404(_visible_notifications_qs(request.user), pk=pk)
    if notification.recipient_id == request.user.pk:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    elif notification.is_public:
        NotificationRead.objects.get_or_create(notification=notification, user=request.user)
    return JsonResponse({"status": "ok"})


@sub_admin_approved_required
@require_POST
def sub_admin_notification_mark_all_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)

    public_unread = Notification.objects.filter(
        is_public=True, recipient__isnull=True
    ).exclude(reads__user=request.user)
    NotificationRead.objects.bulk_create(
        [NotificationRead(notification=n, user=request.user) for n in public_unread],
        ignore_conflicts=True,
    )

    messages.success(request, "All notifications marked as read.")
    return redirect("sub-admin-notifications")


@sub_admin_approved_required
def sub_admin_notifications_poll(request):
    """
    JSON endpoint polled every ~30s from the sub-admin dashboard.
    Returns still-unread notifications so JS can pop a toast for each
    one, then immediately mark it read (see notifications_toast.html).
    """
    unread_private = Notification.objects.filter(recipient=request.user, is_read=False)

    read_public_ids = NotificationRead.objects.filter(
        user=request.user
    ).values_list("notification_id", flat=True)
    unread_public = Notification.objects.filter(
        is_public=True, recipient__isnull=True
    ).exclude(id__in=read_public_ids)

    unread = sorted(
        list(unread_private) + list(unread_public),
        key=lambda n: n.created_at,
        reverse=True,
    )

    data = [
        {
            "id":         str(n.id),
            "type":       n.type,
            "title":      n.title,
            "body":       n.body,
            "link":       n.link,
            "link_label": n.link_label,
            "created_at": n.created_at.strftime("%d %b %Y, %H:%M"),
        }
        for n in unread[:10]
    ]

    return JsonResponse({"unread_count": len(unread), "notifications": data})


@sub_admin_approved_required
def sub_admin_notifications_feed(request):
    """JSON list of recent notifications for the bell dropdown popup."""
    notifications = _visible_notifications_qs(request.user).select_related("sender")[:15]

    read_public_ids = set(
        NotificationRead.objects.filter(user=request.user).values_list("notification_id", flat=True)
    )

    data = []
    for n in notifications:
        is_read = n.is_read if n.recipient_id == request.user.pk else (n.id in read_public_ids)
        data.append({
            "id":         str(n.id),
            "type":       n.type,
            "title":      n.title,
            "body":       n.body,
            "link":       n.link,
            "link_label": n.link_label,
            "is_read":    is_read,
            "created_at": n.created_at.strftime("%d %b, %H:%M"),
        })

    return JsonResponse({"notifications": data})


# ════════════════════════════════════════════════════════
#  LANDING-PAGE CUSTOMIZATION
# ════════════════════════════════════════════════════════

SITE_SETTINGS_TEXT_FIELDS = [
    "site_name", "site_tagline", "favicon_url", "primary_color",
    "hero_title", "hero_subtitle", "hero_image_url", "about_text",
    "stat_deliveries", "stat_satisfaction", "stat_support",
    "phone_primary", "phone_secondary", "email_support", "email_info",
    "address", "google_maps_url", "whatsapp_number",
    "twitter_url", "instagram_url", "facebook_url", "linkedin_url", "tiktok_url",
    "copyright_text", "meta_description", "meta_keywords",
    "logo_url",  # fallback if they don't upload a file
]

SITE_SETTINGS_DEFAULT_FIELDS = [
    "site_name", "site_tagline", "logo_url", "favicon_url", "primary_color",
    "hero_title", "hero_subtitle", "hero_image_url", "about_text",
    "stat_deliveries", "stat_satisfaction", "stat_support",
    "phone_primary", "phone_secondary", "email_support", "email_info",
    "address", "google_maps_url", "whatsapp_number",
    "twitter_url", "instagram_url", "facebook_url", "linkedin_url", "tiktok_url",
    "copyright_text", "meta_description", "meta_keywords",
]


@sub_admin_approved_required
def sub_admin_site_settings(request):
    """
    Edit page for the sub-admin's own landing-page branding.
    Saving costs points_per_site_customization points every time.
    Resetting (deleting their override row) is free and reverts
    them to the admin's global default.
    """
    profile = request.user.sub_admin_profile
    pricing = PointsPricing.get_current()
    cost    = pricing.points_per_site_customization

    own_settings   = SubAdminSiteSettings.objects.filter(sub_admin=profile).first()
    merged_preview = SubAdminSiteSettings.for_user(request.user)
    is_customized  = own_settings is not None

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "save":
            if profile.points_balance < cost:
                messages.error(
                    request,
                    f"You need {cost} point(s) to customize your landing page. "
                    f"You have {profile.points_balance}. Please top up."
                )
                return redirect("sub-admin-buy-points")

            obj, _ = SubAdminSiteSettings.objects.get_or_create(sub_admin=profile)

            for field in SITE_SETTINGS_TEXT_FIELDS:
                setattr(obj, field, request.POST.get(field, "").strip())

            logo_file = request.FILES.get("logo")
            if logo_file:
                obj.logo = logo_file

            obj.save()


            # ── Save any new gallery images uploaded alongside branding ──
            gallery_files = request.FILES.getlist("gallery_images")
            if gallery_files:
                existing_count = profile.gallery_images.count()
                for i, f in enumerate(gallery_files):
                    SubAdminGalleryImage.objects.create(
                        sub_admin=profile, image=f, sort_order=existing_count + i
                    )

            profile.deduct_points(cost)

            messages.success(
                request,
                f"Landing page updated. {cost} point(s) deducted. "
                f"Balance: {profile.points_balance} pts."
            )
        
            profile.deduct_points(cost)

            messages.success(
                request,
                f"Landing page updated. {cost} point(s) deducted. "
                f"Balance: {profile.points_balance} pts."
            )
            return redirect("sub-admin-site-settings")

        elif action == "reset":
            # Free — removes their overrides, falls back to the
            # admin-created default name/branding.
            deleted, _ = SubAdminSiteSettings.objects.filter(sub_admin=profile).delete()
            if deleted:
                messages.success(request, "Landing page reset to the default site branding.")
            else:
                messages.info(request, "You haven't customized your landing page yet.")
            return redirect("sub-admin-site-settings")

    context = {
        "profile":       profile,
        "pricing":       pricing,
        "cost":          cost,
        "own_settings":  own_settings,
        "merged":        merged_preview,
        "is_customized": is_customized,
        "gallery":       profile.gallery_images.all(),
    }
    return render(request, "admin/subadmin/site_settings.html", context)


@super_admin_required
def admin_default_site_settings(request):
    default = SubAdminSiteSettings.get_default()

    if request.method == "POST":
        for field in SITE_SETTINGS_TEXT_FIELDS:
            setattr(default, field, request.POST.get(field, "").strip())

        logo_file = request.FILES.get("logo")
        if logo_file:
            default.logo = logo_file

        default.save()
        messages.success(request, "Default site settings updated.")
        return redirect("admin-default-site-settings")

    return render(request, "admin/default_site_settings.html", {"settings": default})


def _default_settings_context():
    """Global-default-only settings, for the plain /site/ page."""
    default = SubAdminSiteSettings.get_default()
    ctx = {field: (getattr(default, field, "") or "") for field in SITE_SETTINGS_DEFAULT_FIELDS}
    ctx["logo"] = default.get_logo()
    return ctx


def public_subadmin_landing(request, referral_code):
    """
    Public landing page for one sub-admin, reached via their referral
    code. Uses SubAdminSiteSettings.for_user() — any field they've
    customized wins, anything they haven't falls back to the admin's
    global default automatically.
    """
    profile = get_object_or_404(SubAdminProfile, referral_code=referral_code.upper())
    request.session["active_referral_code"] = profile.referral_code 
    settings_ctx = SubAdminSiteSettings.for_user(profile.user)
    return render(request, "public/landing.html", {
        "settings":     settings_ctx,
        "profile":      profile,
        "testimonials": Testimonial.objects.filter(is_active=True).order_by("sort_order"),
        "gallery_images": BrandGalleryImage.objects.filter(is_active=True).order_by("sort_order"),
    })


def public_default_landing(request):
    """Plain landing page using only the admin's global default branding."""
    return render(request, "public/landing.html", {
        "settings":     _default_settings_context(),
        "profile":      None,
        "testimonials": Testimonial.objects.filter(is_active=True).order_by("sort_order"),
        "gallery_images": BrandGalleryImage.objects.filter(is_active=True).order_by("sort_order"),
    })


def _shared_landing_context():
    return {
        "testimonials": Testimonial.objects.filter(is_active=True).order_by("sort_order"),
        "gallery_images": BrandGalleryImage.objects.filter(is_active=True).order_by("sort_order"),
    }


# ════════════════════════════════════════════════════════
#  PUBLIC TRACKING PAGES
# ════════════════════════════════════════════════════════

def tracking_driver(request, tracking_id):
    shipment = get_object_or_404(Shipment, tracking_id=tracking_id)
    driver = None
    if shipment.driver_name:
        driver = {
            "name": shipment.driver_name,
            "phone": shipment.driver_phone,
            "photo_url": shipment.driver_photo.url if shipment.driver_photo else "",
            "vehicle_info": shipment.driver_vehicle_info,
            "rating": shipment.driver_rating,
            "chat_url": shipment.driver_chat_url,
        }
    return render(request, "public/tracking_driver.html", {"shipment": shipment, "driver": driver})


def tracking_shipment_info(request, tracking_id):
    shipment = get_object_or_404(
        Shipment.objects.select_related("sender", "receiver").prefetch_related("checkpoints", "images"),
        tracking_id=tracking_id,
    )
    checkpoints = shipment.checkpoints.order_by("timestamp")
    map_points = json.dumps([
        {"lat": float(cp.latitude), "lng": float(cp.longitude), "location": cp.location,
         "event": cp.get_event_type_display(), "time": cp.timestamp.strftime("%d %b %Y, %H:%M")}
        for cp in checkpoints if cp.latitude and cp.longitude
    ])
    return render(request, "public/tracking_shipment_info.html", {
        "shipment": shipment,
        "map_points": map_points,
        "progress_status": get_progress_status(shipment, shipment.checkpoints),
    })




# Business/sub_admin_views.py

def subadmin_domain_required(view_func):
    """Redirect to correct subdomain if accessing from wrong domain."""
    def wrapper(request, *args, **kwargs):
        subdomain = getattr(request, 'subdomain', 'main')
        if subdomain != 'admin' and not settings.DEBUG:
            return redirect(f'https://admin.transedge.site{request.path}')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper



@sub_admin_approved_required
@require_POST
def sub_admin_gallery_upload(request):
    """Add one or more images to the sub-admin's own gallery."""
    profile = request.user.sub_admin_profile
    files = request.FILES.getlist("gallery_images")

    if not files:
        messages.error(request, "Please choose at least one image.")
        return redirect("sub-admin-site-settings")

    existing_count = profile.gallery_images.count()
    for i, f in enumerate(files):
        SubAdminGalleryImage.objects.create(
            sub_admin=profile,
            image=f,
            sort_order=existing_count + i,
        )

    messages.success(request, f"{len(files)} image(s) added to your gallery.")
    return redirect("sub-admin-site-settings")


@sub_admin_approved_required
@require_POST
def sub_admin_gallery_delete(request, pk):
    """Remove one image from the sub-admin's own gallery."""
    image = get_object_or_404(
        SubAdminGalleryImage, pk=pk, sub_admin=request.user.sub_admin_profile
    )
    image.delete()
    messages.success(request, "Image removed.")
    return redirect("sub-admin-site-settings")