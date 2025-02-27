import time
import pandas as pd
import json
import uuid
import openai
import requests
import re
import os
import numpy as np
import os
from dotenv import load_dotenv
import traceback
from firebase_api.utils import save_summary_to_firestore
from datetime import datetime, timezone
load_dotenv()

MODEL = "gpt-4o"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=OPENAI_API_KEY)
NAVER_MAP_CLIENT_ID = os.getenv("NAVER_MAP_CLIENT_ID")
NAVER_MAP_CLIENT_SECRET = os.getenv("NAVER_MAP_CLIENT_SECRET")

def remove_bounding_boxes(data):
    """Bounding Box 값을 제거하고 저장하는 함수"""
    bounding_boxes = {}
    
    def traverse(node, path=""):
        if isinstance(node, dict):
            if "bounding_box" in node:
                bounding_boxes[path] = node["bounding_box"]
                del node["bounding_box"]
            for key, value in node.items():
                traverse(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                traverse(item, f"{path}[{idx}]")

    traverse(data)
    return bounding_boxes

def process_all_json(input_dir):
    try:
        # 파일 경로 설정
        files = {
            "coai": os.path.join(input_dir, "coai_result_a.json"),
            "ledger": os.path.join(input_dir, "ledger_result.json"),
            "reg": os.path.join(input_dir, "reg_result.json")
        }

        with open(files["coai"], 'r', encoding='utf-8') as f:
            coai_data = json.load(f)
        with open(files["ledger"], 'r', encoding='utf-8') as f:
            ledger_data = {"page1": json.load(f)}
        with open(files["reg"], 'r', encoding='utf-8') as f:
            reg_data = json.load(f)

        # 데이터 통합
        merged_data = {
            "contract": coai_data,
            "building_registry": ledger_data,
            "registry_document": reg_data
        }

        # 1단계: 소유자 수 조정
        name_count = sum(1 for key in ledger_data["page1"].keys() if key.startswith("성명"))
        owners = []
        for page_key, page_content in reg_data.items():
            if not isinstance(page_content, dict):
                continue
            
            for key, value in page_content.items():
                if key.startswith("소유자"):
                    owner_info = {
                        "page": page_key,
                        "key": key,
                        "y1": value["bounding_box"]["y1"],
                        "text": value.get("text", "")
                    }
                    owners.append(owner_info)

        # 소유자 수 조정
        owners.sort(key=lambda x: x["y1"])
        owners_to_remove = len(owners) - name_count

        if owners_to_remove > 0:
            for i in range(owners_to_remove):
                owner = owners[i]
                del merged_data["registry_document"][owner["page"]][owner["key"]]
        
        return merged_data
    
    except Exception as e:
        print(f"\n오류 발생: {str(e)}")
        raise

# 주소 앞에 [집합건물] 헤드 지우기
def remove_brackets(address):
    # 정규표현식을 사용하여 [...]로 둘러싸인 부분을 찾아 제거
    cleaned_address = re.sub(r'\[.*?\]', '', address)
    # 추가 공백 정리 (여러 공백을 하나로 줄이기)
    cleaned_address = re.sub(r'\s+', ' ', cleaned_address).strip()
    return cleaned_address
# 네이버 Geocoding API 호출 함수 정의
def geocode_address(address):
    url = f"https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode?query={address}"
    headers = {
        'X-NCP-APIGW-API-KEY-ID': NAVER_MAP_CLIENT_ID,
        'X-NCP-APIGW-API-KEY': NAVER_MAP_CLIENT_SECRET
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data['addresses']:
            location = data['addresses'][0]
            return location['y'], location['x']
        else:
            return None, None
    else:
        print(f"Error {response.status_code}: {response.text}")
        return None, None
#gpt 기동
def analyze_with_gpt(analysis_data):
    message_content = f"다음 데이터를 분석하고 JSON 형식으로 응답해주세요. {analysis_data}"
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": message_content
            }],
            response_format={"type": "json_object"},  # 명시적으로 JSON 응답 지정
            max_tokens=3000
        )
        
        # 응답 안전하게 파싱
        try:
            return json.loads(response.choices[0].message.content.strip())
        except json.JSONDecodeError as e:
            print(f"JSON 파싱 오류: {e}")
            print(f"원본 응답: {response.choices[0].message.content}")
            
            # 기본 응답 반환
            return {"error": f"JSON 파싱 오류: {str(e)}"}
            
    except Exception as e:
        print(f"API 호출 오류: {e}")
        return {"error": f"API 호출 오류: {str(e)}"}

#주소 확인
def parse_address(address):
    parsed_result = {}

    match = re.search(r"^(서울특별시|부산광역시|경기도|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|제주특별자치도|충청북도|충청남도|전라북도|전라남도|경상북도|경상남도)\s+(\S+구|\S+시|\S+군)", address)
    if match:
        parsed_result["시도"] = match.group(1)
        parsed_result["시군구"] = match.group(2)
        address = address.replace(match.group(0), "").strip() 

    match = re.search(r"(\S+동\d*|\S+읍|\S+면)(?:가)?", address)
    if match:
        full_dong = match.group(0)
        parsed_result["동리"] = full_dong
        address = address.replace(full_dong, "").strip()

    match = re.search(r"(?:제)?(\d+)동", address)
    if match:
        parsed_result["동명"] = match.group(1)
        address = re.sub(r"제?\d+동", "", address).strip()

    address = re.sub(r"제?\d+층", "", address).strip()

    match = re.search(r"(?:제)?(\d+)호", address)
    if match:
        parsed_result["호명"] = match.group(1)
        address = re.sub(r"제?\d+호", "", address).strip()

    building_match = re.search(r"([가-힣A-Za-z0-9]+(?:[가-힣A-Za-z0-9\s]+)?(?:아파트|빌라|오피스텔|타워|팰리스|파크|하이츠|프라자|빌딩|스카이|센터|시티|맨션|코아|플라자|타운|힐스))", address)
    if building_match:
        parsed_result["건물명"] = building_match.group(1)
        address = address.replace(building_match.group(1), "").strip()

    for key in ["시도", "시군구", "동리", "동명", "호명"]:
        if key not in parsed_result:
            parsed_result[key] = "nan"

    return parsed_result
#공시가 구하기
def price(address):
    result = parse_address(address)
    print(result)
    # 모든 시도에 대한 GCS 파일 경로 매핑
    gcs_urls = {
        "서울특별시": "https://storage.googleapis.com/jipsin/storage/seoul.csv",
        "부산광역시": "https://storage.googleapis.com/jipsin/storage/busan.csv",
        "대구광역시": "https://storage.googleapis.com/jipsin/storage/daegu.csv",
        "인천광역시": "https://storage.googleapis.com/jipsin/storage/incheon.csv",
        "광주광역시": "https://storage.googleapis.com/jipsin/storage/gwangju.csv",
        "대전광역시": "https://storage.googleapis.com/jipsin/storage/daejeon.csv",
        "울산광역시": "https://storage.googleapis.com/jipsin/storage/ulsan.csv",
        "세종특별자치시": "https://storage.googleapis.com/jipsin/storage/sejong.csv",
        "경기도": "https://storage.googleapis.com/jipsin/storage/gyeonggi.csv",
        "강원특별자치도": "https://storage.googleapis.com/jipsin/storage/gangwon.csv",
        "충청북도": "https://storage.googleapis.com/jipsin/storage/chungbuk.csv",
        "충청남도": "https://storage.googleapis.com/jipsin/storage/chungnam.csv",
        "전라북도": "https://storage.googleapis.com/jipsin/storage/jeunbuk.csv",
        "전라남도": "https://storage.googleapis.com/jipsin/storage/jeunnam.csv",
        "경상북도": "https://storage.googleapis.com/jipsin/storage/gyeongbuk.csv",
        "경상남도": "https://storage.googleapis.com/jipsin/storage/gyeongnam.csv",
        "제주특별자치도": "https://storage.googleapis.com/jipsin/storage/jeju.csv",
    }
    gcs_url = gcs_urls.get(result["시도"], None)

    if gcs_url:
        df = pd.read_csv(gcs_url)
    else:
        print("해당 시도에 대한 GCS 데이터 없음")
    cost = df[
        (df['시도']==result["시도"]) &
        (df['시군구']==result["시군구"]) &
        (df['동리']==result["동리"]) &
        (df["동명"]==result["동명"]) &
        (df["호명"]==result["호명"])
    ]

    if cost.empty:
        cost = df[
            (df['시도']==result["시도"]) &
            (df['시군구']==result["시군구"]) &
            (df['동리']==result["동리"])
        ]
        

    cost_records = cost.to_dict(orient='records')

    # DataFame에서 직접 공시가격 확인 (GPT 호출 없이)
    if not cost.empty:
        # 결과가 1개만 있으면 바로 반환
        if len(cost) == 1:
            direct_price = cost.iloc[0]['공시가격']
            return {"공시가격": direct_price, "method": "direct_match"}
    
    # GPT 분석 사용
    if len(cost_records) == 0:
        print("검색 결과가 없습니다. 데이터베이스에 해당 주소와 유사한 항목이 없습니다.")
        return {"error": "해당 주소를 찾을 수 없습니다.", "공시가격": "NA"}
    else:
        parsed_info = {
            "원본주소": address,
            "파싱결과": result,
            "건물명_추출": result.get("건물명", "알 수 없음"),
            "검색결과수": len(cost_records)
        }

        prompt = {
            "task": "주소 유사도 분석 및 공시가격 추출",
            "parsed_info": parsed_info,
            "candidate_data": cost_records,
            "instruction": "위 원본 주소와 가장 유사한 후보 데이터를 찾아 해당 행의 '공시가격' 값을 JSON 형식으로 반환해주세요. 단지명과 동호수가 가장 중요한 매칭 기준입니다. 반드시 '공시가격' 키에 공시가격 값을 포함해야 합니다."
        }
        
        prompt_json = json.dumps(prompt, ensure_ascii=False, indent=2)
        try:
            gpt_result = analyze_with_gpt(prompt_json)
            
            if 'public_price' in gpt_result:
                return {"공시가격": gpt_result['public_price'], "method": "gpt_analysis"}
            elif '공시가격' in gpt_result:
                return {"공시가격": gpt_result['공시가격'], "method": "gpt_analysis"}
            else:
                return {"공시가격": cost.iloc[0]['공시가격'], "method": "fallback_first_result"}
                
        except Exception as e:
            if not cost.empty:
                return {"공시가격": cost.iloc[0]['공시가격'], "method": "fallback_after_error"}
            return {"error": f"GPT API 오류: {str(e)}", "공시가격": "NA"}
#좌표로 면적 찾기


#------------------------[수정사항]--------------------------
def restore_bounding_boxes(data, bounding_boxes):
    """저장된 Bounding Box 값을 복원하는 함수"""
    def traverse(node, path=""):
        if isinstance(node, dict):
            if path in bounding_boxes:
                node["bounding_box"] = bounding_boxes[path]
            for key, value in node.items():
                new_path = f"{path}.{key}" if path else key
                traverse(value, new_path)
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                new_path = f"{path}[{idx}]"
                traverse(item, new_path)
    
    # 깊은 복사로 입력 데이터 보존
    import copy
    result = copy.deepcopy(data)
    
    # 복원 실행
    traverse(result)
    
    # 결과 반환 (이 부분이 누락되어 있었음)
    return result
def building(data):
    result_dict = {}
    counter = 1
    address_list = []
    used_keys = []

    for key, sub_data in data["contract"].items():
        if isinstance(sub_data, dict):
            if "소재지" in sub_data and "임차할부분" in sub_data:
                combined_address = sub_data["소재지"]["text"] + " " + sub_data["임차할부분"]["text"]
                lat, lng = geocode_address(combined_address)
                if lat and lng:
                    address_key = f"location_{counter}"
                    result_dict[address_key] = {
                        "address": combined_address,
                        "latitude": lat,
                        "longitude": lng,
                        "source": "coai_combined"
                    }
                    used_keys.append(address_key)
                    address_list.append(combined_address)
                    counter += 1

    for key, sub_data in data["building_registry"].items():
        if isinstance(sub_data, dict) and "도로명주소" in sub_data:
            address = sub_data["도로명주소"]["text"]
            lat, lng = geocode_address(address)
            if lat and lng:
                address_key = f"location_{counter}"
                result_dict[address_key] = {
                    "address": address,
                    "latitude": lat,
                    "longitude": lng,
                    "source": "ledger_도로명주소"
                }
                used_keys.append(address_key)
                address_list.append(address)
                counter += 1

    for key, sub_data in data.get("registry_document", {}).items():
        if isinstance(sub_data, dict) and "건물주소" in sub_data:
            address = remove_brackets(sub_data["건물주소"]["text"])
            lat, lng = geocode_address(address)
            if lat and lng:
                address_key = f"location_{counter}"
                result_dict[address_key] = {
                    "address": address,
                    "latitude": lat,
                    "longitude": lng,
                    "source": "reg_건물주소"
                }
                used_keys.append(address_key)
                address_list.append(address)
                counter += 1

    json.dumps(result_dict, ensure_ascii=False, indent=2)
    prompt = {
        "task": "주소 유사도 분석 및 도로명 주소 추출",
        "location": result_dict,
        "addresses": address_list,
        "instruction": "각 주소별 유사도를 분석하고 같은 장소인지 확인하여 모두 같은 장소라면 reg_건물주소를 result 값으로 출력해줘. 아니면 'nan'을 result 값으로 출력해줘. 다른 말은 들어가면 안돼"
    }

    prompt_json = json.dumps(prompt, ensure_ascii=False, indent=2)
    result = analyze_with_gpt(prompt_json)
    print(result)
    return result['result']
#실행(수정사항 포함)

def find_keys_in_json(data):
    """
    JSON 데이터에서 특정 키들을 찾아 결과를 반환하는 함수
    
    Args:
        data (dict): 검색할 JSON 데이터
        
    Returns:
        dict: 찾은 키와 해당 값
    """
    # 찾을 키 목록
    target_keys = [
        "임대인", "성명1", "성명2", "소유자_3", "소유자_4",  # 임대인/소유자 관련
        "위반건축물",  # 건축물 위반사항
        "신탁", "가압류", "가처분",  # 권리 제한 관련
        "보증금_1", "보증금_2", "차임_1", "차임_2",  # 금액 관련
        "(채권최고액)",  # 채권 관련
        "관리비_정액", "관리비_비정액",  # 관리비 관련
        "임대차기간", "계약기간",  # 기간 관련
        "특약", "특약사항",  # 특약 관련
        "집합건물", "면적"  # 건물 유형 및 면적 관련
    ]
    
    # 결과 저장할 딕셔너리
    result = {
        "contract": {},
        "building_registry": {},
        "registry_document": {}
    }
    
    # 계약서(contract) 검색
    if "contract" in data:
        for page_key, page_data in data["contract"].items():
            for key, value in page_data.items():
                if key in target_keys:
                    result["contract"][key] = value
    
    # 건축물대장(building_registry) 검색
    if "building_registry" in data:
        for page_key, page_data in data["building_registry"].items():
            for key, value in page_data.items():
                if key in target_keys:
                    result["building_registry"][key] = value
    
    # 등기부등본(registry_document) 검색
    if "registry_document" in data:
        for page_key, page_data in data["registry_document"].items():
            for key, value in page_data.items():
                if key in target_keys:
                    result["registry_document"][key] = value

    
    return result
def solution_1(data): #등본, 건축물 대장 상 위험 매물, 면적, 계약기간, 임대차 기간, 특약 요약, 주소

    prompt = (f"""
{data}에서 'contract'는 계약서, 'building_registry'는 건축물 대장, 'registry_document'는 등기부등본이다.

다음 항목들을 분석하여 문제가 있으면 각 항목별로 notice와 solution을 추가해주세요:

1. 등기부등본에 '신탁', '압류', '가처분', '가압류', '가등기'가 있는지 확인
2. 건축물대장에 '위반건축물'이 있는지 확인
3. 건축물대장과 계약서상의 면적이 일치하는지 확인
4. 계약기간과 임대차 기간이 일치하는지 확인
5. 특약사항과 특약에 임차인에게 불리한 조항이 있는지 반드시 확인
6. 관리비_비정액에 값이 있고 관리비_정액에 값이 없으면 경고
원본 데이터 구조를 유지하면서, 분석한 항목에 'notice'와 'solution' 필드를 추가해주세요.
예를 들어, 등기부등본에 '가압류'가 있다면:
"""
"""
```
{{
  "가압류": {{
    "text": "...",
    "bounding_box": {{...}},
    "notice": "가압류가 설정되어 있어 권리 침해 우려가 있습니다",
    "solution": "가압류 해제 후 계약 진행 권장"
  }}
}}

```

위반건축물이 있다면:
```
{{
  "위반건축물": {{
    "text": "...",
    "bounding_box": {{...}},
    "notice": "위반건축물로 등록되어 있어 법적 문제가 있습니다",
    "solution": "위반 내용 확인 및 시정 후 계약 진행 권장"
  }}
}}
```

면적/계약기간 불일치는 해당 필드에 notice와 solution을 추가해주세요.
특약사항은 해당 필드에 notice로 요약 내용을 추가해주세요.

문제가 없는 항목은 다음과 같이 추가해주세요:
```
{{
  "notice": "문제 없음",
  "solution": "계약 진행 가능"
}}
```

원본 데이터의 모든 구조를 유지하고, 필요한 필드에만 notice와 solution을 추가하는 방식으로 결과를 JSON 형태로 반환해주세요.
""")
    result = analyze_with_gpt(prompt)

    return result

def solution_2(data): #사용자 이름
    prompt = (f"""
{data}에서 'contract'는 계약서, 'building_registry'는 건축물 대장, 'registry_document'는 등기부등본이다.
계약서에서 '임대인', 건축물대장에서 '성명', 등기부등본에서 '소유자'이 일치하는지 확인 할 것.
성명, 소유자가 1명이 아닌 경우 공동명의로 판단한다.
성명끼리는 같은 notice와 solution을 출력한다.
소유자끼리는 같은 notice와 solution을 출력한다.
"""
"""
소유자가 한 명이 아니라면 '임대인'과 '소유자' 필드에 notice와 solution을 추가해야 한다
{{
  "임대인": {{
    "text": "...",
    "bounding_box": {{...}},
    "notice": "소유자가 공동명의로 확인됩니다",
    "solution": "다른 소유주의 확인 필요"
  }}
}}

건축물대장 '성명'과 등기부등본의 '소유자', 계약서의 '임대인' 중 일치하지 않는 것이 있다면
{{
  "소유자": {{
    "text": "...",
    "bounding_box": {{...}},
    "notice": "건축물 대장 혹은 계약서의 임대인과 일치하지 않습니다",
    "solution": "임대인을 확실하게 확인하여 주십시오."
  }}
}}

{{
  "성명": {{
    "text": "...",
    "bounding_box": {{...}},
    "notice": "건축물 대장 혹은 계약서의 임대인과 일치하지 않습니다",
    "solution": "임대인을 확실하게 확인하여 주십시오."
  }}
}}

임대인/성명/소유자 불일치는 해당 필드에 notice와 solution을 추가해주세요.
문제가 없는 항목은 다음과 같이 추가해주세요:
{{
  "notice": "문제 없음",
  "solution": "계약 진행 가능"
}}

원본 데이터의 모든 구조를 유지하고, 필요한 필드에만 notice와 solution을 추가하는 방식으로 결과를 JSON 형태로 반환해주세요.
""")
    result = analyze_with_gpt(prompt)

    return result


def solution_3(data, cost): #보증금, 근저당권, 공시가
    # 이전 코드에서 문자열 연결과 중첩 따옴표가 혼합되어 있어 오류 발생 가능성 높음
    
    # 단일 f-string으로 수정하여 일관성 유지
    prompt = (f"""
{data}에서 'contract'는 계약서, 'building_registry'는 건축물 대장, 'registry_document'는 등기부등본이다. {cost}는 공시가격이다.
"""
f"""
다음 항목들을 분석하여 문제가 있으면 각 항목별로 notice와 solution을 추가해주세요:
'보증금', '채권최고액' 외에는 notice, solution을 추가하지 않는다.

1. 보증금 일관성 확인:
   - 보증금_1과 보증금_2의 금액이 다른 경우 오류 메시지를 출력
   - 금액 차이가 있는 경우 두 보증금 필드 모두에 오류 표시

원본 데이터 구조를 유지하면서, 분석한 항목에 'notice'와 'solution' 필드를 추가해주세요.
이외의 다른 정보는 무시한다.

2. 차임 일관성 확인:
예를 들어, 차임_1과 차임_2의 금액이 다른 경우

예시 형식:
{{
  "보증금_1": {{
    "text": "예시 텍스트",
    "bounding_box": {{...}},
    "notice": "보증금_2와 금액이 다릅니다",
    "solution": "계약서 내용 확인 후 보증금 금액을 일치시켜야 합니다."
  }}
}}

채권최고액에 대한 분석 결과는 다음과 같이 추가해주세요:
{{
  "채권최고액": {{
    "text": "예시 텍스트",
    "bounding_box": {{...}},
    "notice": "채권최고액이 보증금과 공시가격({cost})를 초과하는지 확인하세요",
    "solution": "채권최고액은 보증금과 공시가격의 차이 이내로 설정하는 것이 안전합니다."
  }}
}}

공시가격이 없는 경우:
{{
  "보증금_1": {{
    "text": "예시 텍스트",
    "bounding_box": {{...}},
    "notice": "공시가격 정보가 없어 적정 보증금 여부를 판단할 수 없습니다.",
    "solution": "국토교통부 부동산 공시가격 알리미 등을 통해 공시가격을 확인하세요."
  }}
}}

문제가 없는 항목은 다음과 같이 추가해주세요:
{{
  "notice": "문제 없음",
  "solution": "계약 진행 가능"
}}

JSON 형식으로 응답해주세요.
""")
    result = analyze_with_gpt(prompt)
    return result

def merge_analysis(sol_json, analysis_jsons):
    """
    구조가 동일한 여러 JSON에서 notice와 solution을 병합
    모든 notice와 solution을 가져옴 (기본 메시지 포함)
    
    Args:
        sol_json (dict): 원본 JSON
        analysis_jsons (list): 분석 결과 JSON 리스트
    
    Returns:
        dict: 병합된 JSON
    """
    # 각 섹션과 필드 순회
    for section_key, section in sol_json.items():
        for subsection_key, subsection in section.items():
            for field_key, field_value in list(subsection.items()):  # list()로 감싸서 반복 중 수정 가능하게 함
                notices = []
                solutions = []
                
                # 각 분석 JSON에서 값 확인
                for analysis in analysis_jsons:
                    # 동일한 경로에 필드가 있는지 확인
                    if (section_key in analysis and 
                        subsection_key in analysis[section_key] and 
                        field_key in analysis[section_key][subsection_key]):
                        
                        analysis_field = analysis[section_key][subsection_key][field_key]
                        
                        # notice와 solution이 있는지 확인
                        if isinstance(analysis_field, dict):
                            if "notice" in analysis_field:
                                # 모든 notice 포함 (문제 없음도 포함)
                                if analysis_field["notice"] not in notices:
                                    notices.append(analysis_field["notice"])
                            
                            if "solution" in analysis_field:
                                # 모든 solution 포함 (계약 진행 가능도 포함)
                                if analysis_field["solution"] not in solutions:
                                    solutions.append(analysis_field["solution"])
                
                # 결과 추가
                if isinstance(field_value, dict):
                    # 이미 딕셔너리인 경우
                    if notices:
                        sol_json[section_key][subsection_key][field_key]["notice"] = "; ".join(notices)
                    
                    if solutions:
                        sol_json[section_key][subsection_key][field_key]["solution"] = "; ".join(solutions)
                else:
                    # 딕셔너리가 아닌 경우 변환
                    if notices or solutions:
                        new_field = {"text": field_value}
                        
                        if notices:
                            new_field["notice"] = "; ".join(notices)
                        
                        if solutions:
                            new_field["solution"] = "; ".join(solutions)
                        
                        sol_json[section_key][subsection_key][field_key] = new_field
    
    return sol_json
    

# 엔드포인트와 통합을 위한 분석 함수
def analyze_contract_data(merged_data, res_1, cost):
    """
    계약서 데이터를 분석하는 통합 함수 - request() 함수와 유사한 구조로 구현
    
    Args:
        merged_data (dict): 병합된 문서 데이터
        res_1 (str/list): 주소 일치 여부 결과
        cost (int/str): 공시가격
        
    Returns:
        dict: 분석 결과
    """
    try:
        # 원본 데이터 보존을 위한 깊은 복사
        import copy
        data = copy.deepcopy(merged_data)
        
        # 주소 관련 키 목록 정의
        used_keys = [
            "소재지",
            "임차할부분",
            "도로명주소",
            "건물주소"
        ]
        
        # 디버깅: 타입과 정확한 값 확인
        print(f"res_1의 타입: {type(res_1)}, 값: {repr(res_1)}")
        
        # res_1이 리스트인 경우 처리
        if isinstance(res_1, list):
            if res_1 and all(isinstance(addr, str) for addr in res_1):
                if all(addr == res_1[0] for addr in res_1):
                    res_1 = res_1[0]  # 모든 주소가 동일하면 첫 번째 주소 사용
                else:
                    res_1 = "nan"  # 주소가 다르면 불일치로 처리
            else:
                res_1 = "nan"  # 빈 리스트이거나 문자열 아닌 요소가 있으면 불일치로 처리
        
        # 보다 안전한 조건식 (request() 함수와 동일)
        if res_1 and res_1 not in ["nan", "NA", "NaN", "NAN", float('nan'), None]:
            # 주소 일치 - 각 문서의 주소 관련 필드에 notice 추가
            for section in ["contract", "building_registry", "registry_document"]:
                if section in data:
                    for subsection_key, subsection in data[section].items():
                        for key in used_keys:
                            if key in subsection and isinstance(subsection[key], dict):
                                subsection[key]["notice"] = "주소 일치 확인됨"
                                subsection[key]["solution"] = "계약 진행 가능"
                                print(f"{section}.{subsection_key}.{key}에 일치 notice 추가 완료")
        else:
            # 주소 불일치 감지
            cost = 'nan'
            print(f"주소 불일치 감지: res_1 = {res_1}")
            
            # used_keys가 None이거나 비어있는지 확인
            if used_keys is None:
                print("used_keys가 None입니다. 기본 키를 사용합니다.")
                used_keys = ["주소", "소재지", "건물주소"]  # 기본 키 설정
            
            # used_keys가 비어있는지 확인
            if not used_keys:
                print("used_keys가 비어있습니다. 기본 키를 사용합니다.")
                used_keys = ["주소", "소재지", "건물주소"]  # 기본 키 설정
            
            print(f"사용할 키: {used_keys}")
            
            # data 내에서 주소 관련 키를 찾아 notice 추가 (request() 함수와 동일한 방식)
            for section in ["contract", "building_registry", "registry_document"]:
                if section in data:
                    for subsection_key, subsection in data[section].items():
                        for key in used_keys:
                            if key in subsection and isinstance(subsection[key], dict):
                                subsection[key]["notice"] = "주소가 일치하지 않습니다"
                                subsection[key]["solution"] = "주소 확인이 필요합니다."
                                print(f"{section}.{subsection_key}.{key}에 불일치 notice 추가 완료")
        
        # 세 가지 분석 실행
        print("solution_1 분석 시작...")
        result_1 = solution_1(data)
        
        print("solution_2 분석 시작...")
        result_2 = solution_2(data)
        print("📌 AI 분석 결과:", result_2)

        print("solution_3 분석 시작...")
        result_3 = solution_3(data, cost)
        
        print("분석 결과 병합 중...")
        # 결과 병합
        merged_result = merge_analysis(data, [result_1, result_2, result_3])
        
        return merged_result
        
    except Exception as e:
        print(f"분석 중 오류 발생: {str(e)}")
        traceback.print_exc()
        return merged_data  # 오류 발생 시 원래 데이터 반환환
    

def adjust_owner_count(building_registry_data, registry_document_data, merged_data):
    """
    건축물대장과 등기부등본의 소유자 수를 일치시키는 함수
    
    Args:
        building_registry_data (dict): 건축물대장 데이터
        registry_document_data (dict): 등기부등본 데이터
        merged_data (dict): 전체 통합 데이터
        
    Returns:
        dict: 소유자 수가 조정된 통합 데이터
    """
    try:
        # 건축물대장의 소유자 수 계산
        name_count = sum(1 for key in building_registry_data.keys() if key.startswith("성명"))
        
        
        # 등기부등본의 소유자 정보 수집
        owners = []
        for page_key, page_content in registry_document_data.items():
            if not isinstance(page_content, dict):
                continue
            
            for key, value in page_content.items():
                if key.startswith("소유자"):
                    owner_info = {
                        "page": page_key,
                        "key": key,
                        "y1": value["bounding_box"]["y1"],
                        "text": value.get("text", "")
                    }
                    owners.append(owner_info)

        # 소유자 수 조정
        owners.sort(key=lambda x: x["y1"])
        owners_to_remove = len(owners) - name_count

        if owners_to_remove > 0:
            for i in range(owners_to_remove):
                owner = owners[i]
                del merged_data["registry_document"][owner["page"]][owner["key"]]
        
        return merged_data
    
    except Exception as e:
        print(f"소유자 수 조정 중 오류 발생: {str(e)}")
        raise

def clean_boundboxing_json(input_json):
    """
    바운딩 박스와 같은 불필요한 정보를 제거하는 함수
    
    Args:
        input_json (dict): 입력 JSON 데이터
    
    Returns:
        dict: 정리된 JSON 데이터
    """
    if isinstance(input_json, str):
        # 파일 경로인 경우
        with open(input_json, 'r', encoding='utf-8') as f:
            input_json = json.load(f)
    
    result = {}
    
    # 각 최상위 키에 대해 처리
    for top_key, top_value in input_json.items():
        result[top_key] = {}
        
        # 각 섹션(페이지) 처리
        for section_key, section_value in top_value.items():
            result[top_key][section_key] = {}
            
            # 각 항목 처리
            for item_key, item_value in section_value.items():
                # 딕셔너리가 아닌 경우 건너뛰기
                if not isinstance(item_value, dict):
                    continue
                
                # "notice" 키가 있는 항목만 유지
                if "notice" in item_value:
                    # 새 항목 생성 (bounding_box 제외)
                    new_item = {}
                    for field_key, field_value in item_value.items():
                        if field_key != "bounding_box":
                            new_item[field_key] = field_value
                    
                    # 결과에 추가
                    result[top_key][section_key][item_key] = new_item
            
            # 빈 섹션이면 삭제
            if not result[top_key][section_key]:
                del result[top_key][section_key]
        
        # 빈 최상위 키면 삭제
        if not result[top_key]:
            del result[top_key]
    
    return result

def summary_result(analysis_data):
    """
    분석 데이터를 요약하는 함수
    
    Args:
        analysis_data (dict): 분석 결과 데이터
    
    Returns:
        dict: 요약 결과
    """
    prompt = """
임대차 계약서를 분석하고 다음 JSON 형식으로 결과를 반환해 주세요.  
각 항목에는 "text" (내용)과 "check" (문제 여부, true/false)를 포함해야 합니다.  
또한, 계약의 전체 요약 정보를 제공하는 "summary" 키를 추가해야 합니다. 
차임_1 혹은 차임_2를 반드시 출력한다.

{
  "summary": {
    "text": "[계약의 전체적인 요약 및 주요 문제점]",
    "check": [true/false]  // 전체 계약에 큰 문제가 있으면 true, 없으면 false
  },
  "contract_details": {
    "임대인": {
      "text": "[임대인 이름]",
      "check": [true/false]  // 임대인 정보에 문제가 있으면 true
    },
    "소재지": {
      "text": "[임대차 건물의 주소]",
      "check": [true/false]
    },
    "임차할부분": {
      "text": "[임차 대상 공간]",
      "check": [true/false]
    },
    "면적": {
      "text": "[전용 면적 m²]",
      "check": [true/false]
    },
    "계약기간": {
      "text": "[계약 시작일 ~ 종료일]",
      "check": [true/false]  // 갱신청구권 언급이 없으면 true
    },
    "보증금": {
      "text": "[보증금 금액]",
      "check": [true/false]  // 보증금 관련 정보가 불명확하면 true
    },
    "차임": {
      "text": "[차임_1, 차임_2 비교 및 월세 금액 및 지불 조건]",
      "check": [true/false]
    },
    "특약사항": {
      "text": "[특약 조항 요약]",
      "check": [true/false]  // 특약에서 보호 조항이 미흡하면 true
    },
    "등기부등본": {
      "text": "[건물 소유자 및 주요 정보]",
      "check": [true/false]
    }
  }
}
"""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": f"다음 JSON 데이터를 분석해 주세요:\n\n```json\n{analysis_data}\n```\n\n이 데이터에서 'notice'와 'solution' 정보를 기반으로 계약의 주요 문제점과 해결책을 요약해주세요."},
            {"role": "user", "content": f"출력 양식은 다음과 같습니다. {prompt}"}
        ],
        response_format={"type": "json_object"},
        max_tokens=3000
    )
    return json.loads(response.choices[0].message.content.strip())

def generate_and_save_summary(analysis_result, user_id, contract_id):
    """
    분석 결과를 요약하고 Firestore에 저장하는 함수
    
    Args:
        analysis_result (dict): 분석 결과 데이터
        user_id (str): 사용자 ID
        contract_id (str): 계약 ID
        
    Returns:
        dict: 요약 결과
    """
    try:
        # 1. 바운딩 박스 제거
        cleaned_data = clean_boundboxing_json(analysis_result)
        
        # 2. GPT로 요약 생성
        summary_data = summary_result(cleaned_data)
        
        # 3. 메타데이터 추가
        summary_data.update({
            "userId": user_id,
            "contractId": contract_id,
            "createdAt": datetime.now(timezone.utc).isoformat()
        })
        
        # 4. Firestore에 저장
        save_success = save_summary_to_firestore(user_id, contract_id, summary_data)
        
        # 5. 결과 반환
        if save_success:
            return summary_data
        else:
            return {
                "error": "요약 저장 실패",
                "userId": user_id,
                "contractId": contract_id
            }
            
    except Exception as e:
        print(f"요약 생성 및 저장 중 오류 발생: {str(e)}")
        traceback.print_exc()
        return {
            "error": f"요약 생성 및 저장 중 오류 발생: {str(e)}",
            "userId": user_id,
            "contractId": contract_id
        }