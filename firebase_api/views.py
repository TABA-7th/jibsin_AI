import firebase_admin
from firebase_admin import credentials, storage
import openai
import os
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv
from .utils import get_latest_image_url



load_dotenv()
#  OpenAI API 키
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

#  네이버 OCR API 키 및 URL
OCR_SECRET_KEY = os.getenv("OCR_SECRET_KEY")
OCR_API_URL = os.getenv("OCR_API_URL")

#  OCR 결과 JSON 저장 경로
OCR_JSON_PATH = os.getenv("OCR_JSON_PATH")
if not OCR_JSON_PATH:
    raise ValueError(" ERROR: OCR_JSON_PATH가 로드되지 않았습니다!")

# Firebase 설정 파일 경로
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIREBASE_KEY_PATH = os.path.join(BASE_DIR, "firebase_key.json")

# Firebase 앱 초기화 (이미 초기화되지 않았다면)
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'jibsin.firebasestorage.app'  # 여기에 실제 Firebase 프로젝트의 storageBucket 이름 입력
    })

# Create your views here.


def get_images(request): # Storage 내 모든 파일 가져오기
    bucket = storage.bucket()
    blobs = bucket.list_blobs() 

    image_urls = []
    for blob in blobs:
        image_url = blob.generate_signed_url(expiration=3600)  # 1시간 동안 유효한 다운로드 링크 생성
        image_urls.append(image_url)

    return JsonResponse({"image_urls": image_urls}) 

#Firebase에서 가장 최근 업로드된 이미지 URL을 반환하는 API.
@csrf_exempt
def fetch_latest_image(request):
    
    try:
        image_url = get_latest_image_url()
        return JsonResponse({"latest_image_url": image_url}, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
# Firebase 연결이 정상적으로 되었는지 확인하는 API 엔드포인트
def test_firebase_connection(request):
    
    
    try:
        bucket = storage.bucket()
        return JsonResponse({"message": "Firebase 연결 성공!", "bucket": bucket.name})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
# 실제 Storage가 없으므로, 가짜 JSON 응답을 반환
def get_fake_images(request):
    
    fake_image_urls = [
        "https://via.placeholder.com/150",
        "https://via.placeholder.com/200",
        "https://via.placeholder.com/250"
    ]
     # 테스트용 임시 이미지
    return JsonResponse({"image_url": fake_image_urls})


# OCR로 추출된 계약서 JSON 데이터를 GPT에 입력하고 법률적 분석을 수행하는 API. 위치가 잘못됨 수정해야됨!
@csrf_exempt  # CSRF 보호 해제 (POST 요청 허용)
def analyze_contract(request):
   
    try:
        # OCR JSON 파일 읽기
        if not os.path.exists(OCR_JSON_PATH):
            return JsonResponse({"error": " OCR JSON 파일이 존재하지 않습니다!"}, status=400)

        with open(OCR_JSON_PATH, "r", encoding="utf-8") as f:
            request_data = json.load(f)  # OCR 결과 JSON 로드

        # OpenAI API 호출
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "당신은 법률 전문가입니다. 주어진 정보가 계약서인지, 건축물 등본인지, 등기부등본인지 알아내어 분석하고 사용자에게 주의할 점을 알려주세요."},
                {"role": "user", "content": f"다음 계약서를 분석하고, 주의해야 할 점을 알려줘: {json.dumps(request_data, ensure_ascii=False)}"}
            ],
            max_tokens=500
        )

        # GPT 응답
        analysis_result = response.choices[0].message.content
        return JsonResponse({"analysis": analysis_result}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
    

