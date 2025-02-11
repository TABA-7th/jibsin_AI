
from django.contrib import admin
from django.urls import path, include
from firebase_api.views import fetch_latest_image

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/", include("firebase_api.urls")),
    path("ai/", include("ai_processing.urls")),
    path("fetch_latest_image/", fetch_latest_image, name="fetch_latest_image"),  # Firebase API 라우트 추가
]
