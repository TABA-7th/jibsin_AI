import json
import os
import requests
from ai_processing.registry_ocr import registry_keyword_ocr #  OCR 모듈 직접 가져오기
from ai_processing.contract_ocr import contract_keyword_ocr 
from ai_processing.building_ocr import building_keyword_ocr
from firebase_api.views import fetch_latest_documents  

OCR_RESULTS = {
    "contract": "./ocr_results_contract.json",
    "registry_document": "./ocr_results_registry.json",
    "building_registry": "./ocr_results_building.json"
}
ALL_RESULTS_FILE = "./ocr_results_all.json"
FIREBASE_API_URL = "http://127.0.0.1:8000/api/fetch_latest_documents"  #  Django API 주소

def get_classified_documents():
    """
     Firestore의 `fetch_latest_documents` API를 호출하여
    각 문서 유형별 최신 이미지 URL을 가져온다.
    """
    try:
        response = requests.get(FIREBASE_API_URL)
        response.raise_for_status()  # HTTP 오류 발생 시 예외 처리
        data = response.json()

        if "classified_documents" not in data:
            print(" Firestore 응답에서 문서를 찾을 수 없음!")
            return None

        return data["classified_documents"]  # {"building_registry": [...], "contract": [...], "registry_document": [...]}

    except requests.exceptions.RequestException as e:
        print(f" Firestore API 호출 실패: {e}")
        return None

def run_all_ocr():
    """
     Firestore에서 가져온 문서들을 OCR 실행 후 JSON 파일로 저장
    """
    print(" Firestore에서 문서 가져오는 중...")
    firebase_document_data = get_classified_documents()
    if not firebase_document_data:
        print(" Firestore에서 문서를 가져오지 못했습니다.")
        return None
    
    print(f" Firestore 문서 가져오기 완료: {firebase_document_data}")

    all_results = {}

    # 등기부등본 OCR 처리
    #if firebase_document_data.get("registry_document"):
        #registry_result = registry_keyword_ocr(
        #    firebase_document_data.get("registry_document", []), 
         #   "registry_document"
       # )
       # if registry_result:
        #    all_results["registry_document"] = registry_result
    
    # 건축물대장 OCR 처리
    if firebase_document_data.get("building_registry"):
        building_result = building_keyword_ocr(
            firebase_document_data.get("building_registry", []),
            "building_registry"
        )  
        if building_result:
            all_results["building_registry"] = building_result
            # 개별 결과 파일 저장
            with open(OCR_RESULTS["building_registry"], "w", encoding="utf-8") as f:
                json.dump({"building_registry": building_result}, f, ensure_ascii=False, indent=4)
            print(f"✅ 건축물대장 OCR 결과 저장 완료: {OCR_RESULTS['building_registry']}")

    # 계약서 OCR 처리 **** 완료 *****
#    if firebase_document_data.get("contract"):
#        contract_result = contract_keyword_ocr(
#            firebase_document_data.get("contract", []), 
#            "contract"
#        )
#        if contract_result:
#            all_results["contract"] = contract_result

 #           with open(OCR_RESULTS["contract"], "w", encoding="utf-8") as f:
  #              json.dump({"contract": contract_result}, f, ensure_ascii=False, indent=4)
   #         print(f"✅ 계약서 OCR 결과 저장 완료: {OCR_RESULTS['contract']}")

    try:
        # 전체 결과 저장
        with open(ALL_RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=4)
        print(f"✅ 전체 OCR 결과 저장 완료: {ALL_RESULTS_FILE}")
        return ALL_RESULTS_FILE
    except Exception as e:
        print(f" OCR 결과 저장 실패: {e}")
        return None

#  실행 코드 추가
if __name__ == "__main__":
    run_all_ocr()  #  Firebase에서 문서 가져와서 OCR 실행
