from django.urls import path
from .views import test_firebase_connection, get_fake_images

urlpatterns = [
    path("test/", test_firebase_connection, name="test_firebase_connection"),
    path('get_fake_images/', get_fake_images, name='get_fake_images'),
]
