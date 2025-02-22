import time
import pandas as pd
import json
import uuid
import time
import openai
import requests
import re
import os
MODEL = "gpt-4o"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=OPENAI_API_KEY)


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

def restore_bounding_boxes(data, bounding_boxes):
    """저장된 Bounding Box 값을 복원하는 함수"""
    def traverse(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                traverse(value, f"{path}.{key}" if path else key)
            if path in bounding_boxes:
                node["bounding_box"] = bounding_boxes[path]
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                traverse(item, f"{path}[{idx}]")
    traverse(data)

def clean_json(data):
    def analyze_with_gpt(analysis_data):
        """GPT API를 사용하여 분석을 수행하는 함수"""
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": analysis_data
            }],
            response_format={"type": "json_object"},
            max_tokens=3000
        )
        return json.loads(response.choices[0].message.content.strip())
    def ana_1(data):
        """임대인 정보 분석"""
        analysis_data = {
            "contract": [],
            "building_registry": [],
            "registry_document": []
        }

        if "contract" in data:
            for key, sub_data in data["contract"].items():
                if isinstance(sub_data, dict) and "임대인" in sub_data:
                    analysis_data["contract"].append(sub_data["임대인"]["text"])

        if "building_registry" in data:
            for key, sub_data in data["building_registry"].items():
                if isinstance(sub_data, dict):
                    for sub_key, value in sub_data.items():
                        if sub_key.startswith("성명"):
                            analysis_data["building_registry"].append(value["text"])

        if "registry_document" in data:
            for key, sub_data in data["registry_document"].items():
                if isinstance(sub_data, dict):
                    for sub_key, value in sub_data.items():
                        if sub_key.startswith("소유자"):
                            analysis_data["registry_document"].append(value["text"])

        prompt = (
        f"다음은 부동산 계약 관련 문서에서 추출한 임대인 정보입니다:"
        f"계약서 상 임대인: {', '.join(analysis_data['contract'])}"
        f"건축물대장 소유자: {', '.join(analysis_data['building_registry'])}"
        f"등기부등본 소유자: {', '.join(analysis_data['registry_document'])}"
                    
                    """부동산 계약서에서 임대 목적물의 상태와 권리 관계를 점검하고, 문제가 없는지 확인해줘.  
다음 항목을 기준으로 분석하고, 수정 또는 보완이 필요한 부분을 구체적으로 설명해줘.  

**임대 목적물의 기본 정보 확인**  
- 계약서에 기재된 **주소(동·호수 포함), 면적이 정확한가?**  
- 등기부등본과 계약서상의 주소 및 면적이 일치하는가?  

**건물의 권리관계 확인**  
- 등기부등본을 확인하여 **근저당, 가압류, 압류, 가등기, 경매개시결정을 확인했는가?**  
- 건축물대장을 확인하여 **위반건축물을 확인했는가?**

⚠ **위 항목에서 문제가 발견될 경우, 해결 방법과 법적 보호 조치를 상세히 설명해줘.**  


                    내부적으로 모든 분석을 수행한 후, 최종적으로 아래 **JSON 형식으로만** 응답해.
                    ```json
                    {
                      "notice": "발견된 문제 요약",
                      "solution": "해결 방법 요약"
                    }
                    ```
                    **출력 규칙:**
                    - 문제가 있으면 `notice`에 **주요 문제 요약**을 입력하고, `solution`에 **해결 방법**을 제공해.
                    - 문제가 없으면 다음과 같이 응답해:
                      ```json
                      {
                        "notice": "문제 없음",
                        "solution": "계약 진행 가능"
                      }
                      ```
                    - JSON 형식 외의 설명을 포함하지 마.
                    """)
        result = analyze_with_gpt(prompt)

        # 분석 결과 추가
        if "contract" in data:
            for key, sub_data in data["contract"].items():
                if isinstance(sub_data, dict) and "임대인" in sub_data:
                    data["contract"][key]["임대인"]["notice"] = result.get("notice", "")
                    data["contract"][key]["임대인"]["solution"] = result.get("solution", "")

        if "building_registry" in data:
            for key, sub_data in data["building_registry"].items():
                if isinstance(sub_data, dict):
                    for sub_key, value in sub_data.items():
                        if sub_key.startswith("성명"):
                            data["building_registry"][key][sub_key]["notice"] = result.get("notice", "")
                            data["building_registry"][key][sub_key]["solution"] = result.get("solution", "")

        if "registry_document" in data:
            for key, sub_data in data["registry_document"].items():
                if isinstance(sub_data, dict):
                    for sub_key, value in sub_data.items():
                        if sub_key.startswith("소유자"):
                            data["registry_document"][key][sub_key]["notice"] = result.get("notice", "")
                            data["registry_document"][key][sub_key]["solution"] = result.get("solution", "")

        return data
    
    def ana_2(data):
        """위치 및 면적 분석"""
        analysis_data = {
            "contract": {},
            "building_registry": {},
            "registry_document": {}
        }
        
        if "contract" in data:
            for key, sub_data in data["contract"].items():
                if isinstance(sub_data, dict):
                    for target_key in ["소재지", "임차할부분", "면적"]:
                        if target_key in sub_data:
                            analysis_data["contract"][target_key] = sub_data[target_key]["text"]

        if "building_registry" in data:
            for key, sub_data in data["building_registry"].items():
                if isinstance(sub_data, dict):
                    for target_key in ["대지위치", "도로명주소", "면적"]:
                        if target_key in sub_data:
                            analysis_data["building_registry"][target_key] = sub_data[target_key]["text"]

        if "registry_document" in data:
            for key, sub_data in data["registry_document"].items():
                if isinstance(sub_data, dict):
                    for target_key in ["신탁", "가압류", "가등기", "가처분", "건물주소"]:
                        if target_key in sub_data:
                            analysis_data["registry_document"][target_key] = sub_data[target_key]["text"]


        prompt = (f"""
        다음은 부동산 계약 관련 문서의 위치 및 면적 정보입니다:

        계약서 정보:
        - 소재지: {analysis_data['contract'].get('소재지', 'NA')}
        - 임차할부분: {analysis_data['contract'].get('임차할부분', 'NA')}
        - 면적: {analysis_data['contract'].get('면적', 'NA')}

        건축물대장 정보:
        - 대지위치: {analysis_data['building_registry'].get('대지위치', 'NA')}
        - 도로명주소: {analysis_data['building_registry'].get('도로명주소', 'NA')}
        - 면적: {analysis_data['building_registry'].get('면적', 'NA')}

        등기부등본 정보:
        - 건물주소: {analysis_data['registry_document'].get('건물주소', 'NA')}
"""
"""
                    부동산 계약서에서 임대 목적물의 상태와 권리 관계를 점검하고, 문제가 없는지 확인해줘.  
다음 항목을 기준으로 분석하고, 수정 또는 보완이 필요한 부분을 구체적으로 설명해줘.  

**임대 목적물의 기본 정보 확인**  
- 계약서에 기재된 **주소(동·호수 포함), 면적이 정확한가?**  
- 등기부등본과 계약서상의 주소 및 면적이 일치하는가?  

**건물의 권리관계 확인**  
- 등기부등본을 확인하여 **근저당, 가압류, 압류, 가등기, 경매개시결정을 확인했는가?**  
- 건축물대장을 확인하여 **위반건축물을 확인했는가?**

⚠ **위 항목에서 문제가 발견될 경우, 해결 방법과 법적 보호 조치를 상세히 설명해줘.**  


                    내부적으로 모든 분석을 수행한 후, 최종적으로 아래 **JSON 형식으로만** 응답해.
                    ```json
                    {
                      "notice": "발견된 문제 요약",
                      "solution": "해결 방법 요약"
                    }
                    ```
                    **출력 규칙:**
                    - 문제가 있으면 `notice`에 **주요 문제 요약**을 입력하고, `solution`에 **해결 방법**을 제공해.
                    - 문제가 없으면 다음과 같이 응답해:
                      ```json
                      {
                        "notice": "문제 없음",
                        "solution": "계약 진행 가능"
                      }
                      ```
                    - JSON 형식 외의 설명을 포함하지 마.
        """)

        result = analyze_with_gpt(prompt)

        # 분석 결과 추가
        if "contract" in data:
            for key, sub_data in data["contract"].items():
                if isinstance(sub_data, dict):
                    for target_key in ["소재지", "임차할부분", "면적"]:
                        if target_key in sub_data:
                            data["contract"][key][target_key]["notice"] = result.get("notice", "")
                            data["contract"][key][target_key]["solution"] = result.get("solution", "")

        if "building_registry" in data:
            for key, sub_data in data["building_registry"].items():
                if isinstance(sub_data, dict):
                    for target_key in ["대지위치", "도로명주소", "면적"]:
                        if target_key in sub_data:
                            data["building_registry"][key][target_key]["notice"] = result.get("notice", "")
                            data["building_registry"][key][target_key]["solution"] = result.get("solution", "")

        if "registry_document" in data:
            for key, sub_data in data["registry_document"].items():
                if isinstance(sub_data, dict):
                    if "건물주소" in sub_data:
                        data["registry_document"][key]["건물주소"]["notice"] = result.get("notice", "")
                        data["registry_document"][key]["건물주소"]["solution"] = result.get("solution", "")

        return data
    
    def ana_3(data):
        """보증금 및 임대료 분석"""
        if "contract" in data:
            for key, sub_data in data["contract"].items():
                if isinstance(sub_data, dict):
                    payment_info = {}
                    for sub_key in sub_data:
                        if any(sub_key.startswith(prefix) for prefix in ["보증금", "차임", "관리비"]):
                            payment_info[sub_key] = sub_data[sub_key]["text"]
                    
                    if payment_info:
                        prompt = (f"""
                        다음은 부동산 계약의 보증금, 임대료, 관리비 정보입니다:
                        
                        {', '.join(f'{k}: {v}' for k, v in payment_info.items())}"""
                        
"""
                    부동산 계약서에서 임대 목적물의 상태와 권리 관계를 점검하고, 문제가 없는지 확인해줘.  
다음 항목을 기준으로 분석하고, 수정 또는 보완이 필요한 부분을 구체적으로 설명해줘.  

계약서에서 보증금 및 월세 조건이 명확하게 작성되었는지 분석해줘.

보증금과 월세 금액이 명확하게 기재되었는지 확인해줘.
관리비가 별도로 청구되는지, 포함된 항목(전기, 수도, 가스 등)이 적절히 기재되었는지 점검해줘.
입금 계좌가 임대인 명의인지 확인하는 내용이 포함되어 있는지 분석해줘.
분석 후 누락된 정보나 모호한 부분을 지적해줘."
⚠ **위 항목에서 문제가 발견될 경우, 해결 방법과 법적 보호 조치를 상세히 설명해줘.**  


                    내부적으로 모든 분석을 수행한 후, 최종적으로 아래 **JSON 형식으로만** 응답해.
                    ```json
                    {
                      "notice": "발견된 문제 요약",
                      "solution": "해결 방법 요약"
                    }
                    ```
                    **출력 규칙:**
                    - 문제가 있으면 `notice`에 **주요 문제 요약**을 입력하고, `solution`에 **해결 방법**을 제공해.
                    - 문제가 없으면 다음과 같이 응답해:
                      ```json
                      {
                        "notice": "문제 없음",
                        "solution": "계약 진행 가능"
                      }
                      ```
                    - JSON 형식 외의 설명을 포함하지 마.
                    """)
                        result = analyze_with_gpt(prompt)
                        
                        # 결과를 각 필드에 추가
                        for sub_key in payment_info.keys():
                            data["contract"][key][sub_key]["notice"] = result.get("notice", "")
                            data["contract"][key][sub_key]["solution"] = result.get("solution", "")
        return data
    def ana_4(data):
            """계약기간 분석"""
            if "contract" in data:
                for key, sub_data in data["contract"].items():
                    if isinstance(sub_data, dict):
                        period_info = {}
                        for period_key in ["계약기간", "임대차기간"]:
                            if period_key in sub_data:
                                period_info[period_key] = sub_data[period_key]["text"]
                        
                        if period_info:
                            prompt = (f"""
                            다음은 부동산 계약의 기간 정보입니다:
                            
                            {', '.join(f'{k}: {v}' for k, v in period_info.items())}"""
                            
"""
다음 항목을 기준으로 분석하고, 수정 또는 보완이 필요한 부분을 구체적으로 설명해줘.  

계약서의 계약 기간 및 갱신 조건을 검토해줘.

계약 기간이 정확하게 (예: 2025년 2월 21일 ~ 2027년 2월 20일) 기재되어 있는지 확인해줘.
계약 갱신청구권(최소 2년 거주 보장)에 대한 내용이 포함되어 있는지 점검해줘.
중도 해지 시 위약금이나 해지 절차가 명확히 정의되어 있는지 분석해줘.
위 조건을 기준으로 검토하고, 누락된 사항이 있으면 지적해줘."

⚠ **위 항목에서 문제가 발견될 경우, 법적 보호를 받을 수 있는 방법을 설명해줘.**  


                    내부적으로 모든 분석을 수행한 후, 최종적으로 아래 **JSON 형식으로만** 응답해.
                    ```json
                    {
                      "notice": "발견된 문제 요약",
                      "solution": "해결 방법 요약"
                    }
                    ```
                    **출력 규칙:**
                    - 문제가 있으면 `notice`에 **주요 문제 요약**을 입력하고, `solution`에 **해결 방법**을 제공해.
                    - 문제가 없으면 다음과 같이 응답해:
                      ```json
                      {
                        "notice": "문제 없음",
                        "solution": "계약 진행 가능"
                      }
                      ```
                    - JSON 형식 외의 설명을 포함하지 마.
                    """
                            )
                            result = analyze_with_gpt(prompt)
                            
                           # 결과를 각 필드에 추가
                            for period_key in period_info.keys():
                                data["contract"][key][period_key]["notice"] = result.get("notice", "")
                                data["contract"][key][period_key]["solution"] = result.get("solution", "")
            return data
            
    def ana_5(data):
        """특약사항 분석"""
        if "contract" in data:
            for key, sub_data in data["contract"].items():
                if isinstance(sub_data, dict):
                    special_terms = {}
                    for sub_key in sub_data:
                        if sub_key.startswith("특약"):
                            special_terms[sub_key] = sub_data[sub_key]["text"]
                    
                    if special_terms:
                        prompt = (f"""
                        다음은 부동산 계약의 특약사항입니다:
                        
                        {', '.join(f'{k}: {v}' for k, v in special_terms.items())}"""


                        """
다음 항목을 기준으로 분석하고, 수정 또는 보완이 필요한 부분을 구체적으로 설명해줘.  

계약서의 계약 기간 및 갱신 조건을 검토해줘.

계약 기간이 정확하게 (예: 2025년 2월 21일 ~ 2027년 2월 20일) 기재되어 있는지 확인해줘.
계약 갱신청구권(최소 2년 거주 보장)에 대한 내용이 포함되어 있는지 점검해줘.
중도 해지 시 위약금이나 해지 절차가 명확히 정의되어 있는지 분석해줘.
위 조건을 기준으로 검토하고, 누락된 사항이 있으면 지적해줘."

⚠ **위 항목에서 문제가 발견될 경우, 법적 보호를 받을 수 있는 방법을 설명해줘.**  


                    내부적으로 모든 분석을 수행한 후, 최종적으로 아래 **JSON 형식으로만** 응답해.
                    ```json
                    {
                      "notice": "발견된 문제 요약",
                      "solution": "해결 방법 요약"
                    }
                    ```
                    **출력 규칙:**
                    - 문제가 있으면 `notice`에 **주요 문제 요약**을 입력하고, `solution`에 **해결 방법**을 제공해.
                    - 문제가 없으면 다음과 같이 응답해:
                      ```json
                      {
                        "notice": "문제 없음",
                        "solution": "계약 진행 가능"
                      }
                      ```
                    - JSON 형식 외의 설명을 포함하지 마.
                    """
                        )
                        result = analyze_with_gpt(prompt)
                        
                        # 결과를 각 필드에 추가
                        for sub_key in special_terms.keys():
                            data["contract"][key][sub_key]["notice"] = result.get("notice", "")
                            data["contract"][key][sub_key]["solution"] = result.get("solution", "")
        return data

    data = ana_1(data)
    data = ana_2(data)
    data = ana_3(data)
    data = ana_4(data)
    data = ana_5(data)
    return data

# def process_all_json(input_dir):
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
            ledger_data = {"1": json.load(f)}
        with open(files["reg"], 'r', encoding='utf-8') as f:
            reg_data = json.load(f)

        # 데이터 통합
        merged_data = {
            "coai_result_a": coai_data,
            "ledger_result": ledger_data,
            "reg_result": reg_data
        }

        # 1단계: 소유자 수 조정
        name_count = sum(1 for key in ledger_data["1"].keys() if key.startswith("성명"))
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
                del merged_data["reg_result"][owner["page"]][owner["key"]]
        
        return merged_data
    
    except Exception as e:
        print(f"\n오류 발생: {str(e)}")
        raise

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
