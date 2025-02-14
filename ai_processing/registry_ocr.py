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
        print(f" 이미지 다운로드 실패: {image_url}")
        return None

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    temp_file.write(response.content)
    temp_file.flush()
    temp_file.close()

    return temp_file.name  # ✅ 로컬 파일 경로 반환

#  이미지 병합 함수 (병합 후 OCR 정확도 향상)
def merge_images(image_urls):
    """
     여러 개의 이미지를 하나로 병합 (세로로 붙이기)
    """
    images = [Image.open(img) for img in image_urls]
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
        print(f" JSON 변환 실패: {e}")
        return ""

# ✅ 3️⃣ 병합된 이미지를 로컬에 저장하는 함수
def save_merged_image(merged_image):
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    merged_image.save(temp_file.name, format="JPEG")
    return temp_file.name  # ✅ 저장된 로컬 파일 경로 반환

# Clova OCR 호출 (1차 OCR)
def first_registry_ocr(image_path, doc_type):
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
        
        output_file = f"./ocr_results_{doc_type}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=4)
        
        print(f"✅ 1차 OCR 결과 저장 완료: {output_file}")
        return output_file  # JSON 파일 경로 반환

    print(f"❌ OCR 실패: {response.status_code}, {response.text}")
    return None


#  OCR 및 GPT 분석 실행 (Firebase에서 문서별로 실행)
def registry_keyword_ocr(image_urls, doc_type):
    """
    Firestore에서 가져온 이미지 URL을 OCR에 넣고, 2차 GPT 분석까지 수행하는 함수
    """
    all_text_data = []

    #  Firebase에서 이미지 다운로드 (중복 호출 제거)
    image_paths = []
    for url in image_urls:
        img_path = download_image(url)
        if img_path:
            image_paths.append(img_path)
    
    if not image_paths:
        print(" 다운로드된 이미지가 없습니다.")
        return []
    
    #  여러 개의 이미지 병합
    merged_image = merge_images(image_paths)
    merged_image_path = save_merged_image(merged_image)  #  병합된 이미지 저장 후 경로 가져오기
    
    ocr_result_path = first_registry_ocr(merged_image_path, doc_type)
    if ocr_result_path and os.path.exists(ocr_result_path):
        with open(ocr_result_path, 'r', encoding='utf-8') as f:
            ocr_data = json.load(f)
    else:
        print(f" OCR 결과가 없음: {image_urls}")
        return []

    # cleanup
    os.remove(merged_image_path)
    for img_path in image_paths:
        os.remove(img_path)

    df_json = json.dumps(ocr_data, ensure_ascii=False)

    #  GPT 분석 (2차 OCR)
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"다음은 등기부등본 OCR 분석을 위한 데이터입니다.\n\n"
                        f" **내용 데이터 :**\n{df_json}\n\n"
                        f" **작업 목표:**\n"
                        f"등기부등본 데이터에서 다음 정보를 추출하여 정해진 형식으로 반환해주세요:\n"
                        f"1. 부동산의 표시:\n"
                        f"  - 소재지번\n"
                        f"  - 건물내역/구조\n"
                        f"  - 면적정보\n"
                        f"2. 소유권에 관한 사항:\n"
                        f"  - 등기원인\n"
                        f"  - 권리자정보\n"
                        f"  - 주소정보\n"
                        f"3. 기타 권리에 관한 사항:\n"
                        f"  - 채권최고액\n"
                        f"  - 채무자정보\n"
                        f"  - 근저당권자\n"
                        f"\n\n🎯 **결과 형식:**\n"
                        f"- JSON 형식으로 반환 (각 항목의 바운딩 박스 포함)\n"
                        f"- 모든 발견된 정보를 포함\n\n"
                        f" **반환 예시:**\n"
                        f"{{\n"
                        f"  \"소재지번\": {{\n"
                        f"    \"text\": \"경기도 성남시 분당구...\",\n"
                        f"    \"bounding_box\": {{\n"
                        f"      \"x1\": 값, \"y1\": 값, \"x2\": 값, \"y2\": 값\n"
                        f"    }}\n"
                        f"  }},\n"
                        f"  ... (발견된 다른 모든 정보)\n"
                        f"}}\n\n"
                        f" **주의사항:**\n"
                        f"- 찾을 수 없는 정보는 해당 필드를 생략\n"
                        f"- '-' 표시가 있는 말소사항은 제외\n"
                        f"- 모든 발견된 정보를 포함할 것\n"
                    )
                },
            ]
        }
    ]

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=5000
    )
    try:
        gpt_keywords = response.choices[0].message.content.strip() if response.choices else "{}"
        gpt_keywords = gpt_keywords.replace("```json", "").replace("```", "").strip()
        json.loads(gpt_keywords)
    except json.JSONDecodeError:
        print("GPT 응답이 JSON 형식이 아님! 원본 응답 출력:", response.choices[0].message.content)
        gpt_keywords = "{}"


    # OCR 결과 JSON 파일로 저장
    output_file = f"ocr_result_{doc_type}.json"  #  문서 유형별 저장
    return save_ocr_json(gpt_keywords, output_file)



