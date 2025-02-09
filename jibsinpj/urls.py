
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path("firebase-api/", include("firebase_api.urls")),  # Firebase API 라우트 추가
]
