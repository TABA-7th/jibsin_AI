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


# 환경 변수 로드
load_dotenv()

# API 설정
secret_key = os.getenv("OCR_SECRET_KEY")
api_url = os.getenv("OCR_API_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4o" 

client = openai.OpenAI(api_key=OPENAI_API_KEY)

def base_xy(i):
    if i==1:
        rows = [
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
            ['(관리비_정액)',220,1032,1034,1068],
            ['(관리비_비정액)',216,1254,1038,1286],
            ['(임대일)',877,1344,1145,1378],
            ['(종료일)',553,1369,923,1408],
            ['수리필요시설',90,1479,254,1512],
            ['(수리할내용)',460,1473,1127,1512],
            ['(수리완료시기)',504,1514,841,1551],
        ]
    elif i==2:
        rows = [
        ['임대인부담',73,215,225,263],
        ['임차인부담',75,269,226,310],
        ['(임대인부담)',228,214,1202,264],
        ['(임차인부담)',228,264,1200,312],
        ['(중개보수)', 378,1044,814,1080],
        ['(교부일)', 378,1156,766,1192],
        ['특약사항',56,1234,1188,1658],
        ]
    else:
        rows = [
        ['특약',46,28,1196,166],
        ['(계약일)',510,236,1184,274],
        ['임대인_주소', 98,288,250,334],
        ['(임대인_주소)',254,290,1064,338],
        ['임대인_주민등록번호',110,338,242,386],
        ['(임대인_주민등록번호)',256,336,564,388],
        ['임대인_전화',560,334,692,386],
        ['(임대인_전화)',690,338,854,388],
        ['(임대인_성명)',930,340,1066,390],
        ['임대인_성명', 860,342,926,380],
        ['임대인_대리인_주소',258,390,326,434],
        ['임대인_대리인_주소', 330,392,562,438],
        ['임대인_대리인_주민등록번호',564,388,690,438],
        ['(임대인_대리인_주민등록번호)',694,390,858,438],
        ['임대인_대리인_성명',862,392,922,434],
        ['(임대인_대리인_성명)',932,390,1064,438],
        ['임차인_주소',110,442,246,488],
        ['(임차인_주소)',254,290+154,1064,338+154],
        ['임차인_주민등록번호',110,338+154,242,386+154],
        ['(임차인_주민등록번호)',256,336+154,564,388+154],
        ['임차인_전화',560,334+154,692,386+154],
        ['(임차인_전화)',690,338+154,854,388+154],
        ['(임차인_성명)',930,340+154,1066,390+154],
        ['임차인_성명', 860,342+154,926,380+154],
        ['임차인_대리인_주소',258,390+154,326,434+154],
        ['임차인_대리인_주소', 330,392+154,562,438+154],
        ['임차인_대리인_주민등록번호',564,388+154,690,438+154],
        ['(임차인_대리인_주민등록번호)',694,390+154,858,438+154],
        ['임차인_대리인_성명',862,392+154,922,434+154],
        ['(임차인_대리인_성명)',932,390+154,1064,438+154],
        ['사무소소재지_1',110,600,242,642],
        ['(사무소소재지_1)',256,596,562,644],
        ['사무소명칭_1',122,644,236,686],
        ['(사무소명칭_1)',254,642,562,692],
        ['사무소소재지_2',586,594,712,642],
        ['(사무소소재지_2)',740,596,1176,646],
        ['사무소명칭_2',594,642,710,690],
        ['(사무소명칭_2)',740,642,1180,696],
            ]
    xy = pd.DataFrame(columns=['Text', 'x1', 'y1', 'x2', 'y2'])
    xy = pd.concat([xy, pd.DataFrame(rows, columns=xy.columns)], ignore_index=True)
    return xy

def cre_ocr(image, secret_key, api_url):
    """OCR 추출 함수"""
    # target_size = (1240, 1753) #1229
    # image_1 = cv2.resize(image, target_size, interpolation=cv2.INTER_AREA)
    
    request_json = {
        'images': [{'format': 'jpg', 'name': 'demo'}],
        'requestId': str(uuid.uuid4()),
        'version': 'V2',
        'timestamp': int(round(time.time() * 1000))
    }
    
    # 이미지 처리
    _, img_encoded = cv2.imencode('.jpg', image)
    files = [('file', ('image.jpg', img_encoded.tobytes(), 'image/jpeg'))]
    
    payload = {'message': json.dumps(request_json).encode('UTF-8')}
    headers = {'X-OCR-SECRET': secret_key}
    
    response = requests.request("POST", api_url, headers=headers, data=payload, files=files)
    
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
    """JSON 형식 오류 수정 함수"""
    text = text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    json_end_index = text.rfind("}")
    if json_end_index != -1:
        text = text[:json_end_index+1]  # JSON 부분만 남김
    text = re.sub(r'}\s*{', '}, {', text)
    text = re.sub(r'(\d{1,3})(\d{3},\d{3})', r'\1,\2', text)
    return text

def ttj(text: str, output_file: str) -> str:
    """JSON 데이터 정리 및 저장 함수"""
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

def contract_keyword_ocr(image_urls, doc_type, user_id, contract_id):
    """Firebase URL에서 계약서 OCR 처리"""
    all_results = {}
    
    
    for image_url in image_urls:
        try:
            # URL에서 페이지 번호 추출 부분 수정
            page_number = int(re.search(r'page(\d+)\.jpg', image_url).group(1))
            
            # URL에서 이미지 다운로드
            response = requests.get(image_url)
            if response.status_code != 200:
                print(f"❌ 이미지 다운로드 실패: {image_url}")
                continue
            
            # 이미지 데이터 변환
            image_data = response.content
            nparr = np.frombuffer(image_data, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # OCR 처리
            df = cre_ocr(image, secret_key, api_url)
            if df.empty:
                print(f"❌ OCR 처리 실패 (페이지 {page_number})")
                continue
                
            # 페이지 번호에 맞는 base_xy 매핑 가져오기
            xy = base_xy(page_number)
            # JSON 변환
            xy_json = xy.to_json(orient="records", force_ascii=False)
            df_json = df.to_json(orient="records", force_ascii=False)
            
        
            # target_texts 설정 (페이지별)
            if page_number == 1:
                target_texts = {
                    "임대인": "사람 이름 (예: 홍길동)",
                    "임차인": "사람 이름 (예: 김철수)",
                    "소재지": "도로명 주소 (예: 서울특별시 강남구 테헤란로 123)",
                    "토지":"종류 (예: 대)",
                    "건물":"종류 (예: 철근콘크리트구조)",
                    "임차할부분":"호수 (예: 제 1층 101호)",
                    "면적":"면적 (예: 88.8m2)",
                    "계약기간": "YYYY-MM-DD ~ YYYY-MM-DD (예: 2025-01-01 ~ 2026-01-01)",
                    "보증금_1": "###원 (예: 10,000,000원)",
                    "보증금_2": "###원 (예: 5,000,000원)",
                    "계약금": "###원 (예: 3,000,000원)",
                    "잔금": "###원 (YYYY-MM-DD에 지불) (예: 7,000,000원 (2025-06-01에 지불))",
                    "차임_1": "###원 (DD일) (예: 500,000원 (10일))",
                    "차임_2": "###원 (DD일) (예: 600,000원 (15일))",
                    "입금계좌": "계좌번호 형식 (예: 123-45-67890)",
                    "관리비_정액":"(정액인 경우) ###원 (예: (정액인 경우) 10,000원)",
                    "관리비_비정액":"(정액이 아닌 경우) ###원 (예: (정액이 아닌 경우) ###원)",
                    "중도금": "###원 (예: 2,000,000원)",
                    "임대일": "YYYY년 MM월 DD일 (예: 2025년 02월 01일)",
                    "종료일": "YYYY년 MM월 DD일 (예: 2026년 01월 01일)",
                    "수리할내용": "텍스트 (예: 보일러 수리 필요)",
                    "수리완료시기": "YYYY-MM-DD (예: 2025-03-01)"
                }
            elif page_number == 2:
                target_texts = {
                    "임대인부담":"텍스트",
                    "임차인부담":"텍스트",
                    "중개보수":"거래가액의 00%인 ###,###원",
                    "교부일":"YYYY-MM-DD",
                    "특약사항":"텍스트"
                }
            else:
                target_texts = {
                    "특약": "텍스트 (예: 본 계약의 임차인은 계약 종료 시 임대인의 요구에 따라 원상복구를 수행하며, 이에 대한 모든 비용을 부담한다. 또한, 원상복구 범위는 임대인이 단독으로 결정하며, 이에 대한 이의를 제기할 수 없다)",
                    "계약일": "yyyy년 mm월 dd일",
                    "임대인_주소": "도로명 주소 (예: 서울특별시 강남구 테헤란로 123)",
                    "임대인_주민등록번호": "000000-0000000",
                    "임대인_전화": "010-0000-0000",
                    "성명": "###",
                    "임대인_대리인_주소": "도로명 주소 (예: 서울특별시 강남구 테헤란로 123)",
                    "임대인_대리인_주민등록번호": "000000-0000000",
                    "임대인_대리인_성명": "###",        
                    "임차인_주소": "도로명 주소 (예: 서울특별시 강남구 테헤란로 123)",
                    "임차인_주민등록번호": "000000-0000000",
                    "임차인_전화": "010-0000-0000",
                    "임차인_성명": "###",
                    "임차인_대리인_주소": "도로명 주소 (예: 서울특별시 강남구 테헤란로 123)",
                    "임차인_대리인_주민등록번호": "000000-0000000",
                    "임차인_대리인_성명": "###",
                    "사무소소재지_1": "텍스트",
                    "사무소소재지_2": "도로명 주소 (예: 서울특별시 강남구 테헤란로 123)",
                    "사무소명칭_1": "텍스트",
                    "사무소명칭_2": "텍스트"
                }

            
            # GPT 분석 요청
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text":  (
                            f"다음은 OCR 분석을 위한 데이터입니다.\n\n"
                            f" **위치 데이터 (xy):**\n{xy_json}\n\n"
                            f" **내용 데이터 (df):**\n{df_json}\n\n"
                            f" **작업 목표:**\n"
                            f"- `xy` 데이터의 위치 정보(좌표)를 활용하여 `df` 데이터와 매칭\n"
                            f"- 각 바운딩 박스 안에 포함된 `df` 데이터를 분석하여 최적의 좌표로 조정\n"
                            f"- 겹치는 단어들을 묶어 최종 바운딩 박스를 생성\n"
                            f"- 내용이 없으면 'NA'로 표시\n\n"
                            f" **각 항목의 출력 형식:**\n"
                            + "\n".join([f"- **{key}**: {value}" for key, value in target_texts.items()]) +
                            f"\n\n **결과 형식:**\n"
                            f"- JSON 형식으로 반환 (각 항목의 바운딩 박스 포함)\n"
                            f"- **출력 데이터가 지정된 형식과 다를 경우 자동으로 변환하여 반환**\n\n"
                            f" **반환 예시:**\n"
                            f"{{\n"
                            f"  \"임대인\": {{\"text\": \"홍길동\", \"bounding_box\": {{\"x1\": 100, \"y1\": 200, \"x2\": 300, \"y2\": 250}}}},\n"
                            f"  \"임차인\": {{\"text\": \"김철수\", \"bounding_box\": {{\"x1\": 120, \"y1\": 220, \"x2\": 320, \"y2\": 270}}}},\n"
                            f"  \"소재지\": {{\"text\": \"서울특별시 강남구 테헤란로 123\", \"bounding_box\": {{\"x1\": 140, \"y1\": 240, \"x2\": 340, \"y2\": 290}}}},\n"
                            f"  \"계약기간\": {{\"text\": \"2025-01-01 ~ 2026-01-01\", \"bounding_box\": {{\"x1\": 150, \"y1\": 250, \"x2\": 350, \"y2\": 300}}}},\n"
                            f"  \"보증금_1\": {{\"text\": \"10,000,000원\", \"bounding_box\": {{\"x1\": 160, \"y1\": 260, \"x2\": 360, \"y2\": 310}}}},\n"
                            f"  \"입금계좌\": {{\"text\": \"123-45-67890\", \"bounding_box\": {{\"x1\": 170, \"y1\": 270, \"x2\": 370, \"y2\": 320}}}}\n"
                            f"}}\n\n"
                            f" **주의사항:**\n"
                            f"- 모든 좌표는 df를 기준으로 출력한다."
                            f"- df를 항상 우선시한다."
                            f"- x1은 항상 {df_json}을 참고한다."
                            f"- '임대일', '종료일'은 y좌표가 관리비_정액의 y좌표보다 크다."
                            f"- '특약사항'은 페이지 2의 가장 중요한 정보로, 반드시 좌표 내의 모든 텍스트를 정확히 포함해야 한다.\n"
                            f"- '특약사항'은 페이지 하단 전체를 포함하며, 페이지의 끝까지 모든 text를 포함한다.\n"
                            f"- '특약사항'을 추출할 때는 해당 영역 내의 모든 {df_json} 'text'를 결합하여 출력한다.\n"
                            f"- '특약사항'의 경우 페이지 하단에 있는 모든 내용을 빠짐없이 포함해야 한다.\n"
                            f"- '특약사항'의 바운딩 박스는 페이지 하단까지 충분히 크게 설정한다 (y2값을 충분히 크게).\n"
                            f"- '특약사항'은 특히 이미지에 보이는 점선 박스 내의 모든 내용을 포함해야 한다.\n"
                            # f"- '특약사항'은 반드시 페이지의 마지막 text까지 해당한다."
                            # f"- '특약사항'은 반드시 좌표에 해당하는 모든 {df_json} 'text' 를 출력한다."
                            # f"- '특약사항'은 반드시 해당하는 df에 해당하는 x2중 가장 큰 값을 사용한다."
                            f"- '특약'은 반드시'계약일'보다 y2가 작다(위에 있다)."
                            f"- '특약'은 페이지 3의 가장 중요한 정보 중 하나로, 반드시 좌표 내의 모든 텍스트를 정확히 포함해야 한다.\n"
                            f"- '특약'을 추출할 때는 해당 영역 내의 모든 {df_json} 'text'를 결합하여 출력한다.\n"
                            f"- '특약'은 특히 이미지에 보이는 점선 박스 내의 모든 내용을 포함해야 한다.\n"
                            f"- '관리비_정액','관리비_정액'은 ###원이 아닌 경우 NA로 처리한다."
                            f"- `xy` 데이터의 바운딩 박스를 그대로 사용하지 말고, `df` 데이터와 가장 적합한 위치로 조정\n"
                            f"- 내용이 없을 경우 `NA`로 반환, text 내용이 없는 경우 좌표를 0, 0, 0, 0으로 해줘.\n"
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
                max_tokens=3000
            )
            
            text = response.choices[0].message.content
            
            try:
                # 결과 저장
                json_data = json.loads(fix_json_format(text))
                all_results[f"page{page_number}"] = json_data
                print(f"✅ 페이지 {page_number} 처리 완료")
                
            except Exception as e:
                print(f"❌ JSON 처리 실패 (페이지 {page_number}): {e}")
                continue
                
        except Exception as e:
            print(f"❌ 처리 중 오류 발생: {e}")
            continue

    if all_results:
        all_results = edit_period(all_results)
        return all_results # 그냥 페이지별 결과만 반환
    
    return None

def edit_period(data):
    """임대일과 종료일을 찾아 임대차기간 필드를 생성하는 함수"""
    # 임대일과 종료일 찾기
    rental_start = None
    rental_end = None
    section = None

    # 모든 섹션에서 임대일과 종료일 검색
    for section_key, section_data in data.items():
        if '임대일' in section_data:
            rental_start = section_data['임대일']
            section = section_key
        if '종료일' in section_data:
            rental_end = section_data['종료일']
            section = section_key

    # 둘 다 찾았는지 확인
    if rental_start and rental_end:
        # 새로운 임대차기간 필드 생성
        rental_period = {
            "text": f"{rental_start['text']}~{rental_end['text']}",
            "bounding_box": {
                # x1, y1은 두 박스 중 더 작은 값
                "x1": min(rental_start['bounding_box']['x1'], rental_end['bounding_box']['x1']),
                "y1": min(rental_start['bounding_box']['y1'], rental_end['bounding_box']['y1']),
                # x2, y2는 두 박스 중 더 큰 값
                "x2": max(rental_start['bounding_box']['x2'], rental_end['bounding_box']['x2']),
                "y2": max(rental_start['bounding_box']['y2'], rental_end['bounding_box']['y2'])
            }
        }
        
        # 임대일, 종료일과 같은 섹션에 임대차기간 추가
        if section:
            data[section]['임대차기간'] = rental_period
        
    else:
        if not rental_start:
            print("임대일을 찾을 수 없습니다.")
        if not rental_end:
            print("종료일을 찾을 수 없습니다.")
    return data