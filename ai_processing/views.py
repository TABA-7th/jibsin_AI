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
    update_analysis_status
)
from .validation import validate_documents
import traceback
from .ai_analysis import (clean_json, remove_bounding_boxes, restore_bounding_boxes, adjust_owner_count, building, price)

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
    통합 분석 프로세스 실행
    1. 문서 URL 가져오기
    2. OCR 실행
    3. AI 분석 실행
    """
    try:
        print("Starting analysis process...")
        data = json.loads(request.body)
        user_id = data.get('userId')
        contract_id = data.get('contractId')
        

        print(f"Received request - user_id: {user_id}, contract_id: {contract_id}")

        if not user_id or not contract_id:
            return JsonResponse({
                'success': False,
                'message': '사용자 ID와 계약 ID가 필요합니다.'
            }, status=400)

        # 상태 업데이트: 분석 시작
        update_analysis_status(user_id, contract_id, "processing")

        # 1. 최신 문서 URL 가져오기
        request.GET = request.GET.copy()
        request.GET['user_id'] = user_id
        request.GET['contract_id'] = contract_id

        print("Fetching document URLs...")
        response = fetch_latest_documents(request)
        print(f"fetch_latest_documents response: {response.content}")
        try:
            response_data = json.loads(response.content)
            if 'classified_documents' not in response_data:
                print("No classified_documents found in response")
                update_analysis_status(user_id, contract_id, "failed")
                return JsonResponse({"error": "문서 URL을 찾을 수 없습니다"}, status=404)
            document_urls = response_data['classified_documents']
            print(f"Found document URLs: {document_urls}")

            # URL이 하나도 없는지 확인
            if not any(urls for urls in document_urls.values()):
                print("No document URLs found for any type")
                update_analysis_status(user_id, contract_id, "failed")
                return JsonResponse({"error": "문서를 찾을 수 없습니다"}, status=404)
                                    
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            update_analysis_status(user_id, contract_id, "failed")
            return JsonResponse({"error": f"응답 파싱 실패: {str(e)}"}, status=500)

        # 2. 각 문서 타입별 OCR 실행
        ocr_results = {}
        document_types = ["registry_document", "contract", "building_registry"]
        
        for doc_type in document_types:
            try:    
                if doc_type not in document_urls or not document_urls[doc_type]:
                    print(f"Warning: {doc_type} URL not found")
                    continue

                # OCR 실행
                if doc_type == "registry_document":
                    result = registry_keyword_ocr(document_urls[doc_type], doc_type, user_id, contract_id)
                elif doc_type == "contract":
                    result = contract_keyword_ocr(document_urls[doc_type], doc_type, user_id, contract_id)
                elif doc_type == "building_registry":
                    result = building_keyword_ocr(document_urls[doc_type], doc_type, user_id, contract_id)

                print(f"OCR Result for {doc_type}: {result}") 
                
                if not result:
                    update_analysis_status(user_id, contract_id, "failed")
                    return JsonResponse({
                        "error": f"{doc_type} OCR 처리 실패"
                    }, status=500)
            except Exception as ocr_error: 
                print(f"OCR 처리 중 오류 발생 - {doc_type}: {str(ocr_error)}")
                traceback.print_exc() 
                continue

            # OCR 결과 저장
            for page_number, page_result in result.items():
                page_num = int(page_number.replace('page', ''))
                page_url = next(
                    (url for url in document_urls[doc_type] 
                     if f"page{page_num}" in url),
                    None
                )
                
                save_data = {
                    "pageNumber": page_num,
                    "document_type": doc_type,
                    "userId": user_id,
                    "status": "completed",
                    "createdAt": datetime.now(timezone.utc),
                    "updatedAt": datetime.now(timezone.utc),
                    "imageUrl": page_url,
                    "ocr_result": page_result
                }
                
                save_success = save_ocr_result_to_firestore(
                    user_id=user_id,
                    contract_id=contract_id,
                    document_type=doc_type,
                    page_number=page_num,
                    json_data=save_data
                )

                if not save_success:
                    update_analysis_status(user_id, contract_id, "failed")
                    return JsonResponse({
                        "error": f"OCR 결과 저장 실패 (문서: {doc_type}, 페이지: {page_num})"
                    }, status=500)

            ocr_results[doc_type] = result
        
        # OCR 결과 전체 저장
        if ocr_results:
            combined_result = {
                "document_type": "combined",
                "userId": user_id,
                "results": ocr_results,
                "analysisStatus": "completed"
            }
            
            # 통합 OCR 결과 저장
            save_combined_results(user_id, contract_id, combined_result)

        # 3. AI 분석 실행
        try:
            # OCR 결과 가져오기
            contract_results = get_latest_analysis_results(user_id, contract_id, "contract")
            building_results = get_latest_analysis_results(user_id, contract_id, "building_registry")
            registry_results = get_latest_analysis_results(user_id, contract_id, "registry_document")

            if not all([contract_results, building_results, registry_results]):
                update_analysis_status(user_id, contract_id, "failed")
                return JsonResponse({
                    'success': False,
                    'message': 'OCR 결과를 찾을 수 없습니다.'
                }, status=404)

            # 데이터 통합
            merged_data = {
                "contract": contract_results.get("contract", {}), # 계약서
                "building_registry": building_results.get("building_registry", {}), #건축물대장
                "registry_document": registry_results.get("registry_document", {}) #등기부 등본
            }

            # 문서 검증 수행
            analysis_result = validate_documents(merged_data)
            
            # AI 분석 결과 저장
            save_analysis_result(user_id, contract_id, analysis_result, image_urls=document_urls)
            
            # 분석 완료 상태 업데이트
            update_analysis_status(user_id, contract_id, "completed")

            return JsonResponse({
                'success': True,
                'message': '문서 분석이 완료되었습니다.',
                'data': analysis_result
            })

        except Exception as e:
            print(f"AI 분석 중 오류 발생: {str(e)}")
            update_analysis_status(user_id, contract_id, "failed")
            return JsonResponse({
                'success': False,
                'message': f'AI 분석 중 오류가 발생했습니다: {str(e)}'
            }, status=500)

    except Exception as e:
        print(f"전체 분석 과정 중 오류 발생: {str(e)}")
        traceback.print_exc()
        if user_id and contract_id:
            update_analysis_status(user_id, contract_id, "failed")
        
        return JsonResponse({
            'success': False,
            'message': f'분석 처리 중 오류가 발생했습니다: {str(e)}'
        }, status=500)
    
def test_ai(request):
    return JsonResponse({"message": "AI test endpoint is working!"})

@csrf_exempt
@require_http_methods(["POST"])
def start_ai_analysis(request):
    """
    통합 분석 프로세스 실행
    1. 문서 URL 가져오기
    2. OCR 실행
    3. AI 분석 실행
    """
    try:
        print("Starting analysis process...")
        data = json.loads(request.body)
        user_id = data.get('userId')
        contract_id = data.get('contractId')
        
        print(f"Received request - user_id: {user_id}, contract_id: {contract_id}")

        if not user_id or not contract_id:
            return JsonResponse({
                'success': False,
                'message': '사용자 ID와 계약 ID가 필요합니다.'
            }, status=400)

        # 상태 업데이트: 분석 시작
        update_analysis_status(user_id, contract_id, "processing")

        # 1. 최신 문서 URL 가져오기
        request.GET = request.GET.copy()
        request.GET['user_id'] = user_id
        request.GET['contract_id'] = contract_id

        print("Fetching document URLs...")
        response = fetch_latest_documents(request)
        print(f"fetch_latest_documents response: {response.content}")
        
        try:
            response_data = json.loads(response.content)
            if 'classified_documents' not in response_data:
                print("No classified_documents found in response")
                update_analysis_status(user_id, contract_id, "failed")
                return JsonResponse({"error": "문서 URL을 찾을 수 없습니다"}, status=404)
            document_urls = response_data['classified_documents']
            print(f"Found document URLs: {document_urls}")

            # URL이 하나도 없는지 확인
            if not any(urls for urls in document_urls.values()):
                print("No document URLs found for any type")
                update_analysis_status(user_id, contract_id, "failed")
                return JsonResponse({"error": "문서를 찾을 수 없습니다"}, status=404)
                                    
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            update_analysis_status(user_id, contract_id, "failed")
            return JsonResponse({"error": f"응답 파싱 실패: {str(e)}"}, status=500)

        # 2. 각 문서 타입별 OCR 실행
        ocr_results = {}
        document_types = ["registry_document", "contract", "building_registry"]
        
        for doc_type in document_types:
            try:    
                if doc_type not in document_urls or not document_urls[doc_type]:
                    print(f"Warning: {doc_type} URL not found")
                    continue

                # OCR 실행
                if doc_type == "registry_document":
                    result = registry_keyword_ocr(document_urls[doc_type], doc_type, user_id, contract_id)
                elif doc_type == "contract":
                    result = contract_keyword_ocr(document_urls[doc_type], doc_type, user_id, contract_id)
                elif doc_type == "building_registry":
                    result = building_keyword_ocr(document_urls[doc_type], doc_type, user_id, contract_id)

                print(f"OCR Result for {doc_type}: {result}") 
                
                if not result:
                    update_analysis_status(user_id, contract_id, "failed")
                    return JsonResponse({
                        "error": f"{doc_type} OCR 처리 실패"
                    }, status=500)
            except Exception as ocr_error: 
                print(f"OCR 처리 중 오류 발생 - {doc_type}: {str(ocr_error)}")
                traceback.print_exc() 
                continue

            # OCR 결과 저장
            for page_number, page_result in result.items():
                page_num = int(page_number.replace('page', ''))
                page_url = next(
                    (url for url in document_urls[doc_type] 
                     if f"page{page_num}" in url),
                    None
                )
                
                save_data = {
                    "pageNumber": page_num,
                    "document_type": doc_type,
                    "userId": user_id,
                    "status": "completed",
                    "createdAt": datetime.now(timezone.utc),
                    "updatedAt": datetime.now(timezone.utc),
                    "imageUrl": page_url,
                    "ocr_result": page_result
                }
                
                save_success = save_ocr_result_to_firestore(
                    user_id=user_id,
                    contract_id=contract_id,
                    document_type=doc_type,
                    page_number=page_num,
                    json_data=save_data
                )

                if not save_success:
                    update_analysis_status(user_id, contract_id, "failed")
                    return JsonResponse({
                        "error": f"OCR 결과 저장 실패 (문서: {doc_type}, 페이지: {page_num})"
                    }, status=500)

            ocr_results[doc_type] = result
        
        # OCR 결과 전체 저장
        if ocr_results:
            combined_result = {
                "document_type": "combined",
                "userId": user_id,
                "results": ocr_results,
                "analysisStatus": "completed"
            }
            
            # 통합 OCR 결과 저장
            save_combined_results(user_id, contract_id, combined_result)

        # 3. AI 분석 실행
        try:
            # OCR 결과 가져오기
            contract_results = get_latest_analysis_results(user_id, contract_id, "contract")
            building_results = get_latest_analysis_results(user_id, contract_id, "building_registry")
            registry_results = get_latest_analysis_results(user_id, contract_id, "registry_document")

            if not all([contract_results, building_results, registry_results]):
                update_analysis_status(user_id, contract_id, "failed")
                return JsonResponse({
                    'success': False,
                    'message': 'OCR 결과를 찾을 수 없습니다.'
                }, status=404)

    
            merged_data = {
                "contract": contract_results.get("contract", {}),
                "building_registry": building_results.get("building_registry", {}),
                "registry_document": registry_results.get("registry_document", {})
            }
            # 소유자 수 조정
            merged_data = adjust_owner_count(
            merged_data["building_registry"],
            merged_data["registry_document"],
            merged_data 
            )

            # Bounding Box 제거 및 저장
            bounding_boxes = remove_bounding_boxes(merged_data)
            
            # 주소 일치 여부 확인
            res_1 = building(merged_data)

            # 공시가격 조회
            if res_1 != "nan":
                try:
                    res = price(res_1)
                    cost = int(res['공시가격'])
                except (ValueError, TypeError, KeyError):
                    cost = 'nan'
                    print("공시가격 조회 실패")
            else:
                cost = 'nan'
                print("주소 불일치로 공시가격 조회 불가")

            # AI 분석 실행
            analysis_result = clean_json(merged_data, res_1, cost)
            
            # Bounding Box 복원
            restore_bounding_boxes(analysis_result, bounding_boxes)
            
            # AI 분석 결과 저장
            save_analysis_result(user_id, contract_id, analysis_result, image_urls=document_urls)
            
            # 분석 완료 상태 업데이트
            update_analysis_status(user_id, contract_id, "completed")

            return JsonResponse({
                'success': True,
                'message': '문서 분석이 완료되었습니다.',
                'data': analysis_result
            })

        except Exception as e:
            print(f"AI 분석 중 오류 발생: {str(e)}")
            update_analysis_status(user_id, contract_id, "failed")
            return JsonResponse({
                'success': False,
                'message': f'AI 분석 중 오류가 발생했습니다: {str(e)}'
            }, status=500)

    except Exception as e:
        print(f"전체 분석 과정 중 오류 발생: {str(e)}")
        traceback.print_exc()
        if user_id and contract_id:
            update_analysis_status(user_id, contract_id, "failed")
        
        return JsonResponse({
            'success': False,
            'message': f'분석 처리 중 오류가 발생했습니다: {str(e)}'
        }, status=500)



# @csrf_exempt
# @require_http_methods(["POST"])
# def fake_start_analysis(request):
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