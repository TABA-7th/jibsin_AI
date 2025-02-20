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
    




def fetch_latest_documents(request):
    """
    Firestore에서 최신 문서 URL 가져오기
    """
    try:
        user_id = request.GET.get('user_id')
        contract_id = request.GET.get('contract_id')

        print(f"Fetching documents for user_id: {user_id}, contract_id: {contract_id}")

        if not user_id or not contract_id:
            return JsonResponse({
                "error": "user_id와 contract_id가 필요합니다"
            }, status=400)

        # 계약 문서 직접 참조
        contract_ref = (
            db.collection("users")
            .document(user_id)
            .collection("contracts")
            .document(contract_id)
        )

        # 문서 가져오기
        contract_doc = contract_ref.get()
        if not contract_doc.exists:
            return JsonResponse({
                "error": "계약 문서를 찾을 수 없습니다"
            }, status=404)

        contract_data = contract_doc.to_dict()
        
        # 문서 타입별로 URL 분류
        classified_docs = {
            "registry_document": [],
            "contract": [],
            "building_registry": []
        }

        # building_registry 처리
        if 'building_registry' in contract_data:
            for doc in contract_data['building_registry']:
                if 'imageUrl' in doc:
                    classified_docs['building_registry'].append(doc['imageUrl'])

        # contract 처리
        if 'contract' in contract_data:
            # contract가 문자열 URL 배열인 경우
            for doc in contract_data['contract']:
                if 'imageUrl' in doc:
                    classified_docs['contract'].append(doc['imageUrl'])

        # registry_document 처리
        if 'registry_document' in contract_data:
            for doc in contract_data['registry_document']:
                if 'imageUrl' in doc:
                    classified_docs['registry_document'].append(doc['imageUrl'])

        print(f"Classified documents: {classified_docs}")

        return JsonResponse({
            "classified_documents": classified_docs
        })

    except Exception as e:
        print(f"Error in fetch_latest_documents: {str(e)}")
        return JsonResponse({
            "error": f"문서 조회 중 오류 발생: {str(e)}"
        }, status=500)