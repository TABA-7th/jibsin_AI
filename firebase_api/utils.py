# Firebase를 초기화하고, 최신 이미지의 URL을 가져오는 함수 제공
# urls -> views.py(api 엔드포인트) -> utils.py(기능구현)

from firebase_admin import firestore
from typing import Dict, Optional
import json
from django.http import JsonResponse
import firebase_admin
from firebase_admin import credentials, storage, firestore 
import os
from google.cloud.firestore import FieldFilter
from datetime import datetime, timezone


#  Firebase 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIREBASE_KEY_PATH = os.path.join(BASE_DIR, "firebase_key.json")

# Firebase 앱 초기화 (이미 초기화되지 않았다면)
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'jibsin.firebasestorage.app'  #  Firebase 스토리지 버킷 이름
    })
db = firebase_admin.firestore.client()

def get_latest_images_by_type(): # Firebase Storage에서 가장 최근 업로드된 이미지 URL을 가져오는 함수.
    
    """ 가장 최근에 업로드된 '문서 유형'의 모든 이미지를 가져옴. ex) 3분 전에 계약서(4장) 업로드, 방금 등기부등본(1장) 업로드 -> 등기부등본 1장만 가져옴 """
    
    try:
        # Firestore 'scanned_documents' 컬렉션에서 최신 데이터 가져오기
        docs = db.collection("scanned_documents").order_by("uploadDate", direction=firestore.Query.DESCENDING).stream()

        latest_type = None  # 가장 최신 문서의 type (예: "building_registry", "contract")
        latest_images = []  # 해당 type에 속하는 이미지 리스트

        for doc in docs:
            data = doc.to_dict()
            if latest_type is None:
                latest_type = data.get("type")  # 가장 최신 type 저장
            if data.get("type") == latest_type:
                latest_images.append(data.get("imageUrl"))  # 같은 type이면 추가
            else:
                break  # 다른 type이 나오면 종료

        if not latest_images:
            return {"error": "최근 업로드된 이미지가 없습니다."}

        return {"latest_images": latest_images, "latest_type": latest_type}

    except Exception as e:
        return {"error": f"Firebase 이미지 가져오기 실패: {str(e)}"}
    
from google.cloud import firestore
import json



def save_ocr_result_to_firestore(user_id: str, contract_id: str, document_type: str, page_number: int, json_data: Dict) -> bool:
    """
    OCR 결과를 Firestore에 저장
    경로: /users/{user_id}/contracts/{contract_id}/analysis/{document_type}_page{page_number}
    """
    try:
        # analysis 컬렉션 참조 생성
        analysis_ref = (
            db.collection("users")
            .document(user_id)
            .collection("contracts")
            .document(contract_id)
            .collection("analysis")
            .document(f"{document_type}_page{page_number}")
        )

        # OCR 결과 저장
        analysis_ref.set(json_data)

        print(f"✅ OCR 결과 저장 완료: {document_type} page {page_number}")
        return True

    except Exception as e:
        print(f"❌ Firestore 저장 실패: {e}")
        return False
"""
# 목표 구조 - 추후 구현을 위해 주석 처리
def save_ocr_result_to_analyses(user_id, contract_id, document_type, page_number, json_data):
    
    # analyses 컬렉션 구조로 저장
    analyses_ref = (
        db.collection("analyses")
        .document("users")
        .collection(user_id)
        .document(contract_id)
        .collection(document_type)
        .document(f"page{page_number}.jpg")
    )
    
    try:
        analyses_ref.set(json_data)
        print(f"✅ Firestore 저장 완료: analyses/users/{user_id}/{contract_id}/{document_type}/page{page_number}")
    except Exception as e:
        print(f"Firestore 저장 실패: {e}")
"""


from firebase_admin import firestore
from typing import Dict, Optional
import json
from django.http import JsonResponse
db = firestore.client()

def get_latest_analysis_results(user_id: str, contract_id: str, document_type: str) -> Optional[Dict]:
    """특정 사용자의 가장 최근 문서 분석 결과 조회"""
    try:
        page_results = {}
        # 여러 페이지의 결과를 가져오기
        for page_num in range(1, 4):  # 1부터 3페이지까지 확인
            doc_ref = (
                db.collection("users")
                .document(user_id)
                .collection("contracts")
                .document(contract_id)
                .collection("analysis")
                .document(f"{document_type}_page{page_num}")
            )
            
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                ocr_result = data.get('ocr_result', {})
                
                # 필요한 필드만 추출하여 원하는 구조로 변환
                page_data = {}
                for key, value in ocr_result.items():
                    # 필드명에서 괄호 등 불필요한 부분 제거
                    cleaned_key = key.replace('(', '').replace(')', '')
                    if isinstance(value, dict):
                        page_data[cleaned_key] = {
                            "text": value.get('text', 'NA'),
                            "bounding_box": value.get('bounding_box', {
                                "x1": 0, "y1": 0, "x2": 0, "y2": 0
                            })
                        }
                
                if page_data:  # 결과가 있는 경우만 저장
                    page_results[f"page{page_num}"] = page_data

        # document_type을 키로 사용하되 한 번만 감싸기
        if page_results:
            return {document_type: page_results}
        return None
    except Exception as e:
        print(f"분석 결과 조회 실패: {e}")
        return None

def save_combined_results(user_id: str, contract_id: str, combined_data: Dict) -> bool:
    """통합된 OCR 결과를 Firestore에 저장"""
    try:
        doc_ref = (
            db.collection("users")
            .document(user_id)
            .collection("contracts")
            .document(contract_id)
            .collection("analysis")
            .document("combined_analysis")
        )
        
        
        doc_ref.set({
            **combined_data,  # OCR 결과 데이터
        })
        print(f"✅ 통합 OCR 결과 저장 완료: /users/{user_id}/contracts/{contract_id}/analysis/combined_analysis")
        return True
    except Exception as e:
        print(f"❌ 통합 OCR 결과 저장 실패: {e}")
        return False
    
    
def save_analysis_result(user_id: str, analysis_data: Dict) -> bool:
    """AI 분석 결과를 Firestore에 저장"""
    try:
        doc_ref = (
            db.collection("analyses")
            .document("users")
            .collection(user_id)
            .document("ai_analysis")
        )
        
        doc_ref.set({
            'result': analysis_data,
            'status': 'completed',
            'type': 'ai_analysis',
            'userId': user_id,
            'createdAt': firestore.SERVER_TIMESTAMP,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        print(f"✅ AI 분석 결과 저장 완료")
        return True
    except Exception as e:
        print(f"❌ AI 분석 결과 저장 실패: {e}")
        return False
