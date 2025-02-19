from django.urls import path
from .views import start_analysis, run_ocr, fake_start_analysis

urlpatterns = [
    path("start_analysis/", start_analysis, name="start_analysis"),
    path('run_ocr/', run_ocr, name='run_ocr'),
    path("fake_start_analysis/", fake_start_analysis, name="fake_start_analysis"),
]