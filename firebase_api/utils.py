# Firebase를 초기화하고, 최신 이미지의 URL을 가져오는 함수 제공

import firebase_admin
from firebase_admin import credentials, storage
import os

#  Firebase 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIREBASE_KEY_PATH = os.path.join(BASE_DIR, "firebase_key.json")

# Firebase 앱 초기화 (이미 초기화되지 않았다면)
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'your-firebase-app.appspot.com'  # 여기에 실제 Firebase 프로젝트의 storageBucket 이름 입력
    })

def get_latest_image_url(): # Firebase Storage에서 가장 최근 업로드된 이미지 URL을 가져오는 함수.
    
    
    try:
        bucket = storage.bucket()
        blobs = list(bucket.list_blobs())

        if not blobs:
            raise ValueError("Firebase Storage에 이미지가 없습니다.")

        # ✅ 가장 최근 업데이트된 이미지 선택
        latest_blob = sorted(blobs, key=lambda x: x.updated, reverse=True)[0]

        # 🔹 서명된 URL 생성 (1시간 유효)
        image_url = latest_blob.generate_signed_url(expiration=3600)

        return image_url

    except Exception as e:
        raise ValueError(f"❌ Firebase 이미지 가져오기 실패: {str(e)}")
