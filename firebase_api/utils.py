# Firebase를 초기화하고, 최신 이미지의 URL을 가져오는 함수 제공
# urls -> views.py(api 엔드포인트) -> utils.py(기능구현)

import firebase_admin
from firebase_admin import credentials, storage, firestore 
import os

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



def save_ocr_result_to_firestore(group_id, document_type, page_number, json_data):
    """
    현재 구조 - Firestore의 scanned_documents 컬렉션에 OCR 결과 저장
    :param group_id: 문서 그룹 ID
    :param document_type: 문서 타입 ('building_registry', 'registry_document', 'contract')
    :param page_number: 페이지 번호
    :param json_data: OCR 결과 JSON 데이터
    """
    try:

        doc_path = f"analyses_ref/{group_id}"
        print(f"Trying to update document at: {doc_path}")

        # scanned_documents 컬렉션의 해당 문서 직접 참조
        doc_ref = db.collection("analyses_ref").document(group_id)
        
        # 문서가 존재하는지 먼저 확인
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.update({
                'result': json_data,
                'status': 'completed'
            })
            print(f"✅ Firestore 저장 완료: {doc_path}")
        else:
            # 문서가 없으면 새로 생성
            doc_ref.set({
                'result': json_data,
                'status': 'completed',
                'type': document_type,
                'pageNumber': page_number
            })
            print(f"✅ Firestore 새 문서 생성 완료: {doc_path}")
    except Exception as e:
        print(f"Firestore 저장 실패: {e}")

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
