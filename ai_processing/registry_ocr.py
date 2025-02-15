import time
import pandas as pd
import cv2
import json
from PIL import Image
import requests
import uuid
import time
import openai
import re
import base64
import numpy as np
import os
from io import BytesIO
from dotenv import load_dotenv
from firebase_api.utils import save_ocr_result_to_firestore

load_dotenv()

# API 설정
secret_key = os.getenv("OCR_SECRET_KEY")
api_url = os.getenv("OCR_API_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4o" # 일단 클로드가 버전 바꾸라해서 바꾸는데 나중에 문제생기면 4-o로

client = openai.OpenAI(api_key=OPENAI_API_KEY)
#계약서원본양식
def registry_xy_mapping():
    rows = [
        ['등기사항전부증명서',348,112,934,162],
        ['집합건물',520,166,766,216],
        ['[집합건물] 건물주소',26,298,908,346],
        ['[표제부](1동의 건물의 표시)',94,354,632,392],
        ['표시번호',34,406,130,444],
        ['접수',172,414,268,440],
        ['소재지번, 건물 명칭 및 번호', 318,410,590,440],
        ['([도로명주소])',312,456,580,642],
        ['건물내역',668,410,808,446],
        ['등기 원인 및 기타사항',904,404,1140,448],
        ['열람일시',22,1620,456,1656],
        ['(대지권이 목적인 토지의 표시)',408,2456,788,2496],
        ['[표제부] (전유부분의 건물의 표시)',80,2672,684,2720],
        ['표시번호',40,2740,130,2776],
        ['접수',166,2732,280,2776],
        ['건물번호',322,2732,480,2780],
        ['(건물번호)',316,2784,490,2842],
        ['건물내역',522,2742,694,2770],
        ['(건물내역)',506,2790,706,2850],
        ['등기원인 및 기타사항',806,2736,1064,2772],
        ['[갑 구] (소유권에 관한 사항)',86,3842,654,3898],
        ['순위번호',46,3908,134,3948],
        ['등기목적',170,3910,314,3944],
        ['접수', 390,3904,490,3946],
        ['등기원인',524,3906,668,3952],
        ['관리자 및 기타사항',824,3902,1030,3946],
        ['(갑구)',38,3902,1156,4526],
        ['[을 구] (소유권 이외의 권리에 대한 사항)', 88,4562,796,4608],
        ['순위번호',46,4628,134,4658],
        ['등기목적',170,4628,314,4658],
        ['접수', 390,4628,490,4658],
        ['등기원인',524,4628,668,4658],
        ['관리자 및 기타사항',824,4628,1030,4658],
        ['(채권최고액)',718,4662,1156,4752]
    ]
    xy = pd.DataFrame(columns=['Text', 'x1', 'y1', 'x2', 'y2'])
    xy = pd.concat([xy, pd.DataFrame(rows, columns=xy.columns)], ignore_index=True)
    return xy

def merge_images(image_urls):
    """Firebase URL로부터 이미지를 다운로드하고 병합"""
    target_size = (1240, 1755)  # 원하는 이미지 크기

    # 이미지 불러와 크기 조정
    images = []
    for url in image_urls:
        # URL에서 이미지 다운로드
        response = requests.get(url)
        if response.status_code == 200:
            # 바이트 데이터를 이미지로 변환
            image = Image.open(BytesIO(response.content))
            # PIL Image를 OpenCV 형식으로 변환
            opencv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            # 크기 조정
            resized_image = cv2.resize(opencv_image, target_size, interpolation=cv2.INTER_AREA)
            # 다시 PIL Image로 변환
            images.append(Image.fromarray(cv2.cvtColor(resized_image, cv2.COLOR_BGR2RGB)))
    
    total_height = sum(img.height for img in images)
    max_width = max(img.width for img in images)

    merged_image = Image.new("RGB", (max_width, total_height))

    # 이미지 붙이기
    y_offset = 0
    for img in images:
        merged_image.paste(img, (0, y_offset))
        y_offset += img.height
    
    # 병합된 이미지 저장
    merged_image.save("merged_registry_image.jpg")
    
    return merged_image

def cre_ocr(image):
    """PIL Image 객체에 대해 OCR 실행"""
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
    
    # 이미지를 바이트 버퍼로 변환
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    image_bytes = buffer.getvalue()
    
    payload = {'message': json.dumps(request_json).encode('UTF-8')}
    files = [('file', ('image.jpg', image_bytes, 'image/jpeg'))]
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
        return df
    return None

def fix_json_format(text: str) -> str:
    """JSON 형식 오류를 자동으로 수정하는 함수"""
    text = text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    
    json_end_index = text.rfind("}")
    if json_end_index != -1:
        text = text[:json_end_index+1]
    
    text = re.sub(r'}\s*{', '}, {', text)
    text = re.sub(r'(\d{1,3})(\d{3},\d{3})', r'\1,\2', text)
    
    return text

def format_registry_json(text: str, output_file: str) -> str:
    """OCR 결과 JSON 데이터를 정리하고 저장하는 함수"""
    try:
        text = fix_json_format(text)
        data = json.loads(text)

        def fix_text(value):
            if value == "NA":
                return value
            value = re.sub(r'(\d+)\s+(\d+)', r'\1,\2', value)
            return value.strip()

        for key, value in data.items():
            if isinstance(value, dict) and "text" in value:
                value["text"] = fix_text(value["text"])

        y1_value = data.get("(소유권에 관한 사항)", {}).get("bounding_box", {}).get("y2", 0)
        y2_value = data.get("(소유권 이외의 권리에 관한 사항)", {}).get("bounding_box", {}).get("y1", 0)

        data["갑구"] = {
            "text": "(갑구)",
            "bounding_box": {
                "x1": 0,
                "y1": y1_value,
                "x2": 1200,
                "y2": y2_value
            }
        }

        # "(소유권에 관한 사항)"과 "(소유권 이외의 권리에 관한 사항)"을 삭제
        data.pop("(소유권에 관한 사항)", None)
        data.pop("(소유권 이외의 권리에 관한 사항)", None)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        print(f"✅ 등기부등본 JSON 정리 완료: {output_file}")
        return output_file

    except json.JSONDecodeError as e:
        print(f"❌ JSON 변환 실패: {e}")
        print("📌 오류 발생 JSON 내용:\n", text)
        return f"❌ JSON 변환 실패: {e}"

def registry_keyword_ocr(image_urls, doc_type):
    """메인 OCR 처리 함수"""
    # 이미지 병합
    merged_image = merge_images(image_urls)
    
    # OCR 수행
    df = cre_ocr(merged_image)
    
    if df is None:
        print("OCR 처리 실패")
        return None

    xy = registry_xy_mapping()
    xy_json = xy.to_json(orient="records", force_ascii=False)
    df_json = df.to_json(orient="records", force_ascii=False)

    target_texts = {
        "종류": "등본 종류 (집합건물, 건물, 토지 중 하나)",
        "(건물주소)": "[등본종류] 도로명 주소 (예: [집합건물] 정왕대로 53번길 29)",
        "(갑구)":"텍스트",
        "(소유권에 관한 사항)": "(소유권에 관한 사항)",
        "(소유권 이외의 권리에 대한 사항)":"(소유권 이외의 권리에 대한 사항)",
        "(채권최고액)": "최고채권액 금 ###원(예: 채권최고액 금1,000,000,000원)"
    }
    
    
    # GPT 분석 요청
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "JSON 형식으로만 응답하세요. 설명이나 마크다운은 포함하지 마세요."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"다음은 OCR 분석을 위한 데이터입니다.\n\n"
                            f"✅ **위치 데이터 (xy):**\n{xy_json}\n\n"
                            f"✅ **내용 데이터 (df):**\n{df_json}\n\n"
                            f"💡 **작업 목표:**\n"
                            f"- 등기부등본에서 **건물 주소, 갑구(소유권), 을구(권리 사항)** 정보를 추출\n"
                            f"- 내용이 없으면 'NA'로 표시\n\n"
                            f"📌 **출력 형식:**\n"
                            f"```json\n"
                            f"{{\n"
                            f"  \"건물주소\": {{ \"text\": \"서울특별시 강남구 테헤란로 123\", \"bounding_box\": {{ \"x1\": 120, \"y1\": 220, \"x2\": 320, \"y2\": 270 }} }},\n"
                            f"  \"갑구\": {{ \"text\": \"(갑구) 소유권 관련 내용\", \"bounding_box\": {{ \"x1\": 86, \"y1\": 3842, \"x2\": 654, \"y2\": 3898 }} }},\n"
                            f"  \"을구\": {{ \"text\": \"(을구) 권리 사항 내용\", \"bounding_box\": {{ \"x1\": 88, \"y1\": 4562, \"x2\": 796, \"y2\": 4608 }} }}\n"
                            f"}}\n"
                            f"```"
                        )
                    }
                ]
            }
        ],
        max_tokens=5000,
        temperature=0.2,
        top_p=1.0
    )

    # 응답 처리
    text = response.choices[0].message.content.strip()
    output_path = f"./ocr_results_registry.json"
    
    return format_registry_json(text, output_path)