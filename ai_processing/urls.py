from django.urls import path
from .views import start_analysis, run_ocr

urlpatterns = [
    path("start_analysis/", start_analysis, name="start_analysis"),
    path('run_ocr/', run_ocr, name='run_ocr'), 
]