# yourapp/utils.py
from .models import SiteSettings

def default_settings_context():
    site = SiteSettings.objects.first()
    return {
        "site_name": site.company_name,
        "site_tagline": site.tagline,
        "logo": site.logo_url if hasattr(site, "logo_url") else None,
        "hero_title": getattr(site, "hero_title", ""),
        "hero_subtitle": site.hero_subtitle,
        "hero_image_url": site.hero_image_url,
        "about_text": getattr(site, "about_text", ""),
        "stat_deliveries": site.stat_deliveries,
        "stat_satisfaction": site.stat_satisfaction,
        "stat_support": site.stat_support,
        "phone_primary": site.phone_primary,
        "phone_secondary": site.phone_secondary,
        "email_support": site.email_support,
        "email_info": site.email_info,
        "address": site.address,
        "google_maps_url": site.google_maps_url,
        "whatsapp_number": site.whatsapp_number,
        "twitter_url": site.twitter_url,
        "instagram_url": site.instagram_url,
        "facebook_url": site.facebook_url,
        "linkedin_url": site.linkedin_url,
        "copyright_text": site.copyright_text,
        "meta_description": getattr(site, "meta_description", ""),
        "meta_keywords": getattr(site, "meta_keywords", ""),
    }