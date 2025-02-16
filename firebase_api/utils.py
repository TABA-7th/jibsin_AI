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
        # scanned_documents 컬렉션에서 해당 페이지 문서 조회
        scanned_docs = db.collection("scanned_documents").where("groupId", "==", group_id).where("type", "==", document_type).where("pageNumber", "==", page_number).get()
        
        if not scanned_docs:
            print(f"해당하는 문서를 찾을 수 없습니다: groupId={group_id}, type={document_type}, page={page_number}")
            return

        # 첫 번째 문서에서 userId 가져오기
        doc_data = scanned_docs[0].to_dict()
        user_id = doc_data.get('userId')
        if not user_id:
            print("userId를 찾을 수 없습니다")
            return


        doc_path = f"analyses/users/{user_id}/{document_type}_{page_number}"
        print(f"Trying to update document at: {doc_path}")


        analyses_ref = (
            db.collection("analyses")  # collection
            .document("users")         # document
            .collection(user_id)       # collection
            .document(f"{document_type}_{page_number}")  # document
        )

        # 문서가 존재하는지 먼저 확인
        doc = analyses_ref.get()

        if doc.exists:
                # 기존 문서 업데이트
                analyses_ref.update({
                    'result': json_data,
                    'status': 'completed',
                    'pageNumber': page_number,
                    'groupId': group_id,
                    'updatedAt': firestore.SERVER_TIMESTAMP
                })
                print(f"✅ Firestore 업데이트 완료: {doc_path}")
        else:
                # 새 문서 생성
                analyses_ref.set({
                    'result': json_data,
                    'status': 'completed',
                    'type': document_type,
                    'pageNumber': page_number,
                    'groupId': group_id,
                    'userId': user_id,
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'updatedAt': firestore.SERVER_TIMESTAMP
                })
                print(f"✅ Firestore 새 문서 생성 완료: {doc_path}")

    except Exception as e:
        print(f"❌ Firestore 저장 실패: {e}")
        raise e

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
