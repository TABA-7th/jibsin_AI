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
from io import BytesIO
from PIL import Image
import requests
from typing import Dict, List
import traceback

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


def save_ocr_result_to_firestore(user_id: str, contract_id: str, 
                               document_type: str, page_number: int, 
                               json_data: Dict) -> bool:
    """
    OCR 결과를 Firestore에 저장
    """
    try:
        # OCR 결과를 저장할 문서 참조 생성
        doc_ref = (
            db.collection("users")
            .document(user_id)
            .collection("contracts")
            .document(contract_id)
            .collection("ocr_results")
            .document(f"{document_type}_page{page_number}")
        )
        
        # 데이터 저장
        doc_ref.set(json_data)
        print(f"✅ OCR 결과 저장 완료: {document_type} page{page_number}")
        return True

    except Exception as e:
        print(f"❌ OCR 결과 저장 실패: {e}")
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


def get_latest_analysis_results(user_id: str, contract_id: str, 
                              document_type: str) -> Optional[Dict]:
    """
    Firestore에서 최신 OCR 결과 가져오기
    """
    try:
        # OCR 결과 문서 가져오기
        results_ref = (
            db.collection("users")
            .document(user_id)
            .collection("contracts")
            .document(contract_id)
            .collection("ocr_results")
        )
        
        # 해당 문서 타입의 모든 페이지 결과 가져오기
        query = results_ref.where("document_type", "==", document_type)
        docs = query.stream()
        
        results = {}
        for doc in docs:
            data = doc.to_dict()
            if "ocr_result" in data:
                results[f"page{data['pageNumber']}"] = data["ocr_result"]
        
        return {document_type: results} if results else None

    except Exception as e:
        print(f"❌ OCR 결과 조회 실패: {e}")
        return None
def save_summary_to_firestore(user_id, contract_id, summary_data):
    """
    요약 결과를 Firestore에 저장하는 함수
    
    Args:
        user_id (str): 사용자 ID
        contract_id (str): 계약 ID
        summary_data (dict): 요약 결과 데이터
        
    Returns:
        bool: 저장 성공 여부
    """
    try:
        from firebase_api.utils import db
        
        # 'summaries' 컬렉션에 저장
        summary_ref = db.collection('users').document(user_id)\
                        .collection('contracts').document(contract_id)\
                        .collection('summary_analysis').document('summary')
        
        summary_ref.set(summary_data)
        print(f"✅ 요약 결과 저장 완료: {user_id}/{contract_id}")
        return True
        
    except Exception as e:
        print(f"❌ 요약 저장 중 오류 발생: {str(e)}")
        traceback.print_exc()
        return False


def save_combined_results(user_id: str, contract_id: str, combined_data: Dict) -> bool:
    """통합된 OCR 결과를 Firestore에 저장"""
    try:
        doc_ref = (
            db.collection("users")
            .document(user_id)
            .collection("contracts")
            .document(contract_id)
            .collection("ocr_results")
            .document("combined_analysis")
        )
        combined_data['createdAt'] = firestore.SERVER_TIMESTAMP
        combined_data['updatedAt'] = firestore.SERVER_TIMESTAMP
        
        
        
        doc_ref.set(combined_data, merge=True)
        print(f"✅ 통합 OCR 결과 저장 완료: /users/{user_id}/contracts/{contract_id}/ocr_results/combined_analysis")
        return True
    except Exception as e:
        print(f"❌ 통합 OCR 결과 저장 실패: {e}")
        return False
    
    
def save_analysis_result(user_id: str, contract_id: str, analysis_result: Dict, image_urls: Dict[str, list[str]]) -> bool:
    """
    AI 분석 결과를 AI_analysis 컬렉션에 저장
    
    Args:
        user_id (str): 사용자 ID
        contract_id (str): 계약서 ID
        analysis_result (Dict): 분석 결과 데이터
        image_urls (Dict[str, List[str]]): 문서 타입별 이미지 URL 리스트
        
    Returns:
        bool: 저장 성공 여부
    """
    try:
        # AI_analysis 컬렉션에 저장하되, 타임스탬프를 이용한 문서 ID 생성
        doc_id = f"analysis_{int(datetime.now().timestamp())}"
        
        # 각 문서 타입별로 이미지 크기 정보 추가
        for doc_type, urls in image_urls.items():
            if doc_type not in analysis_result:
                continue
                
            for page_num, url in enumerate(urls, 1):
                page_key = f"page{page_num}"
                
                if page_key in analysis_result[doc_type]:
                    analysis_result[doc_type][page_key]["image_dimensions"] = {
                        "width": get_page_width(url),
                        "height": get_page_height(url)
                    }
                    
        doc_ref = (
            db.collection("users")
            .document(user_id)
            .collection("contracts")
            .document(contract_id)
            .collection("AI_analysis")
            .document(doc_id)
        )
        
        doc_ref.set({
            'result': analysis_result,
            'status': 'completed',
            'type': 'ai_analysis',
            'userId': user_id,
            'contractId': contract_id,
            'createdAt': firestore.SERVER_TIMESTAMP,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        print(f"✅ AI 분석 결과 저장 완료: {doc_id}")
        return True
    except Exception as e:
        print(f"❌ AI 분석 결과 저장 실패: {e}")
        return False
    
def update_analysis_status(user_id: str, contract_id: str, status: str):
    """contract 문서의 analysisStatus 필드만 업데이트"""
    try:
        contract_ref = (
            db.collection("users")
            .document(user_id)
            .collection("contracts")
            .document(contract_id)
        )
        
        contract_ref.update({
            "analysisStatus": status,
            "updatedAt": firestore.SERVER_TIMESTAMP
        })
        print(f"✅ 분석 상태 업데이트: {status}")
        return True

    except Exception as e:
        print(f"❌ 분석 상태 업데이트 실패: {e}")
        return False
    

def get_page_height(url: str) -> int:
    """
    이미지 URL로부터 높이를 가져오는 함수
    
    Args:
        url (str): 이미지 URL
        
    Returns:
        int: 이미지 높이. 실패 시 기본값 1755 반환
    """
    try:
        response = requests.get(url)
        if response.status_code == 200:
            with Image.open(BytesIO(response.content)) as img:
                return img.height
        print(f"❌ 이미지 다운로드 실패 (상태 코드: {response.status_code})")
        return 1755
    except Exception as e:
        print(f"❌ 이미지 높이 측정 실패: {e}")
        return 1755

def get_page_width(url: str) -> int:
    """
    이미지 URL로부터 너비를 가져오는 함수
    
    Args:
        url (str): 이미지 URL
        
    Returns:
        int: 이미지 너비. 실패 시 기본값 1240 반환
    """
    try:
        response = requests.get(url)
        if response.status_code == 200:
            with Image.open(BytesIO(response.content)) as img:
                return img.width
        print(f"❌ 이미지 다운로드 실패 (상태 코드: {response.status_code})")
        return 1240
    except Exception as e:
        print(f"❌ 이미지 너비 측정 실패: {e}")
        return 1240
