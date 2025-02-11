# OCR 및 GPT 분석을 위한 데이터 처리 코드 포함
import openai
import os
import base64
import pandas as pd
import requests
import json
import uuid
import time
import re
from dotenv import load_dotenv
import re  

key='WVJnTm1OV2pZZVRvTlluYmlLS1lSbUlZQk5jcUxDZWw=' #네이버 key
url = 'https://tx6el9d54v.apigw.ntruss.com/custom/v1/38205/dffe650f3889e1adfe8a87fb4e7dd5e5f7b15247b02996892d2e319bd8000d1c/general' #네이버


load_dotenv()
#  OpenAI API 키
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

#  네이버 OCR API 키 및 URL
OCR_SECRET_KEY = os.getenv("OCR_SECRET_KEY")
OCR_API_URL = os.getenv("OCR_API_URL")

#  OCR 결과 JSON 저장 경로
OUTPUT_JSON_PATH = os.getenv("OUTPUT_JSON_PATH")
client = openai.OpenAI(api_key=OPENAI_API_KEY)

if not OPENAI_API_KEY:
    raise ValueError("ERROR: OPENAI_API_KEY가 로드되지 않았습니다!")


def read_file(file_path = "/home/brian/jibsin/jibsinpj/ai_processing/p_1.txt"):
    global content
    with open(file_path, "r", encoding="utf-8") as file:
        content = file.read()
    return content

# 네이버 OCR API 호출하여 텍스트 및 Bounding Box 가져오기
def read_ocr(secret_key,api_url,image_file):
    request_json = {
        'images': [
            {
                'format': 'jpg',
                'name': 'demo'
            }
        ],
        'requestId': str(uuid.uuid4()),
        'version': 'V2',
        'timestamp': int(round(time.time() * 1000))
    }

    payload = {'message': json.dumps(request_json).encode('UTF-8')}
    files = [('file', open(image_file, 'rb'))]
    headers = {'X-OCR-SECRET': secret_key}

    response = requests.post(api_url, headers=headers, data=payload, files=files)

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
        return all_data
    

def read_image(client,image_path, MODEL, df):
    content=read_file()

    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode("utf-8")

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": "출력은 요청 정보만 [':',':']의 딕셔너리 형태로 출력해줘"
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{df}는 주어진 이미지의 ocr 데이터야. {content}"},
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
    print(text)

MODEL = "gpt-4o"
image_path = "ai_processing/건축물대장.jpg"
df = read_ocr(key, url, image_path)
read_image(client, image_path, MODEL, df)

# OCR 결과 JSON 형식 불용어 정리
def fix_json_format(text: str) -> str:
    # JSON 형식 오류를 자동으로 수정하는 함수.

        text = text.replace("```json", "").replace("```", "").strip()  # 코드 블록 제거
        text = re.sub(r'(\d{1,3}),(\d{3})', r'\1\2', text)  # 숫자 쉼표 제거 (예: "1,000" -> "1000")
        text = re.sub(r'(\d{3})"(\d{3})', r'\1,\2', text)  # 잘못된 따옴표 쉼표 수정 (예: "100"000" -> "100,000")
        text = re.sub(r'"text":\s*"([^"]*?)"(\d+)"', r'"text": "\1\2"', text)  # 숫자 주변 잘못된 따옴표 제거
        text = text.replace('""', '"')  # 이중 따옴표 제거 (예: ""text"" -> "text")
        return text

#  OCR 결과 JSON 데이터를 정리하고 저장하는 함수 (형수님이 짜신)
def ttj(text: str, output_file: str) -> str:
    
    try:
        text = fix_json_format(text)  # JSON 형식 자동 수정
        data = json.loads(text)  # JSON 변환

        def fix_text(value):
            if value == "NA":
                return value
            value = re.sub(r'(\d+)\s+(\d+)', r'\1,\2', value)  # 숫자 사이 공백을 콤마로 변환
            return value.strip()

        for key, value in data.items():
            if isinstance(value, dict) and "text" in value:
                value["text"] = fix_text(value["text"])

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        return output_file

    except json.JSONDecodeError as e:
        return f" JSON 변환 실패: {e}"
    
# OCR 결과 JSON 데이터를 정리하고 저장하는 함수(gpt가 짠)
def save_cleaned_json(ocr_data, output_file):
    
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(ocr_data, f, ensure_ascii=False, indent=4)
        return output_file
    except json.JSONDecodeError as e:
        return f" JSON 변환 실패: {e}"
    
if __name__ == "__main__":
    image_path = "ai_processing/건축물대장.jpg"

    # OCR 수행
    ocr_result = read_ocr(OCR_SECRET_KEY, OCR_API_URL, image_path)
    print(" OCR 결과:", ocr_result)

    # OCR 결과를 JSON 파일로 저장
    saved_json_path = save_cleaned_json(ocr_result, OUTPUT_JSON_PATH)
    print(f" OCR 결과 저장 완료: {saved_json_path}") 


    