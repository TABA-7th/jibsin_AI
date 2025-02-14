import time
import pandas as pd
import cv2
import json
import requests
import uuid
import openai
import re
import os
import base64
import numpy as np
import tempfile
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

def base_xy():
    """계약서 양식의 기준 좌표값 설정"""
    rows = [
            ['1st',70,114,1208,238],
            ['2nd',70,244,1224,728],
            ['3rd',70,730,1222,1339],
            ['4th',58,1344,1194,1620],
            ['주택임대차표준계약서',396,119,838,173],
            ['임대인', 127, 193, 198, 221],
            ['(임대인)', 198, 193, 410, 221],
            ['임차인', 445, 193, 510, 221],
            ['(임차인)', 510, 193, 725, 221],
            ['소재지', 94, 291, 186, 319],
            ['(소재지)', 333, 289, 1203, 321],
            ['[임차주택의 표시]',70,244,302,282],
            ['토지',101,321,182,357],
            ['(토지)', 330,322,681,356],
            ['건물',103,357,183,388],
            ['(건물)',103,357,183,388],
            ['면적',712,322,764,355],
            ['(면적)',803,322,1179,358],
            ['계약기간',240,521,330,546],
            ['(계약기간)',336,518,620,548],
            ['보증금_1',633,523,697,547],
            ['(보증금_1)',691,520,861,548],
            ['차임_1', 878,521,927,547],
            ['(차임_1)',925,516,1113,549],
            ['계약내용',74,734,206,769],
            ['보증금_2',93,824,182,865],
            ['(보증금_2)',220,826,966,863],
            ['계약금',95,866,178,906],
            ['(계약금)',220,865,646,904],
            ['중도금',93,908,177,946],
            ['(중도금)', 217,907,1004,946],
            ['잔금',92,947,177,984],
            ['(잔금)',218,945,1012,984],
            ['차임(월세)',86,987,182,1028],
            ['(차임_2)',220,989,607,1023],
            ['입금계좌',722,990,809,1022],
            ['(입금계좌)', 806,995,1140,1021],
            ['(정액)',360,1026,1028,1069],
            ['(비정액)',408,1258,1197,1290],
            ['(임대일)',877,1344,1145,1378],
            ['(임대차기간)',554,1370,922,1401],
            ['수리필요시설',90,1479,254,1512],
            ['(수리할내용)',460,1473,1127,1512],
            ['(수리완료시기)',504,1514,841,1551],
            ['임대인부담', 73, 1968, 225, 2016],
            ['임차인부담', 75, 2022, 226, 2063],
            ['(임대인부담)', 228, 1967, 1202, 2017],
            ['(임차인부담)', 228, 2017, 1200, 2065],
            ['(중개보수)', 378, 2797, 814, 2833],
            ['(제 13조)', 50, 2885, 1202, 2947],
            ['(교부일)', 378, 2909, 766, 2945],
            ['특약사항', 56, 2987, 1188, 3411],
            ['특약',46,3534,1196,3672],
            ['(특약 이전)',46,3716,1184,3780],
            ['(계약일)',510,3742,1184,3780],
            ['임대인_주소', 98,3794,250,3840],
            ['(임대인_주소)',254,3796,1064,3844],
            ['임대인_주민등록번호',110,3844,242,3892],
            ['(임대인_주민등록번호)',256,3842,564,3894],
            ['임대인_전화',560,3840,692,3892],
            ['(임대인_전화)',690,3844,854,3894],
            ['(성명)',930,3846,1066,3896],
            ['성명', 860,3848,926,3886],
            ['임대인_대리인_주소',258,3896,326,3940],
            ['임대인_대리인_주소', 330,3898,562,3944],
            ['임대인_대리인_주민등록번호',564,3894,690,3944],
            ['(임대인_대리인_주민등록번호)',694,3896,858,3944],
            ['임대인_대리인_성명',862,3898,922,3940],
            ['(임대인_대리인_성명)',932,3896,1064,3944],
            ['임차인_주소',110,3948,246,3994],
            ['(임차인_주소)',254,3948+154,1064,3996+154],
            ['임차인_주민등록번호',110,3996+154,242,4044+154],
            ['(임차인_주민등록번호)',256,3994+154,564,4046+154],
            ['임차인_전화',560,3992+154,692,4044+154],
            ['(임차인_전화)',690,3996+154,854,4046+154],
            ['(임차인_성명)',930,3998+154,1066,4048+154],
            ['임차인_성명', 860,4000+154,926,4038+154],
            ['임차인_대리인_주소',258,4004+154,326,4048+154],
            ['임차인_대리인_주소', 330,4006+154,562,4052+154],
            ['임차인_대리인_주민등록번호',564,4002+154,690,4052+154],
            ['(임차인_대리인_주민등록번호)',694,4004+154,858,4052+154],
            ['임차인_대리인_성명',862,4006+154,922,4048+154],
            ['(임차인_대리인_성명)',932,4004+154,1064,4052+154],
            ['사무소소재지_1',110,4108,242,4150],
            ['(사무소소재지_1)',256,4104,562,4152],
            ['사무소명칭_1',122,4152,236,4194],
            ['(사무소명칭_1)',254,4150,562,4200],
            ['사무소소재지_2',586,4102,712,4150],
            ['(사무소소재지_2)',740,4104,1176,4154],
            ['사무소명칭_2',594,4150,710,4198],
            ['(사무소명칭_2)',740,4150,1180,4204]
        ]
    xy = pd.DataFrame(columns=['Text', 'x1', 'y1', 'x2', 'y2'])
    xy = pd.concat([xy, pd.DataFrame(rows, columns=xy.columns)], ignore_index=True)
    return xy

def merge_images(image_urls):
    """Firebase URL로부터 이미지를 다운로드하고 병합"""
    target_size = (1240, 1753)
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
    
    y_offset = 0
    for img in images:
        merged_image.paste(img, (0, y_offset))
        y_offset += img.height
    
    return merged_image

def cre_ocr(image):
    """병합된 이미지에 대해 OCR 실행"""
    request_json = {
        'images': [{'format': 'jpg', 'name': 'demo'}],
        'requestId': str(uuid.uuid4()),
        'version': 'V2',
        'timestamp': int(round(time.time() * 1000))
    }
    
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
        for image_result in ocr_results.get('images', []):
            for field in image_result.get('fields', []):
                text = field['inferText']
                bounding_box = field['boundingPoly']['vertices']
                x1, y1 = int(bounding_box[0]['x']), int(bounding_box[0]['y'])
                x2, y2 = int(bounding_box[2]['x']), int(bounding_box[2]['y'])
                all_data.append({"Text": text, "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        return pd.DataFrame(all_data)
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

def ttj(text: str, output_file: str) -> str:
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

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        return output_file

    except json.JSONDecodeError as e:
        print(f"❌ JSON 변환 실패: {e}")
        print("📌 오류 발생 JSON 내용:\n", text)
        return f"❌ JSON 변환 실패: {e}"

def contract_keyword_ocr(image_urls, doc_type):
    """Firebase URLs에서 계약서 OCR 처리"""
    merged_image = merge_images(image_urls)
    df = cre_ocr(merged_image)
    
    if df is None:
        print(" OCR 처리 실패")
        return ""
        
    xy = base_xy()
    xy_json = xy.to_json(orient="records", force_ascii=False)
    df_json = df.to_json(orient="records", force_ascii=False)
    
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
                            f"- 겹치는 단어들을 묶어 최종 바운딩 박스를 생성\n"
                            f"- 내용이 없으면 'NA'로 표시\n\n"
                            # ... (나머지 프롬프트 내용)
                        )
                    }
                ]
            }
        ],
        max_tokens=5000
    )
    
    text = response.choices[0].message.content.strip()
    return ttj(text, f"ocr_result_{doc_type}.json")

def run_contract_ocr(firebase_document_data):
    """Firestore에서 가져온 문서들을 OCR 실행"""
    results = {
        "contract": contract_keyword_ocr(firebase_document_data.get("contract", []), "contract")}