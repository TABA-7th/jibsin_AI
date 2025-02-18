#  Firebase 관련 API의 URL을 정의하는 파일
# 역할: views.py의 함수들과 Django의 URL을 연결
# urls -> views.py(api 엔드포인트) -> utils.py(기능구현)

from django.urls import path
from .views import (
    fetch_latest_documents,
    test_firebase_connection,
)
from . import views

urlpatterns = [
    path("test_firebase_connection/", test_firebase_connection, name="test_firebase_connection"), # Firebase 연결 테스트
    path("fetch_latest_documents/", fetch_latest_documents, name="fetch_latest_documents"), # firebase에서 날짜로 분류 -> type분류
]
