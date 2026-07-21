from django.urls import path, include

urlpatterns = [
    path('', include('Business.urls')),
]