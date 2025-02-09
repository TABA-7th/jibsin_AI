import firebase_admin
from firebase_admin import credentials, storage
import os
from django.http import JsonResponse

# Firebase 설정 파일 경로
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIREBASE_KEY_PATH = os.path.join(BASE_DIR, "firebase_key.json")

# Firebase 앱 초기화 (이미 초기화되지 않았다면)
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'your-firebase-app.appspot.com'  # 여기에 실제 Firebase 프로젝트의 storageBucket 이름 입력
    })

# Create your views here.


def get_images(request):
    bucket = storage.bucket()
    blobs = bucket.list_blobs()  # Storage 내 모든 파일 가져오기

    image_urls = []
    for blob in blobs:
        image_url = blob.generate_signed_url(expiration=3600)  # 1시간 동안 유효한 다운로드 링크 생성
        image_urls.append(image_url)

    return JsonResponse({"image_urls": image_urls})

def test_firebase_connection(request):
    """
    Firebase 연결이 정상적으로 되었는지 확인하는 API 엔드포인트
    """
    try:
        bucket = storage.bucket()
        return JsonResponse({"message": "Firebase 연결 성공!", "bucket": bucket.name})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    

def get_fake_images(request):
    # 실제 Storage가 없으므로, 가짜 JSON 응답을 반환
    fake_image_urls = [
        "https://via.placeholder.com/150",
        "https://via.placeholder.com/200",
        "https://via.placeholder.com/250"
    ]
     # 테스트용 임시 이미지
    return JsonResponse({"image_url": fake_image_urls})