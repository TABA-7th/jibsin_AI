
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/", include("firebase_api.urls")),
    path("ai/", include("ai_processing.urls")),
]
