import json
import os
from datetime import datetime

def adjust_owners(merged_data):
    """
    건축물대장의 소유자 수에 맞춰 등기부등본의 소유자 수 조정
    가장 최근 소유자만 유지
    """
    try:
        # 건축물대장에서 소유자 수 확인
        building_owner_count = sum(1 for key in merged_data["building_registry"]["1"].keys() 
                                 if key.startswith("성명"))

        # 등기부등본에서 소유자 정보 수집
        owners = []
        for page_key, page_content in merged_data["registry_document"].items():
            if not isinstance(page_content, dict):
                continue
            
            for key, value in page_content.items():
                if key.startswith("소유자_"):
                    owner_info = {
                        "page": page_key,
                        "key": key,
                        "y1": value["bounding_box"]["y1"],
                        "text": value.get("text", ""),
                        "data": value
                    }
                    owners.append(owner_info)
                    print(f"- 소유자 발견: {owner_info['text']} ({owner_info['page']} - {owner_info['key']})")

        # 소유자 정보를 y1 좌표 기준으로 정렬 (위에서 아래로)
        owners.sort(key=lambda x: x["y1"])
        
        # 초과하는 소유자 수 계산
        owners_to_remove = len(owners) - building_owner_count

        # 초과하는 소유자 정보 삭제 (이전 소유자부터)
        if owners_to_remove > 0:
            print(f"\n{owners_to_remove}명의 이전 소유자 정보를 제외합니다")
            for i in range(owners_to_remove):
                owner = owners[i]
                print(f"- 제외: {owner['text']} ({owner['page']} - {owner['key']})")
                del merged_data["registry_document"][owner["page"]][owner["key"]]

        return merged_data

    except Exception as e:
        print(f"소유자 수 조정 중 오류 발생: {str(e)}")
        raise


def validate_documents(merged_data):
    """문서 데이터 검증 및 경고 메시지 추가
    
    검증 항목:
    1. 소유자 정보 일치 여부
    2. 소재지 정보 일치 여부
    3. 면적 정보 일치 여부
    4. 임대차 계약 정보
    5. 발급일자 유효성
    6. 위험 단어 검사
    """
    try:
        # 소유자 수 조정
        merged_data = adjust_owners(merged_data)

        # 1. 소유자 정보 일치 여부 검증
        contract_owner = merged_data["contract"]["1"]["임대인"]["text"]
        building_owner = merged_data["building_registry"]["1"].get("성명1", {}).get("text", "")
        reg_owners = []
        
        # 조정된 등기부등본에서 최신 소유자 정보 확인
        for page_key, page_content in merged_data["registry_document"].items():
            if isinstance(page_content, dict):
                for key, value in page_content.items():
                    if key.startswith("소유자_"):
                        reg_owners.append(value["text"])

        # 임대인이 building_registry나 registry_document에 포함되어 있는지 확인
        owner_match = contract_owner in [building_owner] + reg_owners
        if not owner_match:
            merged_data["contract"]["1"]["임대인"]["notice"] = "[경고] 집주인과 임대인이 다릅니다."
            if "성명1" in merged_data["building_registry"]["1"]:
                merged_data["building_registry"]["1"]["성명1"]["notice"] = "[경고] 집주인과 임대인이 다릅니다."
            for page_key, page_content in merged_data["registry_document"].items():
                if isinstance(page_content, dict):
                    for key, value in page_content.items():
                        if key.startswith("소유자_"):
                            value["notice"] = "[경고] 집주인과 임대인이 다릅니다."

        # 2. 소재지 정보 일치 여부 검증
        contract_address = merged_data["contract"]["1"]["소재지"]["text"]
        reg_address = merged_data["registry_document"]["1페이지"]["건물주소"]["text"]
        building_address = merged_data["building_registry"]["1"]["도로명주소"]["text"]

        # 주소에서 공통 부분 추출 
        if not (building_address in contract_address and any(part in reg_address for part in building_address.split())):
            merged_data["contract"]["1"]["소재지"]["notice"] = "[경고] 건물 주소 정보가 일치하지 않습니다."
            merged_data["registry_document"]["1페이지"]["건물주소"]["notice"] = "[경고] 건물 주소 정보가 일치하지 않습니다."

        # 3. 면적 정보 일치 여부 검증
        contract_area = merged_data["contract"]["1"]["면적"]["text"]
        building_area = merged_data["building_registry"]["1"]["면적"]["text"]

        # 숫자만 추출하여 비교
        contract_area_num = float(''.join(filter(lambda x: x.isdigit() or x == '.', contract_area)))
        building_area_num = float(''.join(filter(lambda x: x.isdigit() or x == '.', building_area)))

        if abs(contract_area_num - building_area_num) > 0.001:  # 소수점 오차 허용
            merged_data["contract"]["1"]["면적"]["notice"] = "[경고] 면적 정보가 다릅니다."
            merged_data["building_registry"]["1"]["면적"]["notice"] = "[경고] 면적 정보가 다릅니다."

        # 4. 임대차 계약 정보 검증
        contract_period = merged_data["contract"]["1"]["계약기간"]["text"]
        reg_period = None
        
        for page in merged_data["registry_document"].values():
            for key, value in page.items():
                if key == "임대차기간":
                    reg_period = value["text"]
                    reg_period_field = value
                    break
            if reg_period:
                break

        if reg_period and contract_period != reg_period:
            merged_data["contract"]["1"]["계약기간"]["notice"] = "[경고] 임대차 계약 기간이 다릅니다."
            reg_period_field["notice"] = "[경고] 임대차 계약 기간이 다릅니다."

        # 5. 발급일자 유효성 확인
        issue_date_str = merged_data["building_registry"]["1"]["발급일자"]["text"]
        issue_date = datetime.strptime(issue_date_str, "%Y년 %m월 %d일")
        current_date = datetime(2025, 2, 20)

        if abs((current_date - issue_date).days) > 0:
            merged_data["building_registry"]["1"]["발급일자"]["notice"] = "[경고] 발급일자가 오래되었습니다."

        # 기본 notice 필드 추가
        def add_default_notice(item):
            if isinstance(item, dict):
                if "text" in item and "notice" not in item:
                    item["notice"] = ""
                for value in item.values():
                    add_default_notice(value)
            elif isinstance(item, list):
                for element in item:
                    add_default_notice(element)

        add_default_notice(merged_data)

        # 6. 위험 단어 검사
        warning_words = ["신탁", "압류", "가압류", "가처분", "위반건축물"]
        warning_count = 0

        def check_warnings(item):
            nonlocal warning_count
            if isinstance(item, dict):
                if "text" in item and isinstance(item["text"], str):
                    for word in warning_words:
                        if word in item["text"] and item["text"] != "NA":
                            item["notice"] = f"[경고] 위험 단어 '{word}' 발견"
                            warning_count += 1
                            print(f"- 경고 단어 발견: '{word}' in '{item['text']}'")
                            break
                for value in item.values():
                    check_warnings(value)
            elif isinstance(item, list):
                for element in item:
                    check_warnings(element)

        check_warnings(merged_data)
        if warning_count == 0:
            print("- 경고 단어가 발견되지 않았습니다")

        return merged_data

    except Exception as e:
        print(f"검증 중 오류 발생: {str(e)}")
        raise