from django.urls import path
from . import views
from . import sub_admin_views as sv

urlpatterns = [

    # ── PUBLIC ────────────────────────────────────────

   
    path("", sv.public_default_landing, name="transedge-home"),
    path("track/",                        views.tracking_search,  name="tracking-search"),
    path("track/<str:tracking_id>/",      views.tracking_detail,  name="tracking-detail"),

    # ── ADMIN AUTH ────────────────────────────────────
    path("admin-portal/login/",           views.admin_login,      name="admin-login"),
    path("admin-portal/logout/",          views.admin_logout,     name="admin-logout"),

    # ── ADMIN DASHBOARD ───────────────────────────────
    path("admin-portal/",                 views.admin_dashboard,  name="admin-dashboard"),
    path("admin-portal/reports/",         views.reports,          name="reports"),

    # ── SHIPMENTS ─────────────────────────────────────
    path("admin-portal/shipments/",
         views.shipment_list,   name="shipment-list"),
    path("admin-portal/shipments/create/",
         views.shipment_create, name="shipment-create"),
    path("admin-portal/shipments/<uuid:pk>/",
         views.shipment_detail, name="shipment-detail"),
    path("admin-portal/shipments/<uuid:pk>/edit/",
         views.shipment_edit,   name="shipment-edit"),
    path("admin-portal/shipments/<uuid:pk>/delete/",
         views.shipment_delete, name="shipment-delete"),

    # ── CHECKPOINTS ───────────────────────────────────
    path("admin-portal/shipments/<uuid:shipment_pk>/checkpoint/add/",
         views.checkpoint_add,    name="checkpoint-add"),
    path("admin-portal/checkpoint/<uuid:pk>/delete/",
         views.checkpoint_delete, name="checkpoint-delete"),

    # ── IMAGES ────────────────────────────────────────
    path("admin-portal/image/<uuid:pk>/delete/",
         views.image_delete,      name="image-delete"),
    path("admin-portal/image/<uuid:pk>/set-primary/",
         views.image_set_primary, name="image-set-primary"),

    # ── PAYMENTS ──────────────────────────────────────
    path("admin-portal/payments/",
         views.payment_list,          name="payment-list"),
    path("admin-portal/payments/<uuid:pk>/update/",
         views.payment_update,        name="payment-update"),
    path("admin-portal/payments/<uuid:pk>/remind/",
         views.payment_send_reminder, name="payment-remind"),

    # ── JSON API ──────────────────────────────────────
    path("api/track/<str:tracking_id>/",
         views.api_track,                name="api-track"),
    path("api/admin/shipments/<uuid:pk>/checkpoints/",
         views.api_shipment_checkpoints, name="api-shipment-checkpoints"),

    # ── SUB-ADMIN AUTH ────────────────────────────────
    path("sub-admin/register/",
         sv.sub_admin_register,  name="sub-admin-register"),
    path("sub-admin/login/",
         sv.sub_admin_login,     name="sub-admin-login"),
    path("sub-admin/logout/",
         sv.sub_admin_logout,    name="sub-admin-logout"),

    # ── SUB-ADMIN PORTAL ──────────────────────────────
    path("sub-admin/",
         sv.sub_admin_dashboard,       name="sub-admin-dashboard"),
    path("sub-admin/shipments/",
         sv.sub_admin_shipment_list,   name="sub-admin-shipment-list"),
    path("sub-admin/shipments/create/",
         sv.sub_admin_shipment_create, name="sub-admin-shipment-create"),
    path("sub-admin/shipments/<uuid:pk>/",
         sv.sub_admin_shipment_detail, name="sub-admin-shipment-detail"),

    # ── SUB-ADMIN POINTS ──────────────────────────────
    path("sub-admin/points/",
         sv.sub_admin_buy_points,      name="sub-admin-buy-points"),
    path("sub-admin/points/pay/",
         sv.sub_admin_points_pay,      name="sub-admin-points-pay"),
    path("sub-admin/points/verify/<str:reference>/",
         sv.sub_admin_points_verify,   name="sub-admin-points-verify"),
    path("sub-admin/paystack/webhook/",
         sv.sub_admin_paystack_webhook, name="sub-admin-paystack-webhook"),

    # ── SUPER ADMIN — SUB-ADMIN MANAGEMENT ───────────
    path("admin-portal/sub-admins/",
         sv.manage_sub_admins,  name="manage-sub-admins"),
    path("admin-portal/sub-admins/pricing/",
         sv.set_points_pricing, name="set-points-pricing"),
    path("admin-portal/sub-admins/<uuid:pk>/",
         sv.sub_admin_detail,   name="sub-admin-detail"),
    path("admin-portal/sub-admins/<uuid:pk>/approve/",
         sv.approve_sub_admin,  name="approve-sub-admin"),
    path("admin-portal/sub-admins/<uuid:pk>/reject/",
         sv.reject_sub_admin,   name="reject-sub-admin"),
    path("admin-portal/sub-admins/<uuid:pk>/suspend/",
         sv.suspend_sub_admin,  name="suspend-sub-admin"),
    path("admin-portal/sub-admins/<uuid:pk>/reinstate/",
         sv.reinstate_sub_admin, name="reinstate-sub-admin"),
    path("admin-portal/sub-admins/<uuid:pk>/adjust-points/",
         sv.admin_adjust_points, name="admin-adjust-points"),
     path("sub-admin/", sv.sub_admin_dashboard, name="sub-admin-dashboard"),
     path("sub-admin/landing/", sv.sub_admin_landing, name="sub-admin-landing"), 
     path("sub-admin/shipments/<uuid:pk>/checkpoint/add/",
     sv.sub_admin_checkpoint_add, name="sub-admin-checkpoint-add"),
     path("sub-admin/profile/", sv.sub_admin_profile, name="sub-admin-profile"),
     path("sub-admin/shipments/<uuid:pk>/addons/", sv.sub_admin_shipment_addons, name="sub-admin-shipment-addons"),
     path("sub-admin/shipments/<uuid:pk>/amend/", sv.sub_admin_shipment_amend_form, name="sub-admin-shipment-amend-form"),
     path("sub-admin/shipments/<uuid:pk>/amend/submit/", sv.sub_admin_shipment_amend, name="sub-admin-shipment-amend"),
  

# Site content management
    path("admin-portal/site-settings/",                     views.admin_site_settings,      name="admin-site-settings"),
    path("admin-portal/testimonials/",                      views.admin_testimonials,        name="admin-testimonials"),
    path("admin-portal/testimonials/<int:pk>/edit/",        views.admin_testimonial_edit,    name="admin-testimonial-edit"),
    path("admin-portal/testimonials/<int:pk>/delete/",      views.admin_testimonial_delete,  name="admin-testimonial-delete"),
    path('shipments/<uuid:pk>/invoice/create/', sv.sub_admin_invoice_create, name='sub-admin-invoice-create'),
    path('invoices/<uuid:pk>/', sv.sub_admin_invoice_detail, name='sub-admin-invoice-detail'),
    path('invoices/<uuid:pk>/update/', sv.sub_admin_invoice_update, name='sub-admin-invoice-update'),
    path('invoices/<uuid:pk>/items/add/', sv.sub_admin_invoice_add_item, name='sub-admin-invoice-add-item'),
    path('invoices/<uuid:pk>/items/<uuid:item_pk>/remove/', sv.sub_admin_invoice_remove_item, name='sub-admin-invoice-remove-item'),
    path('invoices/<uuid:pk>/mark-paid/', sv.sub_admin_invoice_mark_paid, name='sub-admin-invoice-mark-paid'),
    path("invoices/<uuid:pk>/pdf/", sv.sub_admin_invoice_pdf, name="sub-admin-invoice-pdf"),
    path("sub-admin/foreign-numbers/", sv.sub_admin_buy_foreign_number, name="sub-admin-buy-foreign-number"),
    path("sub-admin/foreign-numbers/prices/", sv.sub_admin_foreign_number_prices, name="sub-admin-foreign-number-prices"),
    path("sub-admin/foreign-numbers/<str:order_id>/cancel/", sv.sub_admin_cancel_foreign_number, name="sub-admin-cancel-foreign-number"),
    path("sub-admin/foreign-numbers/<str:order_id>/check-sms/", sv.sub_admin_check_sms_5sim, name="sub-admin-check-sms-5sim"),
    path("sub-admin/wallet/deposit/", sv.sub_admin_wallet_deposit, name="sub-admin-wallet-deposit"),
    path("sub-admin/wallet/deposit/pay/", sv.sub_admin_wallet_deposit_pay, name="sub-admin-wallet-deposit-pay"),
    path("sub-admin/wallet/deposit/verify/<str:reference>/", sv.sub_admin_wallet_deposit_verify, name="sub-admin-wallet-deposit-verify"),

    

    # ── Sub-admin notifications ────────────────────────────────────
    path("sub-admin/notifications/", sv.sub_admin_notifications, name="sub-admin-notifications"),
    path("sub-admin/notifications/<uuid:pk>/read/", sv.sub_admin_notification_mark_read, name="sub-admin-notification-mark-read"),
    path("sub-admin/notifications/mark-all-read/", sv.sub_admin_notification_mark_all_read, name="sub-admin-notification-mark-all-read"),
    path("sub-admin/notifications/poll/", sv.sub_admin_notifications_poll, name="sub-admin-notifications-poll"),

    # ── Super-admin notifications ──────────────────────────────────
    path("admin/notifications/", sv.admin_notification_list, name="admin-notification-list"),
    path("admin/notifications/create/", sv.admin_notification_create, name="admin-notification-create"),
    path("admin/notifications/<uuid:pk>/delete/", sv.admin_notification_delete, name="admin-notification-delete"),

    # ── Sub-admin landing page customization ───────────────────────
    path("sub-admin/site-settings/", sv.sub_admin_site_settings, name="sub-admin-site-settings"),

    # ── Super-admin global default landing page ─────────────────────
    path("admin/default-site-settings/", sv.admin_default_site_settings, name="admin-default-site-settings"),
    path("sub-admin/notifications/feed/", sv.sub_admin_notifications_feed, name="sub-admin-notifications-feed"),
    
    path("site/", sv.public_default_landing, name="public-default-landing"),
    path("site/<str:referral_code>/", sv.public_subadmin_landing, name="public-subadmin-landing"),
    path("admin/default-site-settings/", sv.admin_default_site_settings, name="admin-default-site-settings"),
    path("track/<str:tracking_id>/driver/", sv.tracking_driver, name="tracking-driver"),
    path("track/<str:tracking_id>/shipment/", sv.tracking_shipment_info, name="tracking-shipment-info"),
    path("buy-logs/", views.browse_logs, name="buy-logs-browse"),
    path("buy-logs/<uuid:pk>/", views.log_detail, name="buy-logs-detail"),
    path("buy-logs/<uuid:pk>/purchase/", views.purchase_log, name="buy-logs-purchase"),
    path("buy-logs/purchases/", views.my_purchases, name="buy-logs-my-purchases"),
    path("buy-logs/purchases/<uuid:pk>/", views.purchase_receipt, name="buy-logs-receipt"),
    path('adverts/', views.admin_advert_list, name='admin-advert-list'),
    path('adverts/new/', views.admin_advert_create, name='admin-advert-create'),
    path('adverts/<int:pk>/edit/', views.admin_advert_edit, name='admin-advert-edit'),
    path('adverts/<int:pk>/toggle/', views.admin_advert_toggle, name='admin-advert-toggle'),
    path('adverts/<int:pk>/delete/', views.admin_advert_delete, name='admin-advert-delete'),
    path('adverts/<int:pk>/edit/', views.admin_advert_edit, name='admin-advert-edit'),
    path('sub-admin/gallery/upload/', sv.sub_admin_gallery_upload, name='sub-admin-gallery-upload'),
    path('sub-admin/gallery/<int:pk>/delete/', sv.sub_admin_gallery_delete, name='sub-admin-gallery-delete'),
    path("sub-admin/insufficient-funds/",sv.sub_admin_insufficient_funds,name="sub-admin-insufficient-funds"),
    path("sub-admin/purchases/<uuid:pk>/detail/",sv.sub_admin_purchase_detail_json, name="sub-admin-purchase-detail-json"),
    path("buy-logs/<uuid:pk>/purchase/", sv.buy_logs_purchase, name="buy-logs-purchase"),
    path("buy-logs/success/<uuid:pk>/", sv.buy_logs_payment_success, name="buy-logs-payment-success"),
    path("shipping/sub-admin/tutorials/",sv.tutorial_list,   name="sub-admin-tutorials"),
    path("shipping/sub-admin/tutorials/<int:pk>/",sv.tutorial_detail, name="sub-admin-tutorial-detail"),

]

