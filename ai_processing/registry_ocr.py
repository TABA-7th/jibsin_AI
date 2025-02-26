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
def base_xy():
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
        ['관리자 및 기타사항', 824,3902,1030,3946],
        ['소유자', 824,3902,1030,4462],
        ['[을 구] (소유권 이외의 권리에 대한 사항)', 88,4562,796,4608],
        ['순위번호',46,4628,134,4658],
        ['등기목적',170,4628,314,4658],
        ['접수', 390,4628,490,4658],
        ['등기원인',524,4628,668,4658],
        ['관리자 및 기타사항',824,4628,1030,4658],
        ['(채권최고액)',718,4662,1156,4752],
        ['이하여백',410,4952,689,4990]
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
    
    # 이미지 병합
    total_height = sum(img.height for img in images)
    max_width = max(img.width for img in images)
    merged_image = Image.new("RGB", (max_width, total_height))

    # 이미지 붙이기
    y_offset = 0
    for img in images:
        merged_image.paste(img, (0, y_offset))
        y_offset += img.height
    
    return merged_image

# def get_page_of_text(y_coordinate, page_count):
#     """
#     y 좌표를 기준으로 어떤 페이지에 있는지 판단하는 함수
    
#     :param y_coordinate: 텍스트의 y 좌표
#     :param page_count: 전체 페이지 수
#     :return: 해당 텍스트가 있는 페이지 번호
#     """
#     page_height = 1755  # 각 페이지의 높이
    
#     for page in range(1, page_count + 1):
#         if (page - 1) * page_height <= y_coordinate < page * page_height:
#             return page
    
#     return 1  # 기본값으로 첫 페이지 반환

def get_page_height(url):
    """이미지 URL로부터 높이를 가져오는 함수"""
    response = requests.get(url)
    if response.status_code == 200:
        image = Image.open(BytesIO(response.content))
        return image.height
    return 1755  # 기본 높이

## 함수 추가가
def organize_by_pages(data, page_heights):
    """페이지별로 데이터를 구조화하고 좌표를 보정하는 함수"""
    
    # 페이지 경계 계산
    page_boundaries = []
    current_height = 0
    for height in page_heights:
        page_boundaries.append({
            'start': current_height,
            'end': current_height + height
        })
        current_height += height

    # 결과를 저장할 딕셔너리 초기화
    result = {f"{i+1}페이지": {} for i in range(len(page_heights))}
    
    # 각 항목을 해당하는 페이지에 할당
    for key, value in data.items():
        if isinstance(value, dict) and "bounding_box" in value:
            y1 = value["bounding_box"]["y1"]
            
            # y1 값이 어느 페이지 범위에 속하는지 확인
            for page_num, boundary in enumerate(page_boundaries):
                if boundary['start'] <= y1 < boundary['end']:
                    # 해당 페이지에 항목 추가
                    page_key = f"{page_num+1}페이지"
                    new_value = value.copy()
                    # y 좌표 보정
                    new_value["bounding_box"]["y1"] -= boundary['start']
                    new_value["bounding_box"]["y2"] -= boundary['start']
                    result[page_key][key] = new_value
                    break
    
    return result

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

def registry_keyword_ocr(image_urls, doc_type, user_id, contract_id):
    """메인 OCR 처리 함수"""

    page_numbers = [int(re.search(r'page(\d+)', url).group(1)) for url in image_urls]
    page_heights = []


    
    all_dfs = []
    y = 0
    
    # 각 페이지별 OCR 수행 및 높이 정보 수집
    for url in image_urls:
        response = requests.get(url)
        if response.status_code == 200:
            image = Image.open(BytesIO(response.content))
            page_heights.append(image.height)
            
            # 각 페이지별 OCR 수행
            df = cre_ocr(image)
            if df is not None:
                df["y1"] += y
                df["y2"] += y
                all_dfs.append(df)
                y += image.height
    
    merged_df = pd.concat(all_dfs, ignore_index=True)

    xy = base_xy()
    xy_json = xy.to_json(orient="records", force_ascii=False)
    df_json = merged_df.to_json(orient="records", force_ascii=False)

    # current_page = re.search(r'page(\d+)', image_urls[0]).group(1)
    # page_number = int(current_page)  # str을 int로 변환
    # page_count = len(image_urls)  # 전체 페이지 수

    target_texts = {
            "종류": "등본 종류 (집합건물, 건물, 토지 중 하나)",
            "(건물주소)": "[등본종류] 도로명 주소 (예: [집합건물] 정왕대로 53번길 29)",
            "열람일시": "yyyy년 mm월 dd일 hh시mm분ss초",
            "(갑구)":"텍스트",
            "(소유권에 관한 사항)": "(소유권에 관한 사항)",
            "소유자":"이름",
            "신탁":"신탁 (예: 신탁, 이외의 다른 단어가 있으면 안됨)",
            "압류":"압류 (예: 압류, 이외의 다른 단어가 있으면 안됨)",
            "가처분":"가처분 (예: 가처분, 이외의 다른 단어가 있으면 안됨)",
            "가압류":"가압류 (예: 가압류, 이외의 다른 단어가 있으면 안됨)",
            "(소유권 이외의 권리에 대한 사항)":"(소유권 이외의 권리에 대한 사항)",
            "(채권최고액)": "최고채권액 금 ###원(예: 채권최고액 금1,000,000,000원)",
            "이하여백": "이 하 여 백"
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
                            f"**위치 데이터 (xy):**\n{xy_json}\n\n"
                            f"**내용 데이터 (df):**\n{df_json}\n\n"
                            f"**작업 목표:**\n"
                            f"- 내용이 없으면 'NA'로 표시\n\n"
                            f"- `xy` 데이터의 위치 정보(좌표)를 활용하여 `df` 데이터와 매칭. {xy_json}의 위치는 참고만하고 항상 {df_json}을 따른다.\n"
                            f"- 'xy' 데이터의 바운딩 박스 크기는 'df'에 맞게 조정된다"
                            f" **각 항목의 출력 형식:**\n"
                            + "\n".join([f"- **{key}**: {value}" for key, value in target_texts.items()]) +
                            f"\n\n**결과 형식:**\n"
                            f"- JSON 형식으로 반환 (각 항목의 바운딩 박스 포함)\n"
                            f"- **출력 데이터가 지정된 형식과 다를 경우 자동으로 변환하여 반환**\n\n"
                            f"**반환 예시:**\n"
                            f"{{\n"
                            f"  \"종류\": {{\"text\": \"집합건물\", \"bounding_box\": {{\"x1\": 100, \"y1\": 200, \"x2\": 300, \"y2\": 250}}}},\n"
                            f"  \"건물주소\": {{\"text\": \"정왕대로 53번길 29\", \"bounding_box\": {{\"x1\": 120, \"y1\": 220, \"x2\": 320, \"y2\": 270}}}},\n"
                            f"  \"(소유권에 관한 사항)\": {{\"text\": \"( 소유권에 관한 사항 )\", \"bounding_box\": {{\"x1\": 120, \"y1\": 220, \"x2\": 320, \"y2\": 270}}}},\n"
                            f"  \"소유주\": {{\"text\": \"( 소유권에 관한 사항 )\", \"bounding_box\": {{\"x1\": 120, \"y1\": 220, \"x2\": 320, \"y2\": 270}}}},\n"
                            f"  \"(소유권 이외의 권리에 관한 사항)\": {{\"text\": \"(소유권 이외의 권리에 관한 사항)\", \"bounding_box\": {{\"x1\": 120, \"y1\": 220, \"x2\": 320, \"y2\": 270}}}},\n"                            
                            f"  \"열람일시\": {{\"text\": \"2025년 02월 15일 14시 48분\", \"bounding_box\": {{\"x1\": 150, \"y1\": 250, \"x2\": 350, \"y2\": 300}}}},\n"
                            f"  \"채권최고액\": {{\"text\": \"채권최고액 금1,000,000,000원\", \"bounding_box\": {{\"x1\": 170, \"y1\": 270, \"x2\": 370, \"y2\": 320}}}}\n"
                            f"}}\n\n"
                            f"**주의사항:**\n"
                            f"- 모든 좌표는 df를 기준으로 출력한다."
                            f"- df를 항상 우선시한다."
                            f"- 특약사항은 해당 페이지의 마지막 텍스트까지 포함한다."
                            f"- 텍스트가 여러 바운딩 박스에 걸쳐 있는 경우, 중심점 기준으로 판단\n"
                            f"- 내용이 없을 경우 `NA`로 반환, text 내용이 없는 경우 좌표를 0, 0, 0, 0으로 해줘.\n"
                            f"- df 기준으로 없는 내용을 추가하지 말것"
                            f"- 소유주는 '(소유권 이외의 권리에 관한 사항)'와 '(소유권에 관한 사항) 사이에 해당하는 모든 이름이다'"
                            f"- 소유주가 여러명인 경우 소유주_1, 소유주_2 의 형식으로 출력된다"
                            f"- 채권최고액은 '(소유권에 관한 사항)' 과 '이하여백' 사이에 해당하는 모든 금액이다."
                            f"- 채권최고액은 여러개인 경우 채권최고액_1, 채권최고액_2의 형식으로 출력된다."
                            f"- 채권최고액은 채권최고액_i 중 가장 i가 큰 것만을 출력한다."
                            f"- JSON 형식이 정확하도록 반환할 것!\n"
                            f"- JSON 형식 이외의 어떤 알림, 내용은 첨가하지 말것!\n"
                            f"- 반환 내용 외의 경고, 알림은 반환하지 말것\n"
                            f" '아래는 제공된 `xy` 및 `df` 데이터를 사용하여 각 항목을 분석한 결과입니다'와 같은 알림은 절대 금지\n"
                            f" OpenAI 응답내용금지\n"


                        )
                    }
                    ]
                }
            ],
            max_tokens=5000,
            temperature=0.2,
            top_p=1.0
        )
        
    text = response.choices[0].message.content.strip()
    data = json.loads(fix_json_format(text))

    # 불필요한 필드 제거
    data.pop("(소유권에 관한 사항)", None)
    data.pop("(소유권 이외의 권리에 대한 사항)", None)

    # 6. 페이지별 데이터 구조화
    organized_data = organize_by_pages(data, page_heights)


    # 7. 페이지 번호 형식 맞추기
    page_structured_data = {}
    for i, (old_key, value) in enumerate(organized_data.items()):
        new_key = f"page{page_numbers[i]}"
        page_structured_data[new_key] = value

    return page_structured_data

    

    # page_structured_data = {}
    
    # for key, value in data.items():
    #     if isinstance(value, dict) and "bounding_box" in value:
    #         # 원본 페이지 번호 기준으로 페이지 결정
    #         page_index = get_page_of_text(value["bounding_box"]["y1"], page_count)
    #         page_key = f"page{page_numbers[page_index - 1]}"
            
    #         # 페이지별 딕셔너리 초기화
    #         if page_key not in page_structured_data:
    #             page_structured_data[page_key] = {}
            
    #         # 해당 페이지에 데이터 추가
    #         page_structured_data[page_key][key] = value

    # 기존의 갑구 및 불필요한 필드 처리 로직
    # y1_value = data.get("(소유권에 관한 사항)", {}).get("bounding_box", {}).get("y2", "값 없음")
    # y2_value = data.get("(소유권 이외의 권리에 관한 사항)", {}).get("bounding_box", {}).get("y1", "값 없음")

    # if isinstance(y1_value, (int, float)) and isinstance(y2_value, (int, float)):
    #     # 갑구의 페이지 결정
    #     갑구_page_index = get_page_of_text(y1_value, page_count)
    #     page_key = f"page{page_numbers[갑구_page_index - 1]}"
    #     page_structured_data[page_key]["갑구"] = {
    #         "text": "(갑구)",
    #         "bounding_box": {
    #             "x1": 0,
    #             "y1": y1_value,
    #             "x2": 1200,
    #             "y2": y2_value
    #         }
    #     }
