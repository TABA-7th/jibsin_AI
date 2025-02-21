
from django.contrib import admin
from django.urls import path, include
from ai_processing import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/", include("firebase_api.urls")),
    path("ai/", include("ai_processing.urls")),
    path("ai/test/", views.test_view, name="test_view"),
]
