import json
import os
from datetime import datetime

def adjust_owners(merged_data):
    """
    건축물대장의 소유자 수에 맞춰 등기부등본의 소유자 수 조정
    가장 최근 소유자만 유지
    """
    try:
        # 건축물대장에서 소유자 수 확인 - page1에서 직접 확인
        building_owner_count = 1  # 기본값 설정
        building_registry = merged_data.get("building_registry", {}).get("page1", {})
        if building_registry:
            # 성명1 또는 성명 필드 존재 여부 확인
            if "성명1" in building_registry or "성명" in building_registry:
                building_owner_count = 1

        # 등기부등본에서 소유자 정보 수집
        owners = []
        registry_doc = merged_data.get("registry_document", {})
        
        # 소유자 필드 직접 확인
        if "page1" in registry_doc and "소유자" in registry_doc["page1"]:
            owner_info = {
                "page": "page1",
                "key": "소유자",
                "y1": registry_doc["page1"]["소유자"]["bounding_box"]["y1"],
                "text": registry_doc["page1"]["소유자"].get("text", ""),
                "data": registry_doc["page1"]["소유자"]
            }
            owners.append(owner_info)
            print(f"- 소유자 발견: {owner_info['text']} (page1 - 소유자)")

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
        contract_owner = merged_data.get("contract", {}).get("page1", {}).get("임대인", {}).get("text", "")
        
        # 건축물대장 소유자
        building_registry = merged_data.get("building_registry", {}).get("page1", {})
        building_owner = (building_registry.get("성명1", {}).get("text", "") or 
                        building_registry.get("성명", {}).get("text", ""))
        
        # 등기부등본 소유자
        registry_doc = merged_data.get("registry_document", {}).get("page1", {})
        reg_owner = registry_doc.get("소유자", {}).get("text", "")

        # 임대인이 building_registry나 registry_document에 포함되어 있는지 확인
        owner_match = contract_owner in [building_owner, reg_owner]
        if not owner_match and contract_owner:
            if "임대인" in merged_data.get("contract", {}).get("page1", {}):
                merged_data["contract"]["page1"]["임대인"]["notice"] = "[경고] 집주인과 임대인이 다릅니다."
            
            if building_owner and "성명1" in building_registry:
                building_registry["성명1"]["notice"] = "[경고] 집주인과 임대인이 다릅니다."
            
            if reg_owner and "소유자" in registry_doc:
                registry_doc["소유자"]["notice"] = "[경고] 집주인과 임대인이 다릅니다."

        # 2. 소재지 정보 일치 여부 검증
        contract_address = merged_data.get("contract", {}).get("page1", {}).get("소재지", {}).get("text", "")
        reg_address = registry_doc.get("건물주소", {}).get("text", "")
        
        # 건축물대장 주소 확인
        building_address = (building_registry.get("도로명주소", {}).get("text", "") or 
                          building_registry.get("대지위치", {}).get("text", "") or 
                          building_registry.get("주소", {}).get("text", ""))

        # 주소 일치 여부 검증
        if building_address and contract_address and reg_address:
            if not (building_address in contract_address and 
                   any(part in reg_address for part in building_address.split())):
                if "소재지" in merged_data.get("contract", {}).get("page1", {}):
                    merged_data["contract"]["page1"]["소재지"]["notice"] = "[경고] 건물 주소 정보가 일치하지 않습니다."
                if "건물주소" in registry_doc:
                    registry_doc["건물주소"]["notice"] = "[경고] 건물 주소 정보가 일치하지 않습니다."

        # 3. 면적 정보 일치 여부 검증
        try:
            contract_area = merged_data.get("contract", {}).get("page1", {}).get("면적", {}).get("text", "0")
            building_area = building_registry.get("면적", {}).get("text", "0")

            # 숫자만 추출하여 비교
            contract_area_num = float(''.join(filter(lambda x: x.isdigit() or x == '.', contract_area)))
            building_area_num = float(''.join(filter(lambda x: x.isdigit() or x == '.', building_area)))

            if abs(contract_area_num - building_area_num) > 0.001:  # 소수점 오차 허용
                if "면적" in merged_data.get("contract", {}).get("page1", {}):
                    merged_data["contract"]["page1"]["면적"]["notice"] = "[경고] 면적 정보가 다릅니다."
                if "면적" in building_registry:
                    building_registry["면적"]["notice"] = "[경고] 면적 정보가 다릅니다."
        except (ValueError, TypeError) as e:
            print(f"면적 정보 비교 중 오류 발생: {e}")

        # 4. 임대차 계약 정보 검증
        contract_period = merged_data.get("contract", {}).get("page1", {}).get("계약기간", {}).get("text", "")
        lease_period = merged_data.get("contract", {}).get("page1", {}).get("임대차기간", {}).get("text", "")

        if contract_period and lease_period and contract_period != lease_period:
            if "계약기간" in merged_data.get("contract", {}).get("page1", {}):
                merged_data["contract"]["page1"]["계약기간"]["notice"] = "[경고] 임대차 계약 기간이 다릅니다."
            if "임대차기간" in merged_data.get("contract", {}).get("page1", {}):
                merged_data["contract"]["page1"]["임대차기간"]["notice"] = "[경고] 임대차 계약 기간이 다릅니다."

        # 5. 발급일자 유효성 확인
        if "발급일자" in building_registry:
            try:
                issue_date_str = building_registry["발급일자"]["text"]
                issue_date = datetime.strptime(issue_date_str, "%Y년 %m월 %d일")
                current_date = datetime(2025, 2, 20)  # 현재 날짜

                if (current_date - issue_date).days > 30:  # 30일 이상 지난 경우
                    building_registry["발급일자"]["notice"] = "[경고] 발급일자가 30일 이상 지났습니다."
            except ValueError as e:
                print(f"발급일자 확인 중 오류 발생: {e}")

        # 6. 위험 단어 검사
        warning_words = ["신탁", "압류", "가압류", "가처분", "위반건축물"]
        
        def check_warnings(data):
            """재귀적으로 위험 단어 검사"""
            if isinstance(data, dict):
                if "text" in data and isinstance(data["text"], str) and data["text"] != "NA":
                    for word in warning_words:
                        if word in data["text"]:
                            data["notice"] = f"[경고] 위험 단어 '{word}' 발견"
                            print(f"- 경고 단어 발견: '{word}' in '{data['text']}'")
                for value in data.values():
                    check_warnings(value)
            elif isinstance(data, list):
                for item in data:
                    check_warnings(item)

        check_warnings(merged_data)

        # 모든 필드에 기본 notice 추가
        def add_default_notice(data):
            """재귀적으로 notice 필드 추가"""
            if isinstance(data, dict):
                if "text" in data and "notice" not in data:
                    data["notice"] = ""
                for value in data.values():
                    add_default_notice(value)
            elif isinstance(data, list):
                for item in data:
                    add_default_notice(item)

        add_default_notice(merged_data)

        return merged_data

    except Exception as e:
        print(f"검증 중 오류 발생: {str(e)}")
        raise