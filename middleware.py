from django.shortcuts import redirect
from django.conf import settings


class SubdomainMiddleware:
    """
    Routes requests based on subdomain:
      transedge.site        → public shipping site
      admin.transedge.site  → sub-admin panel
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().lower().split(':')[0]  # strip port

        # Determine subdomain
        base_domain = getattr(settings, 'BASE_DOMAIN', 'transedge.site')

        if host == f'admin.{base_domain}':
            request.subdomain = 'admin'
        elif host in (base_domain, f'www.{base_domain}'):
            request.subdomain = 'main'
        else:
            request.subdomain = 'main'  # default for localhost

        response = self.get_response(request)
        return response