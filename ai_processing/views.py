from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from firebase_admin import firestore
from typing import Dict, Optional
from datetime import datetime, timezone
from .registry_ocr import registry_keyword_ocr
from .contract_ocr import contract_keyword_ocr
from .building_ocr import building_keyword_ocr
from firebase_api.views import fetch_latest_documents
from firebase_api.utils import (
    get_latest_analysis_results,
    save_combined_results,
    save_analysis_result,
    save_ocr_result_to_firestore,
)

@csrf_exempt
@require_http_methods(["POST"])
def run_ocr(request):
    """
    OCR 실행 엔드포인트
    
    프론트엔드에서 필요한 파라미터:
    - user_id: 사용자 ID
    - contract_id: 계약 ID
    - document_type: 문서 타입 (registry_document, contract, building_registry)
    """
    try:
        # 요청 데이터 파싱
        data = json.loads(request.body)
        user_id = data.get('user_id')
        contract_id = data.get('contract_id')
        document_type = data.get('document_type')
        
        # 필수 파라미터 검증
        if not all([user_id, contract_id, document_type]):
            missing_params = []
            if not user_id: missing_params.append("user_id")
            if not contract_id: missing_params.append("contract_id")
            if not document_type: missing_params.append("document_type")
            return JsonResponse({
                "error": f"필수 파라미터가 누락되었습니다: {', '.join(missing_params)}"
            }, status=400)
        
        # fetch_latest_documents 호출을 위한 request 객체 수정
        request.GET = request.GET.copy()
        request.GET['user_id'] = user_id
        request.GET['contract_id'] = contract_id

        response = fetch_latest_documents(request)
        
        # 디버깅을 위한 로그 추가
        print("fetch_latest_documents response:", response.content)
        try:
            response_data = json.loads(response.content)
            if 'classified_documents' not in response_data:
                return JsonResponse({"error": "문서 URL을 찾을 수 없습니다"}, status=404)
            document_urls = response_data['classified_documents']
        except json.JSONDecodeError as e:
            return JsonResponse({"error": f"응답 파싱 실패: {str(e)}"}, status=500)
        
        # 요청된 문서 타입의 URL 확인
        if document_type not in document_urls or not document_urls[document_type]:
            return JsonResponse(
                {"error": f"{document_type} 타입의 문서를 찾을 수 없습니다"}, 
                status=404
            )

        # 문서 타입별 OCR 실행
        result = None
        if document_type == "registry_document":
            result = registry_keyword_ocr(
                document_urls["registry_document"],
                "registry_document",
                user_id,
                contract_id
            )
        elif document_type == "contract":
            result = contract_keyword_ocr(
                document_urls["contract"],
                "contract",
                user_id,
                contract_id
            )
        elif document_type == "building_registry":
            result = building_keyword_ocr(
                document_urls["building_registry"],
                "building_registry",
                user_id,
                contract_id
            )
        else:
            return JsonResponse({"error": "지원하지 않는 문서 타입입니다"}, status=400)

        if not result:
            return JsonResponse({"error": "OCR 처리 실패"}, status=500)

        # OCR 결과 저장
        if result:
            for page_number, page_result in result.items():
                page_num = int(page_number.replace('page', ''))
                
                # 해당 페이지의 URL 찾기
                page_url = next(
                    (url for url in document_urls[document_type] 
                     if f"page{page_num}" in url),
                    None
                )
                
                current_time = datetime.now(timezone.utc)

                # 저장할 데이터 구조화
                save_data = {
                "pageNumber": page_num,
                "document_type": document_type,
                "userId": user_id,
                "status": "completed",
                "createdAt": current_time,  # UTC 시간 사용
                "updatedAt": current_time,
                "imageUrl": page_url,
                "ocr_result": page_result
                }
                
                save_success = save_ocr_result_to_firestore(
                    user_id=user_id,
                    contract_id=contract_id,
                    document_type=document_type,
                    page_number=page_num,
                    json_data=save_data
                )

                if not save_success:
                    return JsonResponse({"error": f"OCR 결과 저장 실패 (페이지 {page_num})"}, status=500)
            
        return JsonResponse({
            "status": "success",
            "message": f"{document_type} OCR 처리 완료",
            "user_id": user_id,
            "contract_id": contract_id,
            "result": result
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "잘못된 JSON 형식입니다"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
@csrf_exempt
@require_http_methods(["POST"])
def start_analysis(request):
    """
    AI 분석 엔드포인트
    """
    return JsonResponse({"message": "분석 기능은 아직 구현되지 않았습니다."})


@csrf_exempt
@require_http_methods(["POST"])
def fake_start_analysis(request):
    """AI 분석 엔드포인트"""
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        contract_id = data.get('contract_id')

        if not all([user_id, contract_id]):
            return JsonResponse({
                "error": "필수 파라미터가 누락되었습니다"
            }, status=400)

        # OCR 결과 가져오기
        results = get_latest_analysis_results(user_id, contract_id, "building_registry")
        
        if not results:
            return JsonResponse({
                "error": "OCR 결과를 찾을 수 없습니다"
            }, status=404)

        # 저장할 데이터 구조화 - combined_data가 아닌 results를 직접 저장
        save_success = save_combined_results(
            user_id=user_id,
            contract_id=contract_id,
            combined_data=results  # 이미 적절한 구조를 가진 results를 직접 저장
        )

        if not save_success:
            return JsonResponse({
                "error": "분석 결과 저장 실패"
            }, status=500)

        return JsonResponse({
            "status": "success",
            "message": "OCR 결과 통합 완료",
            "data": results
        })

    except json.JSONDecodeError:
        return JsonResponse({
            "error": "잘못된 JSON 형식입니다"
        }, status=400)
    except Exception as e:
        return JsonResponse({
            "error": str(e)
        }, status=500)