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
@csrf_exempt
def fetch_latest_documents(request):
    try:
        if request.method == 'POST':
            data = json.loads(request.body)
            user_id = data.get('user_id')
            contract_id = data.get('contract_id')
            document_type = data.get('document_type')
        else:
            user_id = request.GET.get('user_id')
            contract_id = request.GET.get('contract_id')
            document_type = request.GET.get('document_type')

        if not user_id or not contract_id:
            return JsonResponse({"error": "user_id와 contract_id가 필요합니다"}, status=400)

        contract_ref = (db.collection("users")
                       .document(user_id)
                       .collection("contracts")
                       .document(contract_id))

        doc = contract_ref.get()
        
        if not doc.exists:
            print(f"❌ 문서를 찾을 수 없음: {user_id}/{contract_id}")
            return JsonResponse({"error": "계약 문서를 찾을 수 없습니다"}, status=404)

        contract_data = doc.to_dict()
        print(f"📄 계약 데이터 조회: {contract_id}")
        print(f"📄 문서 타입: {document_type}")
        print(f"📄 계약 데이터: {contract_data}")

        latest_session_documents = {
            "contract": [],
            "registry_document": [],
            "building_registry": []
        }
        
        # 각 문서 타입별 데이터 처리
        for doc_type in latest_session_documents.keys():
            if doc_type in contract_data:
                if doc_type == 'building_registry':
                    # building_registry는 객체 리스트 구조
                    pages = contract_data[doc_type]
                    for page in pages:
                        if isinstance(page, dict) and 'imageUrl' in page:
                            latest_session_documents[doc_type].append(page['imageUrl'])
                else:
                    # contract와 registry_document는 URL 문자열 리스트
                    if isinstance(contract_data[doc_type], list):
                        latest_session_documents[doc_type].extend(contract_data[doc_type])

        # 요청된 document_type에 대한 URL이 없는 경우
        if document_type and not latest_session_documents.get(document_type):
            print(f"❌ {document_type} 타입의 문서 URL을 찾을 수 없음")
            return JsonResponse({"error": "문서 URL을 찾을 수 없습니다"}, status=404)

        response_data = {
            "classified_documents": latest_session_documents,
            "user_id": user_id,
            "contract_id": contract_id
        }
        
        print(f"✅ 응답 데이터: {response_data}")
        return JsonResponse(response_data)
    
    except Exception as e:
        print(f"❌ 문서 조회 중 오류 발생: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)