from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from firebase_admin import firestore
from typing import Dict, Optional

from .registry_ocr import registry_keyword_ocr
from .contract_ocr import contract_keyword_ocr
from .building_ocr import building_keyword_ocr
from firebase_api.views import fetch_latest_documents
from firebase_api.utils import (
    get_latest_analysis_results,
    save_combined_results,
    save_analysis_result
)


@csrf_exempt
@require_http_methods(["POST"])
def run_ocr(request):
    """
    OCR 실행 엔드포인트
    """
    try:
        # 요청 데이터 파싱
        data = json.loads(request.body)
        document_type = data.get('document_type')
        
        if not document_type:
            return JsonResponse({"error": "document_type이 필요합니다"}, status=400)

        # Firebase에서 최신 문서 URL 가져오기
        response = fetch_latest_documents(request)
        if not response or not isinstance(response, JsonResponse):
            return JsonResponse({"error": "문서를 찾을 수 없습니다"}, status=404)

        document_urls = json.loads(response.content)['classified_documents']
        
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
                "registry_document"
            )
        elif document_type == "contract":
            result = contract_keyword_ocr(
                document_urls["contract"],
                "contract"
            )
        elif document_type == "building_registry":
            result = building_keyword_ocr(
                document_urls["building_registry"],
                "building_registry"
            )
        else:
            return JsonResponse({"error": "지원하지 않는 문서 타입입니다"}, status=400)

        if not result:
            return JsonResponse({"error": "OCR 처리 실패"}, status=500)

        return JsonResponse({
            "status": "success",
    
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