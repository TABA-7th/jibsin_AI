# urls -> views.py(api 엔드포인트) -> utils.py(기능구현)

import firebase_admin
from firebase_admin import credentials, storage, firestore
import requests
import tempfile
import openai
import os
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv
from datetime import datetime, timedelta
from ai_processing.ocr import registry_ocr #굳이..?

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


db = firestore.client()

def test_firebase_connection(request):
    """
    Firebase 연결이 정상적으로 되었는지 확인하는 API 엔드포인트
    """
    try:
        bucket = storage.bucket()
        return JsonResponse({"message": "Firebase 연결 성공!", "bucket": bucket.name})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    



@csrf_exempt
def fetch_latest_documents(request): ### document문서들을 통합해서 저장하는 코드
    """
     Firestore에서 최신 문서를 가져와 문서 유형별로 분류 후 반환 (OCR 수행 X)
    """
    try:
        user_id = request.GET.get("user_id")
        session_threshold = timedelta(minutes=1800)

        docs_ref = db.collection("scanned_documents")
        query = docs_ref.order_by("uploadDate", direction=firestore.Query.DESCENDING)

        if user_id:
            query = query.where("userId", "==", user_id)

        docs = list(query.stream())

        if not docs:
            return JsonResponse({"error": "No images found"}, status=404)

        #  최신 세션의 기준 시간 찾기
        latest_upload_time = docs[0].to_dict().get("uploadDate")
        latest_session_documents = {"contract": [], "registry_document": [], "building_registry": []}

        # 최신 세션의 문서들을 임시 저장할 딕셔너리
        temp_documents = {
            "contract": [],
            "registry_document": [],
            "building_registry": []
        }

        for doc in docs:
            data = doc.to_dict()
            image_upload_time = data.get("uploadDate")
            doc_type = data.get("type", "unknown")

            if image_upload_time and abs(image_upload_time - latest_upload_time) <= session_threshold:
                if doc_type in temp_documents:
                    temp_documents[doc_type].append({
                        'imageUrl': data["imageUrl"],
                        'pageNumber': data.get("pageNumber", 1),  # 페이지 번호가 없으면 1로 기본 설정
                        'uploadDate': image_upload_time
                    })
        
            else:
                break  # 최신 세션이 끝났으므로 더 이상 가져오지 않음

        # 각 문서 타입별로 페이지 번호순으로 정렬하여 URL 리스트 생성
        for doc_type in temp_documents:
            if temp_documents[doc_type]:
                # 페이지 번호로 정렬
                sorted_docs = sorted(temp_documents[doc_type], key=lambda x: x['pageNumber'])
                # URL만 추출하여 저장
                latest_session_documents[doc_type] = [doc['imageUrl'] for doc in sorted_docs]
                print(f"✅ {doc_type} 정렬 완료: {len(latest_session_documents[doc_type])} 페이지")

        if not any(latest_session_documents.values()):
            return JsonResponse({"error": "No images found in recent session"}, status=404)

        #  OCR 수행 X, 이미지 URL만 반환
        return JsonResponse({"classified_documents": latest_session_documents}, status=200)

    except Exception as e:
        print(f"❌ 문서 조회 중 오류 발생: {e}")
        return JsonResponse({"error": str(e)}, status=500)


    