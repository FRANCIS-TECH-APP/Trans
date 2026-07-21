"""
URL configuration for consignee project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""


# consignee/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


from Business.sub_admin_views import sub_admin_landing,public_default_landing
from Business import views



urlpatterns = [
    path('admin/', admin.site.urls),
    path('', public_default_landing, name='home'),
    path('shipping/', include('Business.urls')),
    path('track/', views.tracking_search, name='tracking-search'),
    path('track/<str:tracking_id>/', views.tracking_detail, name='tracking-detail'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)