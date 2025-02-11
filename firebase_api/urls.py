#  Firebase 관련 API의 URL을 정의하는 파일
# 역할: views.py의 함수들과 Django의 URL을 연결
# urls -> views.py(api 엔드포인트) -> utils.py(기능구현)

from django.urls import path
from .views import (
    fetch_latest_images,  # 가장 최근의 특정 문서 유형의 이미지만 가져오는 API
    get_images,
    test_firebase_connection,
    get_fake_images,
    analyze_contract,
)

urlpatterns = [
    path("get_images/", get_images, name="get_images"), # Firebase Storage에서 모든 이미지 가져오기
    path("test_firebase_connection/", test_firebase_connection, name="test_firebase_connection"), # Firebase 연결 테스트
    path('get_fake_images/', get_fake_images, name='get_fake_images'), # 테스트용 가짜 이미지 반환
    path("analyze_contract/", analyze_contract, name="analyze_contract"), # OCR 결과를 기반으로 GPT 분석 수행
    path("fetch_latest_images/", fetch_latest_images, name="fetch_latest_images"),
]
