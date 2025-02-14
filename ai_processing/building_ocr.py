import openai
import os
import base64
import pandas as pd
import requests
import json
import uuid
import time
import re
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# API 설정
secret_key = os.getenv("OCR_SECRET_KEY")
api_url = os.getenv("OCR_API_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4o"

client = openai.OpenAI(api_key=OPENAI_API_KEY)

def building_first_ocr(secret_key, api_url, image_data):
    """이미지 데이터에서 OCR 실행"""
    request_json = {
        'images': [{'format': 'jpg', 'name': 'demo'}],
        'requestId': str(uuid.uuid4()),
        'version': 'V2',
        'timestamp': int(round(time.time() * 1000))
    }
    #이미지 처리
    image = Image.open(BytesIO(image_data))
    output_buffer = BytesIO()
    image.save(output_buffer, format='JPEG', quality=95)
    output_buffer.seek(0)
    jpeg_data = output_buffer.getvalue()

    payload = {'message': json.dumps(request_json).encode('UTF-8')}
    files = [('file', ('image.jpg', image_data, 'image/jpeg'))]
    headers = {'X-OCR-SECRET': secret_key}

    response = requests.post(api_url, headers=headers, data=payload, files=files)

    if response.status_code == 200:
        ocr_results = response.json()

        print("OCR Response:", ocr_results) # 응답 구조 확인

        all_data = []
        for image_result in ocr_results.get('images', []):
            for field in image_result.get('fields', []):
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
        return df
    else:
        print(f"OCR Error Response: {response.text}")
        raise ValueError(f"❌ OCR 요청 실패: {response.status_code} - {response.text}")

def fix_json_format(text: str) -> str:
    text = text.replace("```json", "").replace("```", "").strip()
    text = re.sub(r'(\d{1,3}),(\d{3})', r'\1\2', text)
    return text

def save_json(text: str, output_file: str) -> str:
    try:
        text = fix_json_format(text)
        data = json.loads(text)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        return output_file
    except json.JSONDecodeError as e:
        return f"❌ JSON 변환 실패: {e}"

def building_keyword_ocr(image_urls, doc_type):
    """Firebase URL에서 건축물대장 OCR 처리"""
    all_results = {}
    
    for image_url in image_urls:
        # URL에서 이미지 다운로드
        response = requests.get(image_url)
        if response.status_code != 200:
            continue
            
        image_data = response.content
        
        # 1차 OCR 실행
        try:
            df = building_first_ocr(secret_key=secret_key, api_url=api_url, image_data=image_data)
            if df.empty:
                continue
        except Exception as e:
            print(f"OCR 처리 중 오류 발생: {e}")
            continue

        # 2차 GPT 분석
        base64_image = base64.b64encode(image_data).decode("utf-8")
        df_json = json.dumps(df.to_dict(orient="records"), ensure_ascii=False)
        
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "user", "content": "출력은 요청 정보만 {'key': 'value'} 형태의 딕셔너리로 출력해줘"},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"다음은 OCR 분석을 위한 데이터입니다.\n\n"
                                f"✅ **OCR 데이터 (df_json):**\n{json.dumps(df_json, ensure_ascii=False)}\n\n"
                                f"💡 **목표:**\n"
                            f"주어진 문서에서 다음 정보를 정확하게 추출하세요:\n"
                            f"1️⃣ **건축물대장**\n"
                            f"2️⃣ **대지위치**\n"
                            f"3️⃣ **위반건축물** (건축물대장 옆에 있으며, OCR 데이터에서 없으면 'NA'로 처리하며, 좌표값은 {json.dumps({'x1': 0, 'y1': 0, 'x2': 0, 'y2': 0})} 으로 설정)\n"
                            f"4️⃣ **소유자현황** (소유자의 **성명과 주소를 각각 다른 바운딩 박스로 반환해야 함**)\n\n"

                            f"📌 **출력 규칙:**\n"
                            f"- 반드시 `{{'key': 'value'}}` 형태의 **JSON 형식**으로 출력하세요.\n"
                            f"- OCR 데이터에서 **각 정보(성명, 주소)의 바운딩 박스(`bounding_box`)를 각각 포함**해야 합니다.\n"
                            f"- 값이 존재하지 않는 경우 `'text': 'NA'`를 반환하세요.\n\n"

                            f"🔹 **출력 형식 예시:**\n"
                            f"```json\n"
                            f"{{\n"
                            f"  \"건축물대장\": {{\n"
                            f"    \"text\": \"집합건축물대장(전유부,갑)\",\n"
                            f"    \"bounding_box\": {{ \"x1\": 379, \"y1\": 62, \"x2\": 595, \"y2\": 86 }}\n"
                            f"  }},\n"
                            f"  \"대지위치\": {{\n"
                            f"    \"text\": \"서울특별시 서대문구 창천동\",\n"
                            f"    \"bounding_box\": {{ \"x1\": 273, \"y1\": 134, \"x2\": 394, \"y2\": 147 }}\n"
                            f"  }},\n"
                            f"  \"위반건축물\": {{\n"
                            f"    \"text\": \"NA\",\n"
                            f"    \"bounding_box\": {json.dumps({'x1': 0, 'y1': 0, 'x2': 0, 'y2': 0})}\n"
                            f"  }},\n"
                            f"   \"성명\": {{\n"
                            f"     \"text\": \"김나연\",\n"
                            f"     \"bounding_box\": {{ \"x1\": 528, \"y1\": 252, \"x2\": 561, \"y2\": 267 }}\n"
                            f"  }},\n"
                            f"   \"주소\": {{\n"
                            f"      \"text\": \"서울특별시 강남구 테헤란로 123\",\n"
                            f"      \"bounding_box\": {{ \"x1\": 500, \"y1\": 400, \"x2\": 750, \"y2\": 430 }}\n"
                            f"  }}\n"
                            f"}}\n"
                            f"```\n\n"

                            f"⚠️ **주의사항:**\n"
                            f"- JSON 형식을 반드시 준수하세요.\n"
                            f"- OCR 좌표 정보를 포함해야 합니다.\n"
                            f"- 성명과 주소는 **각각 다른 바운딩 박스**에 저장해야 합니다.\n"
                            f"- 추가적인 설명 없이 JSON 형태만 출력하세요."
                            )
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                        }
                    ]
                }
            ],
            max_tokens=1000
        )

        text = response.choices[0].message.content
        output_file = f"ocr_result_{doc_type}.json"
        return save_json(text, output_file)

    return None