from ai_processing.ocr import process_documents_by_type
import requests

def test_ocr():
    # Firestore에서 최신 문서 가져오기
    response = requests.get("http://127.0.0.1:8000/api/fetch_latest_documents/?user_id=test_user")

    if response.status_code == 200:
        classified_documents = response.json().get("classified_documents", {})

        # ✅ OCR 실행
        ocr_results = process_documents_by_type(classified_documents)

        print("🔍 OCR 결과:")
        print(ocr_results)
    else:
        print("❌ Firestore에서 문서를 가져오지 못함:", response.json())

if __name__ == "__main__":
    test_ocr()