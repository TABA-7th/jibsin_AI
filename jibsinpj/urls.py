
from django.contrib import admin
from django.urls import path, include
from firebase_api.views import fetch_latest_image

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/", include("firebase_api.urls")),
    path("ai/", include("ai_processing.urls")),
]
