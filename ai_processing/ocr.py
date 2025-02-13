import time
import pandas as pd
import cv2
import json
import requests
import uuid
import os
import tempfile
from dotenv import load_dotenv

# ✅ 환경 변수 로드
load_dotenv()

# ✅ .env에서 환경 변수 가져오기
OCR_SECRET_KEY = os.getenv("OCR_SECRET_KEY")
OCR_API_URL = os.getenv("OCR_API_URL")

MODEL = "gpt-4o"

def download_image(image_url): # ocr을 수행하기 위해서는 local파일이 필요함!
    """
    ✅ 이미지 URL에서 다운로드하여 임시 파일로 저장하는 함수
    """
    response = requests.get(image_url, stream=True)
    if response.status_code != 200:
        print(f"❌ 이미지 다운로드 실패: {image_url}")
        return None

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    temp_file.write(response.content)
    temp_file.flush()
    temp_file.close()

    return temp_file.name

def contract_ocr(image_url):
    """
    ✅ 계약서 OCR 수행 함수 (이미지 URL을 받아서 OCR 처리)
    """
    image_path = download_image(image_url)
    if not image_path:
        return pd.DataFrame()  # OCR 실패 시 빈 DataFrame 반환

    image = cv2.imread(image_path)
    if image is None:
        print(f"❌ 계약서 이미지 로드 실패: {image_url}")
        return pd.DataFrame()

    target_size = (1240, 1753)
    image_resized = cv2.resize(image, target_size, interpolation=cv2.INTER_AREA)

    request_json = {
        'images': [{'format': 'jpg', 'name': 'contract'}],
        'requestId': str(uuid.uuid4()),
        'version': 'V2',
        'timestamp': int(round(time.time() * 1000))
    }
    payload = {'message': json.dumps(request_json).encode('UTF-8')}
    headers = {'X-OCR-SECRET': OCR_SECRET_KEY}

    _, img_encoded = cv2.imencode('.jpg', image_resized)
    files = [('file', ('contract.jpg', img_encoded.tobytes(), 'image/jpeg'))]

    response = requests.post(OCR_API_URL, headers=headers, data=payload, files=files)

    os.remove(image_path)  # ✅ OCR 완료 후 임시 파일 삭제

    if response.status_code == 200:
        ocr_results = response.json()
        all_data = []

        for image_result in ocr_results['images']:
            for field in image_result['fields']:
                text = field['inferText']
                bounding_box = field['boundingPoly']['vertices']
                x1, y1 = int(bounding_box[0]['x']), int(bounding_box[0]['y'])
                x2, y2 = int(bounding_box[2]['x']), int(bounding_box[2]['y'])

                all_data.append({
                    "Text": text,
                    "x1": x1, "y1": y1,
                    "x2": x2, "y2": y2
                })

        return pd.DataFrame(all_data) # OCR 성공 시 결과 반환

    return pd.DataFrame()  # OCR 실패 시 빈 DataFrame 반환

def registry_ocr(image_url):
    """
    ✅ 등기부등본 OCR 수행 함수 (이미지 URL을 받아서 OCR 처리)
    """
    image_path = download_image(image_url)
    
    if not image_path:
        print(f"❌ 등기부등본 이미지 로드 실패: {image_url}")
        return pd.DataFrame()

    request_json = {
        'images': [{'format': 'jpg', 'name': 'ledger'}],
        'requestId': str(uuid.uuid4()),
        'version': 'V2',
        'timestamp': int(round(time.time() * 1000))
    }
    payload = {'message': json.dumps(request_json).encode('UTF-8')}
    files = [('file', open(image_path, 'rb'))]
    headers = {'X-OCR-SECRET': OCR_SECRET_KEY}

    response = requests.post(OCR_API_URL, headers=headers, data=payload, files=files)

    os.remove(image_path)  # ✅ OCR 완료 후 임시 파일 삭제

    if response.status_code == 200:
        ocr_results = response.json()
        all_data = []

        for image_result in ocr_results['images']:
            for field in image_result['fields']:
                text = field['inferText']
                bounding_box = field['boundingPoly']['vertices']
                x1, y1 = int(bounding_box[0]['x']), int(bounding_box[0]['y'])
                x2, y2 = int(bounding_box[2]['x']), int(bounding_box[2]['y'])
                all_data.append({
                    "Text": text,
                    "x1": x1, "y1": y1,
                    "x2": x2, "y2": y2
                })
        df = pd.DataFrame(all_data)
        return df # OCR 성공 시 결과 반환

    print(f"❌ OCR 실패: {response.status_code}, {response.text}")
    return None # OCR 실패 시 None 반환


# 🔥 4️⃣ OCR 실행 함수 (문서 유형별로 처리)
def process_documents_by_type(classified_documents):
    """
    ✅ Firestore에서 받은 문서 이미지 URL을 OCR에 넣어 실행하는 함수
    """
    ocr_results = {"contract": [], "registry_document": [], "building_registry": []}

    for doc_type, image_urls in classified_documents.items():
        for image_url in image_urls:
            # ✅ OCR 실행
            if doc_type == "contract":
                ocr_result = contract_ocr(image_url)
            elif doc_type == "registry_document":
                ocr_result = registry_ocr(image_url)   ## 건축물 대장정 추가해야돼!
            else:
                continue

            if ocr_result.empty:
                print(f"❌ OCR 결과가 없음: {image_url}")
            else:
                print(f"✅ OCR 성공: {image_url}")

            ocr_results[doc_type].append(ocr_result.to_dict(orient="records"))

    return ocr_results


def read_registry_image(client, image_url): 
    """
    추출한 텍스트 중에서 특정한 부분 좌표와 반환하는 함수(등기부등본본)
    """
    df_regis = registry_ocr(image_url)
    if df_regis is None or df_regis.empty:
        print("❌ OCR 결과가 없으므로 GPT 요청을 건너뜁니다.")
        return None


    # ✅ GPT 입력 프롬프트
    response = client.chat.completions.create(
        model= MODEL ,
        messages=[
            {"role": "user", "content": "출력은 요청 정보만 [':',':']의 딕셔너리 형태로 출력해줘"},
            {"role": "user", "content": [
                {"type": "text", "text": (
                    f"{df_regis}는 주어진 이미지의 OCR 데이터야.\n\n"
                    f"'Text'는 단어들이고 이후는 바운딩 박스 위치야.\n\n"
                    f"'소유자현황'보다 y1이 낮은 부분에서 '도로명주소', '호명칭'과 연결되는 정보를 찾아줘.\n\n"
                    f"그리고 '공용부분'보다 y1이 낮고 '전유부분'보다 높은 부분에서  '면적(m2)', '성명(명칭)'에 해당하는 정보를 찾아줘.\n\n"
                    f"면적은 여러 개 있으면 가장 위에 있는 것만 출력해줘.\n\n"
                    f"💡 **반환 예시:**\n"
                    f"{{\n"
                    f"  \"임대인\": {{\"text\": \"홍길동\", \"bounding_box\": {{\"x1\": 100, \"y1\": 200, \"x2\": 300, \"y2\": 250}}}},\n"
                    f"  \"임차인\": {{\"text\": \"김철수\", \"bounding_box\": {{\"x1\": 120, \"y1\": 220, \"x2\": 320, \"y2\": 270}}}},\n"
                    f"  \"소재지\": {{\"text\": \"서울특별시 강남구 테헤란로 123\", \"bounding_box\": {{\"x1\": 140, \"y1\": 240, \"x2\": 340, \"y2\": 290}}}},\n"
                    f"  \"계약기간\": {{\"text\": \"2025-01-01 ~ 2026-01-01\", \"bounding_box\": {{\"x1\": 150, \"y1\": 250, \"x2\": 350, \"y2\": 300}}}},\n"
                    f"  \"보증금_1\": {{\"text\": \"10,000,000원\", \"bounding_box\": {{\"x1\": 160, \"y1\": 260, \"x2\": 360, \"y2\": 310}}}},\n"
                    f"  \"입금계좌\": {{\"text\": \"123-45-67890\", \"bounding_box\": {{\"x1\": 170, \"y1\": 270, \"x2\": 370, \"y2\": 320}}}}\n"
                    f"}}\n\n"
                    f"⚠️ **주의사항:**\n"
                    f"- `xy` 데이터의 바운딩 박스를 그대로 사용하지 말고, `df` 데이터와 가장 적합한 위치로 조정\n"
                    f"- 텍스트가 여러 바운딩 박스에 걸쳐 있는 경우, **최소 좌표(x1, y1) & 최대 좌표(x2, y2)**로 병합\n"
                    f"- 내용이 없을 경우 `NA`로 반환\n"
                    f"- JSON 형식이 정확하도록 반환할 것!"
                )},
                {"type": "image_url", "image_url": {"url": image_url}} # Firebase 이미지 URL 직접 사용
            ]}
        ],
        max_tokens=1000
    )
    return response.choices[0].message.content

