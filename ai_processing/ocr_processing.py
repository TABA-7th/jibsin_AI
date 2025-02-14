import json
import os
import requests
from ai_processing.building_ocr import building_keyword_ocr  # ✅ OCR 모듈 직접 가져오기

OCR_RESULTS_FILE = "./ocr_results.json"
FIREBASE_API_URL = "http://127.0.0.1:8000/api/fetch_latest_documents"  # ✅ Django API 주소

def get_classified_documents():
    """
    ✅ Firestore의 `fetch_latest_documents` API를 호출하여
    각 문서 유형별 최신 이미지 URL을 가져온다.
    """
    try:
        response = requests.get(FIREBASE_API_URL)
        response.raise_for_status()  # HTTP 오류 발생 시 예외 처리
        data = response.json()

        if "classified_documents" not in data:
            print("❌ Firestore 응답에서 문서를 찾을 수 없음!")
            return None

        return data["classified_documents"]  # ✅ {"building_registry": [...], "contract": [...], "registry_document": [...]}

    except requests.exceptions.RequestException as e:
        print(f"❌ Firestore API 호출 실패: {e}")
        return None

def run_all_ocr():
    """
    ✅ Firestore에서 가져온 문서들을 OCR 실행 후 JSON 파일로 저장
    """
    print("🔥 Firestore에서 문서 가져오는 중...")
    firebase_document_data = get_classified_documents()
    if not firebase_document_data:
        print("❌ Firestore에서 문서를 가져오지 못했습니다.")
        return None
    
    print(f"✅ Firestore 문서 가져오기 완료: {firebase_document_data}")

    all_results = {
        "building_registry": building_keyword_ocr(firebase_document_data.get("building_registry", []), "building_registry"),
        # "contract": contract_keyword_ocr(firebase_document_data.get("contract", []), "contract"),
        # "registry_document": registry_keyword_ocr(firebase_document_data.get("registry_document", []), "registry_document"),
    }

    try:
        with open(OCR_RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=4)
        print(f"✅ 모든 OCR 결과 저장 완료: {OCR_RESULTS_FILE}")
        return OCR_RESULTS_FILE
    except Exception as e:
        print(f"❌ OCR 결과 저장 실패: {e}")
        return None

# ✅ 실행 코드 추가
if __name__ == "__main__":
    run_all_ocr()  # ✅ Firebase에서 문서 가져와서 OCR 실행
