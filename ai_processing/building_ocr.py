import time
import pandas as pd
import json
import requests
import uuid
import openai
import os
import base64
import tempfile
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

#  환경 변수 로드
load_dotenv()

# API 설정
OCR_SECRET_KEY = os.getenv("OCR_SECRET_KEY")
OCR_API_URL = os.getenv("OCR_API_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4o"

client = openai.OpenAI(api_key=OPENAI_API_KEY)

#  Firebase에서 이미지 다운로드 후, 로컬 파일로 저장
def download_image(image_url):
    """
     Firebase에서 이미지 URL을 가져와 로컬 파일로 저장 (Clova OCR 실행을 위해 필요)
    """
    response = requests.get(image_url, stream=True)
    if response.status_code != 200:
        print(f"❌ 이미지 다운로드 실패: {image_url}")
        return None

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    temp_file.write(response.content)
    temp_file.flush()
    temp_file.close()

    return temp_file.name  # ✅ 로컬 파일 경로 반환

#  이미지 병합 함수 (병합 후 OCR 정확도 향상)
def merge_images(image_paths):
    """
     여러 개의 이미지를 하나로 병합 (세로로 붙이기)
    """
    images = [Image.open(img) for img in image_paths]
    total_height = sum(img.height for img in images)
    max_width = max(img.width for img in images)

    merged_image = Image.new("RGB", (max_width, total_height))
    y_offset = 0

    for img in images:
        merged_image.paste(img, (0, y_offset))
        y_offset += img.height

    return merged_image

def save_ocr_json(text: str, output_file: str) -> str:
    try:
        text = text.strip().replace("```json", "").replace("```", "")  # 🔹 불필요한 JSON 래퍼 제거
        data = json.loads(text)  # 🔹 JSON 변환

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)  # 🔹 JSON 저장
        print(f"✅ JSON 결과 저장 완료: {output_file}")
        return output_file  # 🔹 저장된 JSON 파일 경로 반환

    except json.JSONDecodeError as e:
        print(f"❌ JSON 변환 실패: {e}")
        return ""

# ✅ 3️⃣ 병합된 이미지를 로컬에 저장하는 함수
def save_merged_image(merged_image):
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    merged_image.save(temp_file.name, format="JPEG")
    return temp_file.name  # ✅ 저장된 로컬 파일 경로 반환

# Clova OCR 호출 (1차 OCR)
def first_building_ocr(image_path, doc_type):
    """
     네이버 Clova OCR을 사용하여 텍스트 및 바운딩 박스 좌표 추출
    """
    request_json = {
        'images': [{'format': 'jpg', 'name': doc_type}],
        'requestId': str(uuid.uuid4()),
        'version': 'V2',
        'timestamp': int(round(time.time() * 1000))
    }

    with open(image_path, "rb") as image_file:
        image_bytes = image_file.read()

    payload = {'message': json.dumps(request_json).encode('UTF-8')}
    files = [('file', ('image.jpg', image_bytes, 'image/jpeg'))]
    headers = {'X-OCR-SECRET': OCR_SECRET_KEY}

    response = requests.post(OCR_API_URL, headers=headers, data=payload, files=files)

    if response.status_code == 200:
        ocr_results = response.json()
        all_data = []

        for image_result in ocr_results.get('images', []):
            for field in image_result.get('fields', []):
                text = field['inferText']
                bounding_box = field['boundingPoly']['vertices']
                x1, y1 = int(bounding_box[0]['x']), int(bounding_box[0]['y'])
                x2, y2 = int(bounding_box[2]['x']), int(bounding_box[2]['y'])
                all_data.append({"Text": text, "x1": x1, "y1": y1, "x2": x2, "y2": y2})

        return pd.DataFrame(all_data)

    print(f"❌ OCR 실패: {response.status_code}, {response.text}")
    return pd.DataFrame()


# ✅ 4️⃣ OCR 및 GPT 분석 실행 (Firebase에서 문서별로 실행)
def building_keyword_ocr(image_urls, doc_type):
    """
    ✅ Firestore에서 가져온 이미지 URL을 OCR에 넣고, 2차 GPT 분석까지 수행하는 함수
    """
    all_text_data = []

    # ✅ 1️⃣ Firebase에서 이미지 다운로드 (중복 호출 제거)
    image_paths = []
    for url in image_urls:
        img_path = download_image(url)
        if img_path:
            image_paths.append(img_path)
    
    if not image_paths:
        print("❌ 다운로드된 이미지가 없습니다.")
        return []
    
    # ✅ 2️⃣ 여러 개의 이미지 병합
    merged_image = merge_images(image_paths)

    # ✅ 3️⃣ 병합된 이미지 로컬에 저장 후 OCR 실행
    merged_image_path = save_merged_image(merged_image)  # ✅ 병합된 이미지 저장 후 경로 가져오기
    ocr_data = first_building_ocr(merged_image_path, doc_type)
    os.remove(merged_image_path)

    # 다운로드한 개별 이미지 삭제
    for img_path in image_paths:
        os.remove(img_path)

    if ocr_data.empty:
        print(f"❌ OCR 결과가 없음: {image_urls}")
        return []

    df_json = ocr_data.to_json(orient="records", force_ascii=False)

    # ✅ 5️⃣ GPT 분석 (2차 OCR)
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"다음은 OCR 분석을 위한 데이터입니다.\n\n"
                        f"✅ **내용 데이터 (df):**\n{df_json}\n\n"
                        f"💡 **작업 목표:**\n"
                        f"내용 데이터(df)를 이용하여 '표제부', '갑구', '을구' 위치 찾기.\n"
                        f"- 각 단어들은 일정 간격으로 연결되어 있습니다.\n"
                        f"- 그림에서 글자 안에 '-' 선이 있으면 말소 사항이므로 제외해야 합니다.\n"
                        f"\n\n🎯 **결과 형식:**\n"
                        f"- JSON 형식으로 반환 (각 항목의 바운딩 박스 포함)\n"
                        f"- **출력 데이터가 지정된 형식과 다를 경우 자동으로 변환하여 반환**\n\n"
                        f"💡 **반환 예시:**\n"
                        f"{{\n"
                        f"  \"표제부_1\": {{\"text\": \"표제부\", \"bounding_box\": {{\"x1\": 100, \"y1\": 200, \"x2\": 300, \"y2\": 250}}}},\n"
                        f"  \"표제부_2\": {{\"text\": \"표제부\", \"bounding_box\": {{\"x1\": 120, \"y1\": 220, \"x2\": 320, \"y2\": 270}}}},\n"
                        f"  \"갑구\": {{\"text\": \"갑구\", \"bounding_box\": {{\"x1\": 140, \"y1\": 240, \"x2\": 340, \"y2\": 290}}}},\n"
                        f"  \"을구\": {{\"text\": \"을구\", \"bounding_box\": {{\"x1\": 150, \"y1\": 250, \"x2\": 350, \"y2\": 300}}}}\n"
                        f"}}\n\n"
                        f"⚠️ **주의사항:**\n"
                        f"- `표제부_2`는 없을 수도 있습니다.\n"
                        f"- 내용이 없을 경우 `NA`로 반환합니다.\n"
                        f"- JSON 형식이 정확하도록 반환해야 합니다.\n"
                        f"- 반환 내용 외의 경고, 알림은 포함하지 마세요.\n"
                        f"- '아래는 제공된 데이터를 사용하여 각 항목을 분석한 결과입니다'와 같은 문장은 포함하지 마세요.\n"
                    )
                }
            ]
        }
    ]

    # ✅ 6️⃣ 첫 번째 이미지 URL 추가 (비어 있으면 추가 X)
    first_image_url = image_urls[0] if image_urls else None
    if first_image_url:
        messages[0]["content"].append({"type": "image_url", "image_url": {"url": first_image_url}})

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=5000
    )

    gpt_keywords = response.choices[0].message.content.strip() if response.choices else "{}"

    ocr_result = {
        "image_urls": image_urls,
        "ocr_texts": ocr_data.to_dict(orient="records"), #좌표값
        "gpt_keywords": gpt_keywords
    }

    # ✅ 6️⃣ OCR 및 GPT 분석 결과 저장
    all_text_data.append(ocr_result) # 혹시 필요할 수 있으니 

    # ✅ 8️⃣ OCR 결과 JSON 파일로 저장
    output_file = f"ocr_result_{doc_type}.json"  # ✅ 문서 유형별 저장
    return save_ocr_json(json.dumps(ocr_result, ensure_ascii=False, indent=4), output_file)





# 실행 함수 (Firebase에서 가져와 실행)
##def request(firebase_document_data):
    """
    🔥 Firestore에서 가져온 문서들을 OCR 및 GPT 분석 수행
    """
    all_results = {
        "contract": building_keyword_ocr(firebase_document_data.get("contract", []), "contract"),
        "registry_document": building_keyword_ocr(firebase_document_data.get("registry_document", []), "registry_document"),
        "building_registry": building_keyword_ocr(firebase_document_data.get("building_registry", []), "building_registry"),
    }

    output_path = "./ocr_gpt_results.json"
    save_ocr_results(all_results, output_path)


# 🚀 **실행 예시**
# request(classified_documents)  # Firestore에서 받은 문서를 인자로 전달
