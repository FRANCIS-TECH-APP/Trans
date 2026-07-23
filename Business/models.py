# ══════════════════════════════════════════════════════════════════
#  REPLACE your entire models.py with this file
# ══════════════════════════════════════════════════════════════════

import uuid
import random
import string
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.conf import settings
from decimal import Decimal

def generate_tracking_id():
    year = timezone.now().year
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(random.choices(chars, k=8))
    return f"TRK-{year}-{suffix}"


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "admin")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN     = "admin",     "Admin"
        STAFF     = "staff",     "Staff"
        SUB_ADMIN = "sub_admin", "Sub Admin"

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email       = models.EmailField(unique=True)
    full_name   = models.CharField(max_length=255)
    phone       = models.CharField(max_length=20, blank=True)
    role        = models.CharField(max_length=10, choices=Role.choices, default=Role.STAFF)
    is_active   = models.BooleanField(default=True)
    is_staff    = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='business_user_set',
        blank=True,
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='business_user_set',
        blank=True,
    )

    objects = UserManager()

    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.role})"


class ContactInfo(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name   = models.CharField(max_length=255)
    email       = models.EmailField()
    phone       = models.CharField(max_length=20)
    address     = models.TextField()
    city        = models.CharField(max_length=100, blank=True)
    state       = models.CharField(max_length=100, blank=True)
    country     = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    company     = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

class Shipment(models.Model):
    class Status(models.TextChoices):
        CREATED          = "created",         "Created"
        PICKED_UP        = "picked_up",        "Picked Up"
        IN_TRANSIT       = "in_transit",       "In Transit"
        AT_CUSTOMS       = "at_customs",       "At Customs"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for Delivery"
        DELIVERED        = "delivered",        "Delivered"
        HELD             = "held",             "On Hold"
        RETURNED         = "returned",         "Returned"
        CANCELLED        = "cancelled",        "Cancelled"

    class ShipmentType(models.TextChoices):
        STANDARD  = "standard",  "Standard"
        EXPRESS   = "express",   "Express"
        OVERNIGHT = "overnight", "Overnight"
        FREIGHT   = "freight",   "Freight"
        DOCUMENT  = "document",  "Document Only"

    class SupportLinkType(models.TextChoices):
        LINK  = "link",  "Chat Link / URL"
        EMAIL = "email", "Email Address"

    id                   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tracking_id          = models.CharField(
        max_length=20, unique=True,
        default=generate_tracking_id, editable=False,
    )
    created_by           = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True,
        related_name="created_shipments",
    )
    sender               = models.OneToOneField(
        ContactInfo, on_delete=models.PROTECT, related_name="as_sender"
    )
    receiver             = models.OneToOneField(
        ContactInfo, on_delete=models.PROTECT, related_name="as_receiver"
    )
    shipment_type        = models.CharField(max_length=15, choices=ShipmentType.choices, default=ShipmentType.STANDARD)
    description          = models.TextField()
    weight_kg            = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dimensions           = models.CharField(max_length=100, blank=True)
    quantity             = models.PositiveIntegerField(default=1)
    declared_value       = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency             = models.CharField(max_length=5, default="NGN")
    status               = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    origin_country       = models.CharField(max_length=100)
    destination_country  = models.CharField(max_length=100)
    estimated_delivery   = models.DateField(null=True, blank=True)
    actual_delivery      = models.DateField(null=True, blank=True)
    internal_notes       = models.TextField(blank=True)
    special_instructions = models.TextField(blank=True)
    # Points cost snapshot — how many points were spent to create this shipment
    points_spent         = models.PositiveIntegerField(default=0)
    amendment_count = models.PositiveIntegerField(default=0) 
    created_at           = models.DateTimeField(auto_now_add=True)
    updated_at           = models.DateTimeField(auto_now=True)
    support_link_type   = models.CharField(
        max_length=10, choices=SupportLinkType.choices, default=SupportLinkType.LINK
    )
    # Stores either a URL or an email address depending on support_link_type
    support_link_url    = models.CharField(max_length=255, blank=True)
    support_link_label  = models.CharField(max_length=100, blank=True, default="Chat with Support")
    support_link_active = models.BooleanField(default=False)

    # ... existing fields ...
    driver_name        = models.CharField(max_length=100, blank=True, default="")
    driver_phone        = models.CharField(max_length=30, blank=True, default="")
    driver_photo         = models.ImageField(upload_to="drivers/", null=True, blank=True)
    driver_vehicle_info  = models.CharField(max_length=100, blank=True, default="")
    driver_rating        = models.DecimalField(max_digits=2, decimal_places=1, null=True, blank=True)
    driver_chat_url      = models.URLField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.tracking_id} — {self.sender} → {self.receiver}"

class ShipmentImage(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shipment    = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="images")
    image       = models.ImageField(upload_to="shipments/stock/")
    caption     = models.CharField(max_length=255, blank=True)
    is_primary  = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "uploaded_at"]

    def __str__(self):
        return f"Image for {self.shipment.tracking_id}"


class TransitCheckpoint(models.Model):
    class EventType(models.TextChoices):
        PICKUP           = "pickup",          "Package Picked Up"
        DEPARTED         = "departed",        "Departed Facility"
        ARRIVED          = "arrived",         "Arrived at Facility"
        IN_TRANSIT       = "in_transit",      "In Transit"
        CUSTOMS_IN       = "customs_in",      "Entered Customs"
        CUSTOMS_CLEARED  = "customs_cleared", "Customs Cleared"
        OUT_FOR_DELIVERY = "out_delivery",    "Out for Delivery"
        DELIVERED        = "delivered",       "Delivered"
        ATTEMPTED        = "attempted",       "Delivery Attempted"
        HELD             = "held",            "Package on Hold"
        EXCEPTION        = "exception",       "Exception / Alert"

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shipment    = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="checkpoints")
    event_type  = models.CharField(max_length=20, choices=EventType.choices)
    location    = models.CharField(max_length=255)
    city        = models.CharField(max_length=100, blank=True)
    country     = models.CharField(max_length=100, blank=True)
    latitude    = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude   = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    description = models.TextField(blank=True)
    timestamp   = models.DateTimeField()
    added_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.shipment.tracking_id} — {self.get_event_type_display()} @ {self.location}"


class Payment(models.Model):
    class Status(models.TextChoices):
        UNPAID   = "unpaid",   "Unpaid"
        PENDING  = "pending",  "Pending"
        PAID     = "paid",     "Paid"
        PARTIAL  = "partial",  "Partially Paid"
        OVERDUE  = "overdue",  "Overdue"
        WAIVED   = "waived",   "Waived"
        REFUNDED = "refunded", "Refunded"

    class Method(models.TextChoices):
        CARD          = "card",          "Card"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        MOBILE_MONEY  = "mobile_money",  "Mobile Money"
        CRYPTO        = "crypto",        "Cryptocurrency"
        CASH          = "cash",          "Cash"
        PAYSTACK      = "paystack",      "Paystack"
        FLUTTERWAVE   = "flutterwave",   "Flutterwave"

    id                = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shipment          = models.OneToOneField(Shipment, on_delete=models.CASCADE, related_name="payment")
    amount            = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    amount_paid       = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency          = models.CharField(max_length=5, default="NGN")
    method            = models.CharField(max_length=15, choices=Method.choices, blank=True)
    status            = models.CharField(max_length=10, choices=Status.choices, default=Status.UNPAID)
    reason            = models.CharField(max_length=255, blank=True)
    payment_reference = models.CharField(max_length=200, blank=True)
    due_date          = models.DateField(null=True, blank=True)
    paid_at           = models.DateTimeField(null=True, blank=True)
    notes             = models.TextField(blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    @property
    def balance_due(self):
        return self.amount - self.amount_paid

    def __str__(self):
        return f"Payment for {self.shipment.tracking_id} — {self.status} ({self.currency} {self.amount})"


# ══════════════════════════════════════════════════════════════════
#  SUB-ADMIN SYSTEM — POINTS BASED, NO EXPIRY
# ══════════════════════════════════════════════════════════════════

class SubAdminProfile(models.Model):
    class ApprovalStatus(models.TextChoices):
        PENDING   = "pending",   "Pending Approval"
        APPROVED  = "approved",  "Approved"
        REJECTED  = "rejected",  "Rejected"
        SUSPENDED = "suspended", "Suspended"

    user            = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sub_admin_profile",
    )
    approval_status = models.CharField(
        max_length=10,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
    )
    approved_by     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="approved_sub_admins",
    )
    approved_at        = models.DateTimeField(null=True, blank=True)
    rejection_reason   = models.TextField(blank=True)

    # Points wallet — never expires
    points_balance     = models.PositiveIntegerField(default=0)

    # Business info
    company_name       = models.CharField(max_length=255, blank=True)
    phone              = models.CharField(max_length=20, blank=True)
    address            = models.TextField(blank=True)

    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    # ADD THESE:
    avatar          = models.ImageField(upload_to="avatars/", null=True, blank=True)
    whatsapp_number = models.CharField(max_length=20, blank=True)
    referral_code   = models.CharField(max_length=12, unique=True, blank=True, default="")
    referred_by     = models.ForeignKey(
        "self", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="referrals",
    )
    last_activity   = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.referral_code:
            import secrets
            code = secrets.token_hex(4).upper()
            while SubAdminProfile.objects.filter(referral_code=code).exists():
                code = secrets.token_hex(4).upper()
            self.referral_code = code
        super().save(*args, **kwargs)

    @property
    def referral_count(self):
        return self.referrals.count()

    @property
    def shipment_count(self):
        return self.user.created_shipments.count()

    @property
    def transaction_count(self):
        return self.point_purchases.count()

    def get_referral_link(self, request):
        from django.urls import reverse
        path = reverse("sub-admin-register")
        return request.build_absolute_uri(f"{path}?ref={self.referral_code}")
    

    def __str__(self):
        return f"SubAdmin: {self.user.full_name} [{self.approval_status}] — {self.points_balance} pts"

    def can_create_shipment(self):
        cost = PointsPricing.get_current().points_per_shipment
        return self.points_balance >= cost

    def deduct_points(self, amount):
        """Deduct points and return the new balance. Raises ValueError if insufficient."""
        if self.points_balance < amount:
            raise ValueError("Insufficient points")
        self.points_balance -= amount
        self.save(update_fields=["points_balance"])
        return self.points_balance

class PointsPricing(models.Model):
    points_per_shipment      = models.PositiveIntegerField(default=1)
    points_per_amendment     = models.PositiveIntegerField(default=1)
    points_per_invoice       = models.PositiveIntegerField(default=1)   # ← ADD THIS
    price_per_point          = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("100"))
    points_per_support_link  = models.PositiveIntegerField(default=1)
    points_per_site_customization = models.PositiveIntegerField(default=1)
    invoice_fee = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0"),
        help_text="Flat fee added to every invoice created from a shipment."
    )
    currency    = models.CharField(max_length=5, default="NGN")
    updated_by  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Points Pricing"

    def __str__(self):
        return (
            f"{self.points_per_shipment} pts/shipment | "
            f"{self.points_per_amendment} pts/amendment | "
            f"{self.points_per_invoice} pts/invoice | "
            f"{self.points_per_support_link} pts/support-link | "
            f"{self.points_per_site_customization} pts/landing-page | "
            f"{self.currency} {self.price_per_point}/pt"
        )

    @classmethod
    def get_current(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
    


    
class PointsPurchase(models.Model):
    """Records every points top-up payment by a sub-admin."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED  = "failed",  "Failed"

    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sub_admin           = models.ForeignKey(
        SubAdminProfile,
        on_delete=models.CASCADE,
        related_name="point_purchases",
    )
    points_bought       = models.PositiveIntegerField()
    amount_paid         = models.DecimalField(max_digits=14, decimal_places=2)
    currency            = models.CharField(max_length=5, default="NGN")
    paystack_reference  = models.CharField(max_length=200, unique=True)
    paystack_access_code= models.CharField(max_length=200, blank=True)
    status              = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    paid_at             = models.DateTimeField(null=True, blank=True)
    created_at          = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.sub_admin.user.full_name} — "
            f"{self.points_bought} pts — {self.status}"
        )


        

# ══════════════════════════════════════════════════════════════════
#  ADD THESE MODELS TO YOUR EXISTING models.py
#  These power the admin-controlled site content
# ══════════════════════════════════════════════════════════════════

class SiteSettings(models.Model):
    """
    Singleton — controls all public-facing site content.
    Admin edits this from the panel. One row only.
    """
    # Company
    company_name    = models.CharField(max_length=100, default="TransEdge Global")
    tagline         = models.CharField(max_length=255, default="Precision Logistics, Global Reach")
    hero_subtitle   = models.TextField(default="Navigating complexity with precision. End-to-end supply chain solutions.")

    # Contact
    phone_primary   = models.CharField(max_length=30, blank=True)
    phone_secondary = models.CharField(max_length=30, blank=True)
    email_support   = models.EmailField(blank=True)
    email_info      = models.EmailField(blank=True)
    address         = models.TextField(blank=True)
    google_maps_url = models.URLField(blank=True)

    # Social
    twitter_url     = models.URLField(blank=True)
    instagram_url   = models.URLField(blank=True)
    linkedin_url    = models.URLField(blank=True)
    facebook_url    = models.URLField(blank=True)
    whatsapp_number = models.CharField(max_length=20, blank=True,
                                       help_text="Include country code e.g. 2348012345678")

    # Hero image
    hero_image_url  = models.URLField(blank=True,
                                      help_text="URL of the hero background image")

    # Stats shown on homepage
    stat_deliveries = models.CharField(max_length=20, default="15k+")
    stat_satisfaction = models.CharField(max_length=20, default="98%")
    stat_support    = models.CharField(max_length=20, default="24/7")

    # Footer copyright
    copyright_text  = models.CharField(max_length=255, default="© 2024 TransEdge Global. All rights reserved.")

    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Settings"

    def __str__(self):
        return f"Site Settings — {self.company_name}"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Testimonial(models.Model):
    name        = models.CharField(max_length=100)
    role        = models.CharField(max_length=150, help_text="e.g. COO, GlobalTech Solutions")
    avatar      = models.ImageField(upload_to="testimonials/", null=True, blank=True)
    avatar_url  = models.URLField(blank=True, help_text="Use URL if no file upload")
    content     = models.TextField()
    rating      = models.PositiveSmallIntegerField(default=5,
                  help_text="1–5 stars")
    is_active   = models.BooleanField(default=True)
    sort_order  = models.PositiveIntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "-created_at"]

    def __str__(self):
        return f"{self.name} — {self.role}"

    def get_avatar(self):
        if self.avatar:
            return self.avatar.url
        return self.avatar_url or ""


class ClientEarning(models.Model):
    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shipment         = models.OneToOneField(
        'Shipment', on_delete=models.CASCADE, related_name="earning"
    )
    declared_profit  = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    commission_rate  = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    commission_amount= models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net_profit       = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency         = models.CharField(max_length=5, default="NGN")
    payout_status    = models.CharField(max_length=20, choices=[
        ("pending",    "Pending"),
        ("processing", "Processing"),
        ("paid",       "Paid Out"),
        ("on_hold",    "On Hold"),
    ], default="pending")
    payout_date      = models.DateField(null=True, blank=True)
    notes            = models.TextField(blank=True)
    updated_at       = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Earning for {self.shipment.tracking_id}"


class EmailLog(models.Model):
    class EmailType(models.TextChoices):
        TRACKING_CREATED  = "tracking_created",  "Tracking ID Created"
        STATUS_UPDATE     = "status_update",      "Status Update"
        DELIVERY_ALERT    = "delivery_alert",     "Delivery Alert"
        PAYMENT_REMINDER  = "payment_reminder",   "Payment Reminder"
        PAYMENT_CONFIRMED = "payment_confirmed",  "Payment Confirmed"
        CUSTOM            = "custom",             "Custom Message"

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shipment   = models.ForeignKey(
        'Shipment', on_delete=models.SET_NULL, null=True, related_name="emails"
    )
    email_type = models.CharField(max_length=25, choices=EmailType.choices)
    recipient  = models.EmailField()
    subject    = models.CharField(max_length=255)
    body       = models.TextField()
    sent_at    = models.DateTimeField(auto_now_add=True)
    sent_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    is_success = models.BooleanField(default=True)
    error_msg  = models.TextField(blank=True)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"[{self.email_type}] → {self.recipient}"



def generate_invoice_number():
    year = timezone.now().year
    suffix = ''.join(random.choices(string.digits, k=6))
    return f"INV-{year}-{suffix}"


CURRENCY_CHOICES = [
    ("USD", "US Dollar ($)"),
    ("NGN", "Nigerian Naira (₦)"),
    ("EUR", "Euro (€)"),
    ("GBP", "British Pound (£)"),
    ("CAD", "Canadian Dollar (C$)"),
    ("GHS", "Ghanaian Cedi (₵)"),
]

CURRENCY_SYMBOLS = {
    "USD": "$",
    "NGN": "₦",
    "EUR": "€",
    "GBP": "£",
    "CAD": "C$",
    "GHS": "₵",
}


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT     = "draft",     "Draft"
        SENT      = "sent",      "Sent"
        PAID      = "paid",      "Paid"
        OVERDUE   = "overdue",   "Overdue"
        CANCELLED = "cancelled", "Cancelled"

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shipment       = models.OneToOneField(
        Shipment, on_delete=models.CASCADE, related_name="invoice"
    )
    invoice_number = models.CharField(
        max_length=20, unique=True, default=generate_invoice_number, editable=False
    )
    created_by     = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="created_invoices",
    )

    bill_to_name    = models.CharField(max_length=255, blank=True)
    bill_to_email   = models.EmailField(blank=True)
    bill_to_address = models.TextField(blank=True)

    issue_date = models.DateField(default=timezone.now)
    due_date   = models.DateField(null=True, blank=True)
    currency   = models.CharField(max_length=5, choices=CURRENCY_CHOICES, default="USD")

    tax_rate         = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    discount_amount  = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    subtotal      = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"), editable=False)
    tax_amount    = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"), editable=False)
    total_amount  = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"), editable=False)
    amount_paid   = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    status  = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    notes   = models.TextField(blank=True)
    terms   = models.TextField(blank=True, default="Payment due within 7 days of invoice date.")

    paid_at    = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.invoice_number} — {self.shipment.tracking_id}"

    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid

    @property
    def currency_symbol(self):
        return CURRENCY_SYMBOLS.get(self.currency, self.currency)

    def recalculate_totals(self):
        subtotal = sum((item.amount for item in self.items.all()), start=Decimal("0"))

        tax_rate = self.tax_rate if isinstance(self.tax_rate, Decimal) else Decimal(str(self.tax_rate))
        discount_amount = (
            self.discount_amount if isinstance(self.discount_amount, Decimal)
            else Decimal(str(self.discount_amount))
        )

        tax = subtotal * (tax_rate / Decimal("100"))

        self.subtotal     = subtotal
        self.tax_amount    = tax
        self.total_amount  = subtotal + tax - discount_amount
        self.save(update_fields=["subtotal", "tax_amount", "total_amount", "updated_at"])

    def mark_paid(self):
        self.status      = self.Status.PAID
        self.amount_paid = self.total_amount
        self.paid_at     = timezone.now()
        self.save(update_fields=["status", "amount_paid", "paid_at", "updated_at"])

class InvoiceItem(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice     = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255)
    quantity    = models.PositiveIntegerField(default=1)
    unit_price  = models.DecimalField(max_digits=14, decimal_places=2)
    amount      = models.DecimalField(max_digits=14, decimal_places=2, editable=False)

    def save(self, *args, **kwargs):
        self.amount = (self.quantity or 0) * (self.unit_price or 0)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description} — {self.amount}"
    


# ══════════════════════════════════════════════════════════════════
#  ADD TO Business/models.py — NGN wallet + 5Sim foreign numbers
# ══════════════════════════════════════════════════════════════════

class Account(models.Model):
    """NGN cash wallet — separate from SubAdminProfile.points_balance."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="account",
    )
    account_number = models.CharField(max_length=10, unique=True, blank=True)
    balance = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal("0.00")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def generate_account_number(self):
        while True:
            number = str(random.randint(1000000000, 9999999999))
            if not Account.objects.filter(account_number=number).exists():
                return number

    def save(self, *args, **kwargs):
        if not self.account_number:
            self.account_number = self.generate_account_number()
        super().save(*args, **kwargs)

    def __str__(self):
        identifier = getattr(self.user, "email", None) or str(self.user.pk)
        return f"{identifier} — ₦{self.balance}"


class ForeignNumber(models.Model):
    class Status(models.TextChoices):
        PENDING   = "PENDING",   "Pending"
        RECEIVED  = "RECEIVED",  "Received"
        CANCELLED = "CANCELLED", "Cancelled"
        FINISHED  = "FINISHED",  "Finished"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="foreign_numbers",
    )
    order_id     = models.CharField(max_length=100, unique=True)
    country      = models.CharField(max_length=100)
    service      = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=100)
    price        = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sms_code     = models.CharField(max_length=50, blank=True, null=True)
    status       = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    provider     = models.CharField(max_length=20, default="5sim")
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.phone_number} — {self.get_status_display()}"
    


# ══════════════════════════════════════════════════════════════════
#  ADD TO Business/models.py — wallet funding
# ══════════════════════════════════════════════════════════════════

class WalletDeposit(models.Model):
    """Records every NGN wallet top-up payment via Paystack."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED  = "failed",  "Failed"

    id                    = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account               = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="deposits"
    )
    amount                = models.DecimalField(max_digits=14, decimal_places=2)
    currency              = models.CharField(max_length=5, default="NGN")
    paystack_reference    = models.CharField(max_length=200, unique=True)
    paystack_access_code  = models.CharField(max_length=200, blank=True)
    status                = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    paid_at    = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        identifier = getattr(self.account.user, "email", None) or str(self.account.user.pk)
        return f"{identifier} — ₦{self.amount} — {self.status}"







# ══════════════════════════════════════════════════════════════════
#  ADD THESE MODELS TO YOUR EXISTING models.py
#  1. Notification — admin sends to specific user or all users
#  2. SubAdminSiteSettings — each sub-admin controls their own
#     landing page (name, logo, contact, social, about, etc.)
# ══════════════════════════════════════════════════════════════════



# ──────────────────────────────────────────────────────────────────
#  NOTIFICATIONS
#  Admin creates a notification targeted at:
#    - A specific sub-admin user (recipient != None)
#    - All sub-admins at once (recipient = None, is_public = True)
# ──────────────────────────────────────────────────────────────────

class Notification(models.Model):
    class Type(models.TextChoices):
        INFO    = "info",    "Info"
        SUCCESS = "success", "Success"
        WARNING = "warning", "Warning"
        ALERT   = "alert",   "Alert"

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Who sent it — always an admin/staff user
    sender     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sent_notifications",
    )

    # Who receives it:
    #   recipient = specific User  →  private notification
    #   recipient = None + is_public = True  →  broadcast to ALL sub-admins
    recipient  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
        help_text="Leave blank to send to all sub-admins (public broadcast).",
    )
    is_public  = models.BooleanField(
        default=False,
        help_text="If True and recipient is blank, all sub-admins see this.",
    )

    # Content
    type       = models.CharField(max_length=10, choices=Type.choices, default=Type.INFO)
    title      = models.CharField(max_length=255)
    body       = models.TextField()
    link       = models.URLField(
        blank=True,
        help_text="Optional action link shown as a button (e.g. /sub-admin/buy-points/).",
    )
    link_label = models.CharField(max_length=80, blank=True, default="View")

    # State — tracked per-user via NotificationRead for public ones
    is_read    = models.BooleanField(
        default=False,
        help_text="For private notifications only. Public ones use NotificationRead.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        target = self.recipient.full_name if self.recipient else "ALL USERS"
        return f"[{self.type.upper()}] {self.title} → {target}"


class NotificationRead(models.Model):
    """
    Tracks which sub-admins have read a PUBLIC notification.
    Private notifications use Notification.is_read directly.
    """
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="reads",
    )
    user         = models.ForeignKey(
        settings.AUTH_USER_MODEL,                 
        on_delete=models.CASCADE,
        related_name="notification_reads",
    )
    read_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("notification", "user")

    def __str__(self):
        return f"{self.user.full_name} read {self.notification.title}"


# ──────────────────────────────────────────────────────────────────
#  SUB-ADMIN SITE SETTINGS
#  One row per sub-admin.  Admin can set a "global default" row
#  (sub_admin = None).  When a sub-admin has not customised a field
#  the frontend falls back to the global default.
#
#  Helper: SubAdminSiteSettings.for_user(user)  →  merged settings
# ──────────────────────────────────────────────────────────────────

class SubAdminSiteSettings(models.Model):
    """
    Landing-page branding that each sub-admin controls independently.
    sub_admin = None  →  the global default set by the super-admin.
    sub_admin = <profile>  →  that sub-admin's personal overrides.
    """

    sub_admin = models.OneToOneField(
        "SubAdminProfile",          # ← the existing model in your file
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="site_settings",
        help_text="Null = global default (set by super-admin).",
    )

    # ── Branding ──────────────────────────────────────────────────
    site_name        = models.CharField(max_length=100, blank=True, default="")
    site_tagline     = models.CharField(max_length=255, blank=True, default="")
    logo             = models.ImageField(
        upload_to="site_logos/",
        null=True, blank=True,
        help_text="Upload a logo image.",
    )
    logo_url         = models.URLField(
        blank=True,
        help_text="Use a URL if you don't want to upload a file.",
    )
    favicon_url      = models.URLField(blank=True)
    primary_color    = models.CharField(
        max_length=20, blank=True,
        help_text="Hex color e.g. #38bdf8",
    )

    # ── Hero / About ──────────────────────────────────────────────
    hero_title       = models.CharField(max_length=255, blank=True, default="")
    hero_subtitle    = models.TextField(blank=True, default="")
    hero_image_url   = models.URLField(blank=True)
    about_text       = models.TextField(
        blank=True,
        help_text="About section shown on the public landing page.",
    )

    # ── Stats (homepage counters) ─────────────────────────────────
    stat_deliveries   = models.CharField(max_length=20, blank=True, default="")
    stat_satisfaction = models.CharField(max_length=20, blank=True, default="")
    stat_support      = models.CharField(max_length=20, blank=True, default="")

    # ── Contact ───────────────────────────────────────────────────
    phone_primary    = models.CharField(max_length=30, blank=True, default="")
    phone_secondary  = models.CharField(max_length=30, blank=True, default="")
    email_support    = models.EmailField(blank=True, default="")
    email_info       = models.EmailField(blank=True, default="")
    address          = models.TextField(blank=True, default="")
    google_maps_url  = models.URLField(blank=True)

    # ── Social media ──────────────────────────────────────────────
    whatsapp_number  = models.CharField(
        max_length=20, blank=True,
        help_text="Include country code, no + e.g. 2348012345678",
    )
    twitter_url      = models.URLField(blank=True)
    instagram_url    = models.URLField(blank=True)
    facebook_url     = models.URLField(blank=True)
    linkedin_url     = models.URLField(blank=True)
    tiktok_url       = models.URLField(blank=True)

    # ── Footer ────────────────────────────────────────────────────
    copyright_text   = models.CharField(max_length=255, blank=True, default="")

    # ── SEO ───────────────────────────────────────────────────────
    meta_description = models.TextField(blank=True)
    meta_keywords    = models.CharField(max_length=500, blank=True)

    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sub-Admin Site Settings"

    def __str__(self):
        if self.sub_admin:
            return f"Site Settings — {self.sub_admin.user.full_name}"
        return "Site Settings — GLOBAL DEFAULT"

    def get_logo(self):
        """Return logo URL — file upload takes priority over URL field."""
        if self.logo:
            return self.logo.url
        return self.logo_url or ""

    # ── Class-level helpers ───────────────────────────────────────

    @classmethod
    def get_default(cls):
        """
        Return the global default row (sub_admin=None).
        Creates it with empty values if it doesn't exist yet.
        """
        obj, _ = cls.objects.get_or_create(sub_admin=None)
        return obj

    @classmethod
    def for_user(cls, user):
        """
        Return a merged settings object for a sub-admin user.

        Strategy:
          - Start with the global default.
          - Override field-by-field with the sub-admin's own settings
            wherever the sub-admin has set a non-empty value.
          - Returns a plain dict (not a model instance) so it's easy
            to pass straight into a template context.

        Usage in a view:
            settings = SubAdminSiteSettings.for_user(request.user)
            # settings["site_name"], settings["phone_primary"], …
        """
        default = cls.get_default()

        try:
            profile   = user.sub_admin_profile
            overrides = cls.objects.get(sub_admin=profile)
        except (cls.DoesNotExist, Exception):
            overrides = None

        TEXT_FIELDS = [
            "site_name", "site_tagline", "logo_url", "favicon_url",
            "primary_color", "hero_title", "hero_subtitle", "hero_image_url",
            "about_text", "stat_deliveries", "stat_satisfaction", "stat_support",
            "phone_primary", "phone_secondary", "email_support", "email_info",
            "address", "google_maps_url", "whatsapp_number",
            "twitter_url", "instagram_url", "facebook_url",
            "linkedin_url", "tiktok_url", "copyright_text",
            "meta_description", "meta_keywords",
        ]

        merged = {}
        for field in TEXT_FIELDS:
            default_val  = getattr(default,   field, "") or ""
            override_val = getattr(overrides, field, "") or "" if overrides else ""
            # Non-empty override wins; otherwise fall back to default
            merged[field] = override_val if override_val.strip() else default_val

        # Logo: file upload beats URL field
        if overrides and overrides.logo:
            merged["logo"] = overrides.logo.url
        elif default.logo:
            merged["logo"] = default.logo.url
        else:
            merged["logo"] = merged.get("logo_url", "")

        return merged

    @classmethod
    def get_or_create_for_user(cls, user):
        """
        Returns the SubAdminSiteSettings instance for a sub-admin,
        creating it if it doesn't exist.
        """
        profile = user.sub_admin_profile
        obj, _  = cls.objects.get_or_create(sub_admin=profile)
        return obj



# ══════════════════════════════════════════════════════════════════
#  ADD TO Business/models.py — REPLACES your draft BuyLogs /
#  BuyLogDetails / Purchase classes below with this version.
#
#  Wired to the SAME `Account` NGN wallet your ForeignNumber
#  purchases already use — no separate points system.
# ══════════════════════════════════════════════════════════════════

from django.utils.text import slugify

class Category(models.Model):
    name       = models.CharField(max_length=50, unique=True)
    slug       = models.SlugField(max_length=60, unique=True, blank=True)
    icon       = models.CharField(max_length=60, blank=True, help_text="Font Awesome class, e.g. 'fab fa-facebook'")
    is_active  = models.BooleanField(default=True)
    order      = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

class BuyLogs(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category    = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    title       = models.CharField(max_length=200)
    image       = models.ImageField(upload_to="categories/")
    description = models.TextField()
    price       = models.DecimalField(max_digits=10, decimal_places=2)
    active      = models.BooleanField(default=True)
    credential_format = models.CharField(
        max_length=255, blank=True, default="Email,Password",
        help_text=(
            "Comma-separated field labels, in the order they'll appear "
            "when bulk-pasting stock. E.g. 'Email,Password' or "
            "'Username,PIN,Recovery Code'."
        ),
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "title"]
        verbose_name = "Log Product"
        verbose_name_plural = "Log Products"

    def __str__(self):
        return self.title

    @property
    def stock_count(self):
        return self.details.filter(sold=False).count()

    @property
    def in_stock(self):
        return self.stock_count > 0

    def format_labels(self):
        """Returns the credential_format string as a clean list of labels."""
        return [l.strip() for l in self.credential_format.split(",") if l.strip()] or ["Email", "Password"]

    
class BuyLogDetails(models.Model):
    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        BuyLogs, on_delete=models.CASCADE, related_name="details"
    )

    sold       = models.BooleanField(default=False)
    added_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="buy_logs_added",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sold_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Log Stock Item"
        verbose_name_plural = "Log Stock Items"

    def __str__(self):
        first_field = self.credential_fields.first()
        preview = first_field.value if first_field else str(self.pk)[:8]
        return f"{preview} — {'SOLD' if self.sold else 'AVAILABLE'}"

class BuyLogDetailField(models.Model):
    """
    One labeled credential value belonging to a stock item.
    """
    id     = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    detail = models.ForeignKey(
        BuyLogDetails, on_delete=models.CASCADE, related_name="credential_fields"
    )
    label        = models.CharField(max_length=100, help_text="e.g. Email, Password, API Key, PIN")
    value        = models.CharField(max_length=500)
    is_sensitive = models.BooleanField(
        default=True,
        help_text="If true, shown as a copy-to-clipboard credential on the receipt.",
    )
    sort_order   = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]
        verbose_name = "Credential Field"

    def __str__(self):
        return f"{self.label}: {self.value[:20]}"


class Purchase(models.Model):
    """
    A completed sub-admin purchase of one log. Deducts from the same
    `Account` wallet used for ForeignNumber (5sim) purchases.
    """
    id        = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer     = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="log_purchases",
    )
    product   = models.ForeignKey(
        BuyLogs, on_delete=models.CASCADE, related_name="purchases"
    )
    log       = models.OneToOneField(
        BuyLogDetails, on_delete=models.CASCADE, related_name="purchase"
    )
    account   = models.ForeignKey(
        Account, on_delete=models.SET_NULL, null=True,
        related_name="log_purchases",
        help_text="Wallet the purchase was debited from.",
    )
    amount        = models.DecimalField(max_digits=10, decimal_places=2)
    purchased_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-purchased_at"]

    def __str__(self):
        return f"{self.buyer} - {self.product.title}"
    



class DashboardAdvert(models.Model):
    title = models.CharField(max_length=100)
    subtitle = models.CharField(max_length=200, blank=True)
    image = models.ImageField(upload_to='dashboard_adverts/', blank=True, null=True)
    cta_text = models.CharField(max_length=40, default="Learn More")
    cta_url = models.URLField(blank=True)
    background_start = models.CharField(max_length=20, default="#3B82F6", help_text="Gradient start hex color")
    background_end = models.CharField(max_length=20, default="#1E3A8A", help_text="Gradient end hex color")
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-created_at']

    def __str__(self):
        return self.title

    def is_currently_active(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        return True


class DashboardAnnouncement(models.Model):
    title = models.CharField(max_length=120)
    message = models.TextField()
    link_url = models.URLField(blank=True, null=True)
    link_text = models.CharField(max_length=60, default="Join Group")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title



class BrandGalleryImage(models.Model):
    """
    Admin-managed, platform-wide images shown on every sub-admin's public
    landing page. Sub-admins have no CRUD access to this model at all —
    it isn't exposed anywhere in the sub-admin views/templates, so there's
    nothing for them to remove or override.
    """
    image = models.ImageField(upload_to="brand_gallery/")
    caption = models.CharField(max_length=120, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return self.caption or f"Gallery image #{self.pk}"



class SubAdminGalleryImage(models.Model):
    """
    A sub-admin's own gallery images on their public landing page —
    separate from the admin-managed BrandGalleryImage. Sub-admins can
    add and remove their own; they never touch the admin's fixed set.
    """
    sub_admin  = models.ForeignKey(
        SubAdminProfile, on_delete=models.CASCADE, related_name="gallery_images"
    )
    image      = models.ImageField(upload_to="subadmin_gallery/")
    caption    = models.CharField(max_length=120, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.caption or f"Gallery image #{self.pk}"