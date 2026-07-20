from django.contrib import admin
from django.utils.safestring import mark_safe
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    Shipment, ContactInfo, ShipmentImage,
    TransitCheckpoint, Payment, 
    User, SubAdminProfile, PointsPricing, PointsPurchase,NotificationRead, Notification, SubAdminSiteSettings,
    Account, ForeignNumber, SiteSettings, Testimonial, Invoice, InvoiceItem,DashboardAnnouncement,BrandGalleryImage
)


class CheckpointInline(admin.StackedInline):
    model   = TransitCheckpoint
    extra   = 1
    fields  = [
        "event_type", "location", "city", "country",
        "latitude", "longitude", "map_picker",
        "timestamp", "description",
    ]
    readonly_fields = ["map_picker"]

    def map_picker(self, obj):
        lat  = obj.latitude  if (obj and obj.latitude)  else 20.0
        lng  = obj.longitude if (obj and obj.longitude) else 0.0
        zoom = 13 if (obj and obj.latitude) else 2
        uid  = obj.pk if (obj and obj.pk) else "new"

        return mark_safe(f"""
            <link rel="stylesheet"
                  href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
                  integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
                  crossorigin=""/>
            <div style="margin-bottom:8px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                <input type="text" id="map-search-{uid}"
                       placeholder="Search city / address…"
                       style="padding:6px 10px;width:260px;border:1px solid #ccc;
                              border-radius:4px;font-size:13px;"/>
                <button type="button" onclick="mpSearch_{uid}()"
                        style="padding:6px 14px;background:#1a1a2e;color:#fff;
                               border:none;border-radius:4px;cursor:pointer;font-size:13px;">
                    Search
                </button>
                <span id="map-msg-{uid}" style="font-size:12px;color:#888;"></span>
            </div>
            <div id="map-{uid}"
                 style="width:100%;height:380px;border:1px solid #ccc;
                        border-radius:6px;margin-bottom:6px;">
            </div>
            <small style="color:#888;">Click the map <strong>or</strong> drag the marker to set coordinates.</small>
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
                    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV/XN/WLEo="
                    crossorigin=""></script>
            <script>
            (function() {{
                function getInputs(uid) {{
                    const mapEl = document.getElementById('map-' + uid);
                    const fieldset = mapEl.closest('.inline-related') ||
                                     mapEl.closest('fieldset') || document;
                    return {{
                        lat: fieldset.querySelector('input[name$="latitude"]'),
                        lng: fieldset.querySelector('input[name$="longitude"]'),
                    }};
                }}
                function initMap_{uid}() {{
                    if (document.getElementById('map-{uid}')._leaflet_id) return;
                    const map = L.map('map-{uid}').setView([{lat}, {lng}], {zoom});
                    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                        maxZoom: 19, attribution: '© OpenStreetMap contributors'
                    }}).addTo(map);
                    const marker = L.marker([{lat}, {lng}], {{draggable: true}}).addTo(map);
                    function applyCoords(lat, lng) {{
                        const inp = getInputs('{uid}');
                        if (inp.lat) inp.lat.value = lat.toFixed(6);
                        if (inp.lng) inp.lng.value = lng.toFixed(6);
                        document.getElementById('map-msg-{uid}').textContent =
                            lat.toFixed(6) + ', ' + lng.toFixed(6);
                    }}
                    map.on('click', function(e) {{
                        marker.setLatLng(e.latlng);
                        applyCoords(e.latlng.lat, e.latlng.lng);
                    }});
                    marker.on('dragend', function() {{
                        const ll = marker.getLatLng();
                        applyCoords(ll.lat, ll.lng);
                    }});
                    const inp = getInputs('{uid}');
                    [inp.lat, inp.lng].forEach(function(input) {{
                        if (!input) return;
                        input.addEventListener('change', function() {{
                            const la = parseFloat(inp.lat ? inp.lat.value : {lat});
                            const ln = parseFloat(inp.lng ? inp.lng.value : {lng});
                            if (!isNaN(la) && !isNaN(ln)) {{
                                marker.setLatLng([la, ln]);
                                map.setView([la, ln], 13);
                            }}
                        }});
                    }});
                    window['_map_{uid}']         = map;
                    window['_marker_{uid}']      = marker;
                    window['_applyCoords_{uid}'] = applyCoords;
                }}
                window['mpSearch_{uid}'] = function() {{
                    const q = document.getElementById('map-search-{uid}').value.trim();
                    if (!q) return;
                    const msg = document.getElementById('map-msg-{uid}');
                    msg.textContent = 'Searching…';
                    fetch('https://nominatim.openstreetmap.org/search?q=' +
                          encodeURIComponent(q) + '&format=json&limit=1')
                    .then(function(r) {{ return r.json(); }})
                    .then(function(data) {{
                        if (data.length === 0) {{ msg.textContent = 'Not found.'; return; }}
                        const lat = parseFloat(data[0].lat);
                        const lng = parseFloat(data[0].lon);
                        window['_map_{uid}'].setView([lat, lng], 13);
                        window['_marker_{uid}'].setLatLng([lat, lng]);
                        window['_applyCoords_{uid}'](lat, lng);
                    }})
                    .catch(function() {{ msg.textContent = 'Network error.'; }});
                }};
                document.addEventListener('DOMContentLoaded', function() {{
                    const sb = document.getElementById('map-search-{uid}');
                    if (sb) {{
                        sb.addEventListener('keydown', function(e) {{
                            if (e.key === 'Enter') {{ e.preventDefault(); mpSearch_{uid}(); }}
                        }});
                    }}
                    initMap_{uid}();
                }});
                if (document.readyState !== 'loading') {{
                    setTimeout(initMap_{uid}, 100);
                }}
            }})();
            </script>
        """)
    map_picker.short_description = "Map / Coordinate Picker"


class ImageInline(admin.TabularInline):
    model  = ShipmentImage
    extra  = 1
    fields = ["image", "caption", "is_primary"]


class PaymentInline(admin.StackedInline):
    model  = Payment
    fields = [
        "amount", "currency", "method", "status",
        "reason", "amount_paid", "payment_reference",
        "due_date", "notes",
    ]



@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display    = [
        "tracking_id", "sender", "receiver",
        "status", "shipment_type", "points_spent", "created_at",
    ]
    list_filter     = ["status", "shipment_type", "origin_country"]
    search_fields   = [
        "tracking_id",
        "sender__full_name", "sender__email",
        "receiver__full_name", "receiver__email",
    ]
    readonly_fields = ["tracking_id", "points_spent", "created_at", "updated_at"]
    inlines         = [CheckpointInline, ImageInline, PaymentInline]


@admin.register(ContactInfo)
class ContactInfoAdmin(admin.ModelAdmin):
    list_display  = ["full_name", "email", "phone", "city", "country"]
    search_fields = ["full_name", "email"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = ["shipment", "amount", "amount_paid", "status", "method"]
    list_filter   = ["status", "method"]


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    list_display  = ["email", "full_name", "role", "is_active", "date_joined"]
    search_fields = ["email", "full_name"]
    ordering      = ["email"]
    list_filter   = ["role", "is_active"]
    fieldsets = (
        (None,          {"fields": ("email", "password")}),
        ("Personal",    {"fields": ("full_name", "phone")}),
        ("Permissions", {"fields": ("role", "is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields":  ("email", "full_name", "password1", "password2", "role"),
        }),
    )


@admin.register(SubAdminProfile)
class SubAdminProfileAdmin(admin.ModelAdmin):
    list_display    = ["user", "approval_status", "points_balance", "created_at"]
    list_filter     = ["approval_status"]
    search_fields   = ["user__email", "user__full_name"]
    readonly_fields = ["created_at", "updated_at", "approved_by", "approved_at"]



@admin.register(PointsPurchase)
class PointsPurchaseAdmin(admin.ModelAdmin):
    list_display    = ["sub_admin", "points_bought", "amount_paid", "currency", "status", "paid_at"]
    list_filter     = ["status"]
    search_fields   = ["sub_admin__user__email", "paystack_reference"]
    readonly_fields = ["paystack_reference", "paystack_access_code", "created_at"]


from django.contrib import admin
from .models import SiteSettings, Testimonial

@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    # Prevent creating more than one row
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display  = ["name", "role", "rating", "is_active", "sort_order"]
    list_editable = ["is_active", "sort_order"]
    list_filter   = ["is_active"]

from .models import Invoice, InvoiceItem

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "shipment", "status", "total_amount", "created_at")
    list_filter  = ("status",)
    search_fields = ("invoice_number", "shipment__tracking_id")
    inlines = [InvoiceItemInline]


# ══════════════════════════════════════════════════════════════════
#  ADD TO Business/admin.py — Account & ForeignNumber
# ══════════════════════════════════════════════════════════════════

from django.contrib import admin
from .models import Account, ForeignNumber


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display  = ("account_number", "user_display", "balance", "created_at")
    search_fields = ("account_number", "user__email", "user__full_name")
    readonly_fields = ("account_number", "created_at", "updated_at")
    list_select_related = ("user",)
    ordering = ("-created_at",)

    def user_display(self, obj):
        return getattr(obj.user, "email", None) or getattr(obj.user, "full_name", None) or obj.user.pk
    user_display.short_description = "User"
    user_display.admin_order_field = "user__email"


@admin.register(ForeignNumber)
class ForeignNumberAdmin(admin.ModelAdmin):
    list_display  = (
        "phone_number", "user_display", "country", "service",
        "status", "price", "provider", "created_at",
    )
    list_filter   = ("status", "provider", "country", "service")
    search_fields = ("phone_number", "order_id", "user__email", "user__full_name")
    readonly_fields = ("order_id", "created_at")
    list_select_related = ("user",)
    ordering = ("-created_at",)

    def user_display(self, obj):
        return getattr(obj.user, "email", None) or getattr(obj.user, "full_name", None) or obj.user.pk
    user_display.short_description = "User"
    user_display.admin_order_field = "user__email"



# ══════════════════════════════════════════════════════════════════
#  ADD TO Business/admin.py
#
#  Covers:
#    1. PointsPricing  — super admin sets points_per_site_customization
#       (and every other points_per_* cost) from the Django admin,
#       as an alternative to the in-app manage_sub_admins pricing form.
#    2. Notification / NotificationRead — send + inspect notifications
#       straight from the admin, without needing the custom
#       admin_notification_create view.
#    3. SubAdminSiteSettings — inspect/edit any sub-admin's landing
#       page override, or the global default row, from one screen.
#
#  Add these imports to the top of your existing admin.py (merge with
#  whatever you already import from .models):
#    from .models import (
#        PointsPricing, Notification, NotificationRead,
#        SubAdminSiteSettings, SubAdminProfile, User,
#    )
# ══════════════════════════════════════════════════════════════════

from django.contrib import admin
from django.utils.html import format_html


# ════════════════════════════════════════════════════════
#  POINTS PRICING — singleton, one row only
# ════════════════════════════════════════════════════════

@admin.register(PointsPricing)
class PointsPricingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "points_per_shipment",
        "points_per_amendment",
        "points_per_invoice",
        "points_per_support_link",
        "points_per_site_customization",
        "price_per_point",
        "currency",
        "updated_by",
        "updated_at",
    )
    readonly_fields = ("updated_at",)
    fieldsets = (
        ("Shipment & amendment costs", {
            "fields": ("points_per_shipment", "points_per_amendment"),
        }),
        ("Invoice & support link costs", {
            "fields": ("points_per_invoice", "points_per_support_link", "invoice_fee"),
        }),
        ("Landing page customization cost", {
            "fields": ("points_per_site_customization",),
            "description": "How many points a sub-admin spends each time they save their landing-page branding.",
        }),
        ("Point pricing", {
            "fields": ("price_per_point", "currency"),
        }),
        ("Meta", {
            "fields": ("updated_by", "updated_at"),
        }),
    )

    def has_add_permission(self, request):
        # Singleton — PointsPricing.get_current() always uses pk=1.
        return not PointsPricing.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


# ════════════════════════════════════════════════════════
#  NOTIFICATIONS
# ════════════════════════════════════════════════════════

class NotificationReadInline(admin.TabularInline):
    model = NotificationRead
    extra = 0
    readonly_fields = ("user", "read_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "type_badge",
        "target_display",
        "sender",
        "read_status",
        "created_at",
    )
    list_filter = ("type", "is_public", "is_read", "created_at")
    search_fields = ("title", "body", "recipient__full_name", "recipient__email")
    autocomplete_fields = ("recipient", "sender")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"

    fieldsets = (
        ("Content", {
            "fields": ("type", "title", "body", "link", "link_label"),
        }),
        ("Target", {
            "fields": ("recipient", "is_public"),
            "description": (
                "Leave 'Recipient' blank and check 'Is public' to broadcast "
                "to every sub-admin. Set a specific recipient for a private "
                "notification instead."
            ),
        }),
        ("Meta", {
            "fields": ("sender", "is_read", "created_at"),
        }),
    )

    inlines = [NotificationReadInline]

    actions = ["mark_as_read", "mark_as_unread"]

    def save_model(self, request, obj, form, change):
        if not obj.sender_id:
            obj.sender = request.user
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("sender", "recipient")

    @admin.display(description="Type")
    def type_badge(self, obj):
        colors = {
            "info": "#0ea5e9", "success": "#16a34a",
            "warning": "#d97706", "alert": "#dc2626",
        }
        color = colors.get(obj.type, "#64748b")
        return format_html(
            '<span style="color:{}; font-weight:600;">{}</span>',
            color, obj.get_type_display(),
        )

    @admin.display(description="Target")
    def target_display(self, obj):
        if obj.recipient_id:
            return obj.recipient.full_name
        if obj.is_public:
            return "ALL SUB-ADMINS"
        return "—"

    @admin.display(description="Read", boolean=True)
    def read_status(self, obj):
        if obj.recipient_id:
            return obj.is_read
        if obj.is_public:
            return obj.reads.exists()
        return False

    @admin.action(description="Mark selected private notifications as read")
    def mark_as_read(self, request, queryset):
        updated = queryset.filter(recipient__isnull=False).update(is_read=True)
        self.message_user(request, f"{updated} notification(s) marked as read.")

    @admin.action(description="Mark selected private notifications as unread")
    def mark_as_unread(self, request, queryset):
        updated = queryset.filter(recipient__isnull=False).update(is_read=False)
        self.message_user(request, f"{updated} notification(s) marked as unread.")


@admin.register(NotificationRead)
class NotificationReadAdmin(admin.ModelAdmin):
    """Read-only log of who has seen which public broadcast."""
    list_display = ("notification", "user", "read_at")
    list_filter = ("read_at",)
    search_fields = ("notification__title", "user__full_name", "user__email")
    autocomplete_fields = ("notification", "user")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ════════════════════════════════════════════════════════
#  SUB-ADMIN SITE SETTINGS (landing page branding)
# ════════════════════════════════════════════════════════
from .models import SubAdminSiteSettings

@admin.register(SubAdminSiteSettings)
class SubAdminSiteSettingsAdmin(admin.ModelAdmin):
    list_display   = ["sub_admin", "site_name", "phone_primary", "email_support", "updated_at"]
    search_fields  = ["sub_admin__user__full_name", "site_name", "email_support"]
    readonly_fields = ["updated_at"]
    fieldsets = [
        ("Branding", {
            "fields": ["sub_admin", "site_name", "tagline", "hero_subtitle", "logo_image", "logo_url", "hero_image_url", "primary_color"]
        }),
        ("Contact", {
            "fields": ["phone_primary", "phone_secondary", "email_support", "email_info", "address", "whatsapp_number", "google_maps_url"]
        }),
        ("Social Media", {
            "fields": ["twitter_url", "instagram_url", "linkedin_url", "facebook_url"]
        }),
        ("Homepage Stats", {
            "fields": ["stat_deliveries", "stat_satisfaction", "stat_support"]
        }),
        ("Content", {
            "fields": ["about_text", "copyright_text", "updated_at"]
        }),
    ]



# ══════════════════════════════════════════════════════════════════
#  ADD TO Business/admin.py
#  Only ADMIN-role users can add/edit log stock (BuyLogDetails).
#  Sub-admins never reach this at all — they don't have is_staff,
#  so Django admin login already excludes them; this adds a second,
#  explicit check so a STAFF user can't stock logs either — only
#  users with role == User.Role.ADMIN can.
# ══════════════════════════════════════════════════════════════════

from django.contrib import admin
from django.utils.html import format_html
from .models import BuyLogs, BuyLogDetails, Purchase


def _is_admin_role(request):
    user = request.user
    return user.is_superuser or getattr(user, "role", None) == "admin"


class BuyLogDetailsInline(admin.TabularInline):
    model = BuyLogDetails
    extra = 0
    fields = ("email", "password", "recovery_email", "two_factor_code", "sold", "sold_at")
    readonly_fields = ("sold_at",)
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return _is_admin_role(request)

    def has_change_permission(self, request, obj=None):
        return _is_admin_role(request)

    def has_delete_permission(self, request, obj=None):
        return _is_admin_role(request)


@admin.register(BuyLogs)
class BuyLogsAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "price", "stock_badge", "active", "created_at")
    list_filter = ("category", "active")
    search_fields = ("title", "description")
    autocomplete_fields = ("category",) 
    inlines = [BuyLogDetailsInline]

    def stock_badge(self, obj):
        count = obj.stock_count
        color = "#22c55e" if count > 0 else "#ef4444"
        return format_html('<b style="color:{}">{} in stock</b>', color, count)
    stock_badge.short_description = "Stock"

    def has_add_permission(self, request):
        return _is_admin_role(request)

    def has_change_permission(self, request, obj=None):
        return _is_admin_role(request)

    def has_delete_permission(self, request, obj=None):
        return _is_admin_role(request)

from .models import BuyLogs, BuyLogDetails, Purchase, Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "order", "is_active", "product_count")
    list_editable = ("order", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)

    def has_add_permission(self, request):
        return _is_admin_role(request)

    def has_change_permission(self, request, obj=None):
        return _is_admin_role(request)

    def has_delete_permission(self, request, obj=None):
        return _is_admin_role(request)

    def product_count(self, obj):
        return obj.products.count()
    product_count.short_description = "Products"


@admin.register(BuyLogDetails)
class BuyLogDetailsAdmin(admin.ModelAdmin):
    """
    Standalone view of stock across all products — handy for bulk
    stocking. Same admin-only restriction as the inline above.
    """
    list_display = ("email", "product", "sold", "sold_at", "added_by", "created_at")
    list_filter = ("sold", "product__category", "product")
    search_fields = ("email", "product__title")
    readonly_fields = ("sold_at",)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.added_by = request.user
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        return _is_admin_role(request)

    def has_add_permission(self, request):
        return _is_admin_role(request)

    def has_change_permission(self, request, obj=None):
        return _is_admin_role(request)

    def has_delete_permission(self, request, obj=None):
        return _is_admin_role(request)


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    """
    Read-only purchase history. Admin can see who bought what and
    from which wallet, but can't edit or fabricate purchases here —
    purchases only happen through the sub-admin-facing view.
    """
    list_display = ("buyer", "product", "amount", "account", "purchased_at")
    list_filter = ("product__category",)
    search_fields = ("buyer__email", "buyer__full_name", "product__title")
    readonly_fields = ("buyer", "product", "log", "account", "amount", "purchased_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return _is_admin_role(request)
    


from django.contrib import admin
from django.utils.html import format_html
from .models import DashboardAdvert

@admin.register(DashboardAdvert)
class DashboardAdvertAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'order', 'start_date', 'end_date', 'preview')
    list_editable = ('is_active', 'order')
    ordering = ('order',)
    fields = (
        'title', 'subtitle', 'image', 'cta_text', 'cta_url',
        'background_start', 'background_end',
        'is_active', 'order', 'start_date', 'end_date',
    )

    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:40px;border-radius:6px;" />', obj.image.url)
        return "—"
    preview.short_description = "Preview"



@admin.register(DashboardAnnouncement)
class DashboardAnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "created_at")


# admin.py
@admin.register(BrandGalleryImage)
class BrandGalleryImageAdmin(admin.ModelAdmin):
    list_display = ("caption", "sort_order", "is_active")