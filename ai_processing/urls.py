from django.urls import path
from .views import run_ocr, test_ai, start_ai_analysis

urlpatterns = [
    path("start_analysis/", start_ai_analysis, name="start_ai_analysis"),
    path('run_ocr/', run_ocr, name='run_ocr'),
    path("test/", test_ai, name="test_ai"),
]

# path("start_ai_analysis/", start_ai_analysis, name="start_ai_analysis"), start_analysis,