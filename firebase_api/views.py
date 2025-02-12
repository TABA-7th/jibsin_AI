# urls -> views.py(api 엔드포인트) -> utils.py(기능구현)

import firebase_admin
from firebase_admin import credentials, storage, firestore
import openai
import os
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv
from datetime import datetime, timedelta


# 환경 변수 로드
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") #  OpenAI API 키
OCR_SECRET_KEY = os.getenv("OCR_SECRET_KEY") #  네이버 OCR API 키 및 URL
OCR_API_URL = os.getenv("OCR_API_URL")
OCR_JSON_PATH = os.getenv("OCR_JSON_PATH") #  OCR 결과 JSON 저장 경로

if not OCR_JSON_PATH:
    raise ValueError("ERROR: OCR_JSON_PATH가 로드되지 않았습니다!")

# Firebase 설정 파일 경로
FIREBASE_KEY_PATH = os.path.join(os.path.dirname(__file__), "firebase_key.json")

# Firebase 앱 초기화 (이미 초기화되지 않았다면)
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'jibsin.firebasestorage.app'  # 여기에 실제 Firebase 프로젝트의 storageBucket 이름 입력
    })

# Create your views here.

db = firestore.client()

""" def get_images(request): 
    bucket = storage.bucket()
    blobs = bucket.list_blobs() 

    image_urls = []
    for blob in blobs:
        image_url = blob.generate_signed_url(expiration=3600)  # 1시간 동안 유효한 다운로드 링크 생성
        image_urls.append(image_url)

    return JsonResponse({"image_urls": image_urls}) """


# ✅ 최신 문서 유형별 가장 최신 이미지만 가져오기 (type 기준 필터링)
"""
    Firestore에서 최신 문서를 가져와 'type'별로 가장 최신 이미지만 반환하는 API.
    예: 
    - 계약서 3장 (3분 전), 등기부등본 1장 (방금) → 등기부등본 1장만 반환
    - 계약서 3장, 등기부등본 2장 → 각 타입별 가장 최근 이미지만 반환
    """

"""@csrf_exempt
def fetch_latest_documents(request):
   3장, 등기부등본 2장 → 각 타입별 가장 최근 이미지만 반환

    try:
        user_id = request.GET.get("user_id")  # 특정 유저 ID 기준 필터링 (선택 사항)
        docs_ref = db.collection("scanned_documents")  # Firestore 컬렉션 접근

        # 최신 업로드된 문서 정렬 (uploadDate 기준 내림차순)
        query = docs_ref.order_by("uploadDate", direction=firestore.Query.DESCENDING)

        # 특정 유저 ID 기준 필터링
        if user_id:
            query = query.where("userId", "==", user_id)

        docs = query.stream()

        # 'type' 기준 최신 문서 필터링
        latest_documents = {}
        document_types = ["contract", "registry", "building_registry"]

        for doc in docs:
            data = doc.to_dict()
            doc_type = data.get("type", "")

            # 만약 해당 type에 대해 최신 문서가 저장되지 않았다면 추가
            if doc_type in document_types and doc_type not in latest_documents:
                latest_documents[doc_type] = data

        return JsonResponse({"latest_documents": latest_documents}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500) """
    
@csrf_exempt
def fetch_recent_session_images(request):
    """
    Firestore에서 사용자가 가장 최근에 촬영한 세션의 모든 이미지를 가져오는 API
    (개수 제한 없음, 최신 세션의 모든 이미지 포함)
    """
    try:
        user_id = request.GET.get("user_id")  # 유저 ID 기준 필터링
        session_threshold = timedelta(minutes=5)  # 5분 이내 업로드된 이미지를 같은 세션으로 판단

        docs_ref = db.collection("scanned_documents")  # Firestore 컬렉션 접근
        query = docs_ref.order_by("uploadDate", direction=firestore.Query.DESCENDING)  # 최신순 정렬

        if user_id:
            query = query.where("userId", "==", user_id)  # 특정 유저 ID로 필터링

        docs = list(query.stream())  # 모든 문서 가져오기

        if not docs:
            return JsonResponse({"error": "No images found"}, status=404)

        # ✅ 최신 세션의 기준 시간 찾기 (가장 최근 업로드된 이미지의 timestamp)
        latest_upload_time = docs[0].to_dict().get("uploadDate")

        # ✅ 같은 세션 내에서 업로드된 이미지만 필터링 (예: 5분 이내 업로드된 것들만 같은 세션으로 판단)
        latest_session_images = []

        for doc in docs:
            data = doc.to_dict()
            image_upload_time = data.get("uploadDate")

            # 같은 세션(5분 이내) 내에서 업로드된 이미지만 포함
            if image_upload_time and abs(image_upload_time - latest_upload_time) <= session_threshold:
                latest_session_images.append(data)
            else:
                break  # 최신 세션이 끝났으므로 더 이상 가져오지 않음

        return JsonResponse({"latest_session_images": latest_session_images}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
def test_firebase_connection(request):
    """
    Firebase 연결이 정상적으로 되었는지 확인하는 API 엔드포인트
    """
    try:
        bucket = storage.bucket()
        return JsonResponse({"message": "Firebase 연결 성공!", "bucket": bucket.name})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
# 실제 Storage가 없으므로, 가짜 JSON 응답을 반환
# def get_fake_images(request):
    
    fake_image_urls = [
        "https://via.placeholder.com/150",
        "https://via.placeholder.com/200",
        "https://via.placeholder.com/250"
    ]
     # 테스트용 임시 이미지
    return JsonResponse({"image_url": fake_image_urls})


# OCR로 추출된 계약서 JSON 데이터를 GPT에 입력하고 법률적 분석을 수행하는 API. 위치가 잘못됨 수정해야됨!
#@csrf_exempt  # CSRF 보호 해제 (POST 요청 허용)
# def analyze_contract(request):
   
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
    
    

