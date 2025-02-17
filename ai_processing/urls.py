from django.urls import path
from .views import analysis, run_ocr
urlpatterns = [
    path("analysis/",analysis, name = "analysis"),
    path('run_ocr/', run_ocr, name='run_ocr'), 
]