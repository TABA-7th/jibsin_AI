import os
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt
import numpy as np
import firebase_admin
from firebase_admin import credentials, firestore, storage
import json
import datetime
import uuid
import tempfile

# Firebase 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIREBASE_KEY_PATH = os.path.join(BASE_DIR, "firebase_key.json")

# Firebase 앱 초기화 (이미 초기화되지 않았다면)
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'jibsin.firebasestorage.app'  # Firebase 스토리지 버킷 이름
    })
db = firestore.client()
bucket = storage.bucket()

def upload_image_to_firebase(image, user_id, contract_id, doc_type, page_num):
    """
    이미지를 Firebase Storage에 업로드하고 URL을 반환합니다.
    
    Args:
        image (PIL.Image): 업로드할 이미지
        user_id (str): 사용자 ID
        contract_id (str): 계약서 ID
        doc_type (str): 문서 타입
        page_num (int): 페이지 번호
        
    Returns:
        str: 업로드된 이미지의 URL
    """
    try:
        # 임시 파일로 이미지 저장
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            temp_filename = temp_file.name
            image.save(temp_filename, format='PNG')
        
        # Storage 경로 생성
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        storage_path = f"bounding_box_images/{user_id}/{contract_id}/{doc_type}_page{page_num}_{timestamp}.png"
        
        # 이미지 업로드
        blob = bucket.blob(storage_path)
        blob.upload_from_filename(temp_filename)
        
        # 임시 파일 삭제
        os.unlink(temp_filename)
        
        # 이미지 URL 생성
        blob.make_public()
        image_url = blob.public_url
        
        print(f"이미지 업로드 성공: {image_url}")
        return image_url
    
    except Exception as e:
        print(f"이미지 업로드 실패: {e}")
        import traceback
        traceback.print_exc()
        return None

def save_bounding_box_info_to_firestore(user_id, contract_id, doc_type, page_num, image_url):
    """
    바운딩 박스 이미지 정보를 Firestore에 저장합니다.
    
    Args:
        user_id (str): 사용자 ID
        contract_id (str): 계약서 ID
        doc_type (str): 문서 타입
        page_num (int): 페이지 번호
        image_url (str): 이미지 URL
        
    Returns:
        bool: 저장 성공 여부
    """
    try:
        # bounding_box_images 컬렉션 참조
        doc_ref = (
            db.collection("users")
            .document(user_id)
            .collection("contracts")
            .document(contract_id)
            .collection("bounding_box_images")
            .document(f"{doc_type}_page{page_num}")
        )
        
        # 데이터 저장
        doc_ref.set({
            'userId': user_id,
            'contractId': contract_id,
            'documentType': doc_type,
            'pageNumber': page_num,
            'imageUrl': image_url,
            'createdAt': firestore.SERVER_TIMESTAMP,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        
        print(f"바운딩 박스 정보 저장 성공: {doc_type} 페이지 {page_num}")
        return True
    
    except Exception as e:
        print(f"바운딩 박스 정보 저장 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

def process_image_with_boxes_and_upload(image_url, ocr_result, doc_type, page_num, user_id, contract_id):
    """
    이미지를 다운로드하고 바운딩 박스를 그린 후 Firebase에 업로드합니다.
    
    Args:
        image_url (str): 원본 이미지 URL
        ocr_result (dict): OCR 결과 데이터
        doc_type (str): 문서 타입
        page_num (int): 페이지 번호
        user_id (str): 사용자 ID
        contract_id (str): 계약서 ID
    """
    try:
        print(f"{doc_type} 페이지 {page_num} 처리 중...")
        print(f"이미지 URL: {image_url}")
        
        # 이미지 다운로드
        response = requests.get(image_url)
        if response.status_code != 200:
            print(f"이미지 다운로드 실패 (상태 코드: {response.status_code})")
            return
            
        image = Image.open(BytesIO(response.content))
        
        # 바운딩 박스 그리기
        draw = ImageDraw.Draw(image)
        
        # 바운딩 박스 정보 추출 및 그리기
        boxes_drawn = draw_bounding_boxes_from_ocr(draw, ocr_result)
        
        if not boxes_drawn:
            print(f"{doc_type} 페이지 {page_num}에 그릴 바운딩 박스가 없습니다.")
            print(f"OCR 결과 구조: {json.dumps(ocr_result, indent=2)[:500]}...")  # 구조 디버깅
            return
        
        # 로컬에 이미지 저장
        output_dir = "bounding_box_results"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{doc_type}_page_{page_num}.png")
        image.save(output_path)
        print(f"바운딩 박스가 그려진 이미지가 저장되었습니다: {output_path}")
        
        # Firebase Storage에 이미지 업로드
        firebase_image_url = upload_image_to_firebase(image, user_id, contract_id, doc_type, page_num)
        
        if firebase_image_url:
            # Firestore에 이미지 URL 저장
            save_success = save_bounding_box_info_to_firestore(
                user_id, contract_id, doc_type, page_num, firebase_image_url
            )
            
            if save_success:
                print(f"Firebase에 {doc_type} 페이지 {page_num}의 바운딩 박스 이미지가 업로드되었습니다.")
            
        # 미리보기 표시
        plt.figure(figsize=(12, 16))
        plt.imshow(np.array(image))
        plt.axis('off')
        plt.title(f"{doc_type} - 페이지 {page_num}")
        plt.show()
        
    except Exception as e:
        print(f"이미지 처리 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()

def draw_bounding_boxes_from_ocr(draw, ocr_result):
    """
    OCR 결과에서 바운딩 박스 정보를 추출하여 그립니다.
    
    Args:
        draw (PIL.ImageDraw): 그리기 객체
        ocr_result (dict): OCR 결과 데이터
        
    Returns:
        bool: 바운딩 박스를 그렸는지 여부
    """
    boxes_drawn = False
    
    # 디버깅을 위한 로그 출력
    print(f"OCR 결과 키: {list(ocr_result.keys())}")
    
    # OCR 결과 구조에 따라 바운딩 박스 처리
    # 1. 키워드별 바운딩 박스 구조 확인 (주요 사용 구조)
    for keyword, data in ocr_result.items():
        if isinstance(data, dict) and 'bounding_box' in data:
            bbox = data['bounding_box']
            
            # x1, y1, x2, y2 형식의 경우
            if all(k in bbox for k in ['x1', 'y1', 'x2', 'y2']):
                # 박스 그리기
                left = bbox['x1']
                top = bbox['y1']
                right = bbox['x2']
                bottom = bbox['y2']
                draw.rectangle([(left, top), (right, bottom)], outline=(0, 0, 255, 128), width=2)
                
                # 텍스트 추가
                try:
                    font = ImageFont.load_default()
                    text = data.get('text', keyword)
                    text_position = (left, top - 15)
                    draw.text(text_position, text, fill=(255, 0, 0), font=font)
                except Exception as e:
                    print(f"텍스트 그리기 실패: {e}")
                
                boxes_drawn = True
    
    # 2. blocks -> paragraphs -> words 구조 확인
    if 'blocks' in ocr_result:
        for block in ocr_result['blocks']:
            if 'boundingBox' in block:
                draw_box(draw, block['boundingBox'], color=(255, 0, 0, 128), width=3)  # 빨간색 반투명
                boxes_drawn = True
                
            if 'paragraphs' in block:
                for paragraph in block['paragraphs']:
                    if 'boundingBox' in paragraph:
                        draw_box(draw, paragraph['boundingBox'], color=(0, 255, 0, 128), width=2)  # 녹색 반투명
                        boxes_drawn = True
                    
                    if 'words' in paragraph:
                        for word in paragraph['words']:
                            if 'boundingBox' in word:
                                draw_box(draw, word['boundingBox'], color=(0, 0, 255, 128), width=1)  # 파란색 반투명
                                boxes_drawn = True
    
    # 3. textAnnotations 구조 확인 (Google Vision API 형식)
    elif 'textAnnotations' in ocr_result:
        for annotation in ocr_result['textAnnotations']:
            if 'boundingPoly' in annotation:
                vertices = annotation.get('boundingPoly', {}).get('vertices', [])
                if vertices:
                    points = [(vertex.get('x', 0), vertex.get('y', 0)) for vertex in vertices]
                    draw.polygon(points, outline=(0, 0, 255, 128), width=1)
                    boxes_drawn = True
    
    # 4. boundingBoxes 직접 저장된 형식 확인
    elif 'boundingBoxes' in ocr_result:
        for box in ocr_result['boundingBoxes']:
            draw_box(draw, box, color=(0, 0, 255, 128), width=1)
            boxes_drawn = True
            
    # 5. 플랫한 구조의 바운딩 박스 확인
    elif 'text' in ocr_result and 'boundingBox' in ocr_result:
        draw_box(draw, ocr_result['boundingBox'], color=(0, 0, 255, 128), width=1)
        boxes_drawn = True
        
    # 6. 추출된 텍스트와 별도의 좌표 구조 확인
    elif 'keywordCoordinates' in ocr_result:
        for keyword, coords in ocr_result['keywordCoordinates'].items():
            if isinstance(coords, dict) and all(k in coords for k in ['x', 'y', 'width', 'height']):
                draw_box(draw, coords, color=(0, 0, 255, 128), width=1)
                # 키워드 텍스트 추가
                font = None
                try:
                    # 기본 폰트 로드 (환경에 따라 다를 수 있음)
                    font = ImageFont.load_default()
                except:
                    pass
                
                if font:
                    text_position = (coords['x'], coords['y'] - 15)  # 박스 위에 텍스트 표시
                    draw.text(text_position, keyword, fill=(255, 0, 0), font=font)
                
                boxes_drawn = True
    
    # 7. "boxes" 구조 확인 (보통 JSON 결과에 boxes라는 키가 있는 경우)
    elif 'boxes' in ocr_result:
        for box in ocr_result['boxes']:
            if isinstance(box, dict):
                draw_box(draw, box, color=(0, 0, 255, 128), width=1)
                boxes_drawn = True
    
    # 8. 문서 타입별 특정 키워드 구조 확인 (예: registry_data, contract_data 등)
    for potential_key in ['registry_data', 'contract_data', 'building_data', 'data']:
        if potential_key in ocr_result:
            data_obj = ocr_result[potential_key]
            if isinstance(data_obj, dict):
                for keyword, item in data_obj.items():
                    if isinstance(item, dict) and 'coord' in item:
                        draw_box(draw, item['coord'], color=(255, 0, 255, 128), width=2)  # 보라색
                        
                        # 키워드 텍스트 추가
                        font = None
                        try:
                            font = ImageFont.load_default()
                        except:
                            pass
                            
                        if font and 'coord' in item and isinstance(item['coord'], dict):
                            coord = item['coord']
                            if all(k in coord for k in ['x', 'y']):
                                x, y = coord['x'], coord['y']
                                text_position = (x, y - 15)
                                draw.text(text_position, keyword, fill=(255, 0, 0), font=font)
                                
                        boxes_drawn = True
                        
    return boxes_drawn

def draw_box(draw, bounding_box, color, width=2):
    """
    ImageDraw 객체에 바운딩 박스를 그립니다.
    
    Args:
        draw (PIL.ImageDraw): 그리기 객체
        bounding_box (dict): 바운딩 박스 좌표 (vertices 또는 x, y, width, height 형식)
        color (tuple): RGB 또는 RGBA 색상
        width (int): 선 두께
    """
    try:
        if isinstance(bounding_box, dict):
            if 'vertices' in bounding_box:
                vertices = bounding_box['vertices']
                # vertices가 4개의 점 좌표를 포함하는 경우
                points = [(vertex.get('x', 0), vertex.get('y', 0)) for vertex in vertices]
                draw.polygon(points, outline=color, width=width)
            
            elif 'boundingPoly' in bounding_box:
                vertices = bounding_box['boundingPoly'].get('vertices', [])
                points = [(vertex.get('x', 0), vertex.get('y', 0)) for vertex in vertices]
                draw.polygon(points, outline=color, width=width)
            
            elif all(k in bounding_box for k in ['x', 'y', 'width', 'height']):
                # x, y, width, height 형식의 경우
                x = bounding_box['x']
                y = bounding_box['y']
                w = bounding_box['width']
                h = bounding_box['height']
                draw.rectangle([(x, y), (x + w, y + h)], outline=color, width=width)
                
            elif all(k in bounding_box for k in ['left', 'top', 'right', 'bottom']):
                # left, top, right, bottom 형식의 경우
                left = bounding_box['left']
                top = bounding_box['top']
                right = bounding_box['right']
                bottom = bounding_box['bottom']
                draw.rectangle([(left, top), (right, bottom)], outline=color, width=width)
            
            elif all(k in bounding_box for k in ['x', 'y']):
                # 단순 x, y 좌표만 있는 경우 (크기 지정)
                x = bounding_box['x']
                y = bounding_box['y']
                size = bounding_box.get('size', 50)  # 기본 크기
                draw.rectangle([(x, y), (x + size, y + size)], outline=color, width=width)
        
        elif isinstance(bounding_box, list):
            if len(bounding_box) == 4:
                # [x, y, width, height] 또는 [left, top, right, bottom] 형식의 경우
                if all(isinstance(v, (int, float)) for v in bounding_box):
                    # 타입에 따라 해석 방법이 다름 (context에 따라 판단)
                    if bounding_box[2] > bounding_box[0] and bounding_box[3] > bounding_box[1]:
                        # [left, top, right, bottom] 형식으로 판단
                        left, top, right, bottom = bounding_box
                        draw.rectangle([(left, top), (right, bottom)], outline=color, width=width)
                    else:
                        # [x, y, width, height] 형식으로 판단
                        x, y, w, h = bounding_box
                        draw.rectangle([(x, y), (x + w, y + h)], outline=color, width=width)
    except Exception as e:
        print(f"바운딩 박스 그리기 중 오류 발생: {str(e)}")

def fetch_document_urls_from_ocr_results(user_id, contract_id):
    """
    ocr_results 컬렉션에서 문서 URL 가져오기
    """
    try:
        # ocr_results 컬렉션 참조
        ocr_results_ref = (
            db.collection("users")
            .document(user_id)
            .collection("contracts")
            .document(contract_id)
            .collection("ocr_results")
        )
        
        # 모든 OCR 결과 가져오기
        ocr_docs = ocr_results_ref.stream()
        
        document_urls = {}
        document_results = {}
        
        for doc in ocr_docs:
            data = doc.to_dict()
            doc_type = data.get("document_type")
            if not doc_type:
                continue
                
            # 해당 문서 타입이 document_urls에 없으면 추가
            if doc_type not in document_urls:
                document_urls[doc_type] = []
                document_results[doc_type] = {}
                
            # 이미지 URL 추가
            if "imageUrl" in data:
                document_urls[doc_type].append(data["imageUrl"])
                
            # OCR 결과 저장
            if "ocr_result" in data and "pageNumber" in data:
                page_key = f"page{data['pageNumber']}"
                document_results[doc_type][page_key] = data
                
        return document_urls, document_results
    
    except Exception as e:
        print(f"ocr_results에서 URL 가져오기 실패: {str(e)}")
        return {}, {}

def visualize_bounding_boxes_and_upload(user_id, contract_id):
    """
    Firebase에서 이미지와 OCR 결과를 가져와 바운딩 박스를 시각화하고 업로드합니다.
    
    Args:
        user_id (str): 사용자 ID
        contract_id (str): 계약서 ID
    """
    try:
        # 1. Firestore에서 문서 URL 가져오기
        print(f"사용자 {user_id}의 계약서 {contract_id}에 대한 문서 URL 가져오기 시작...")
        
        # 계약서 문서 확인
        contract_ref = (
            db.collection("users")
            .document(user_id)
            .collection("contracts")
            .document(contract_id)
        )
        contract_doc = contract_ref.get()
        
        if not contract_doc.exists:
            print(f"계약서를 찾을 수 없습니다: {contract_id}")
            return False
            
        # 먼저 ocr_results 컬렉션에서 이미지 URL 가져오기 시도
        document_urls, document_results = fetch_document_urls_from_ocr_results(user_id, contract_id)
        
        if not document_urls:
            # ocr_results에서 URL을 가져오지 못한 경우 AI_analysis 컬렉션 확인
            print("ocr_results에서 URL을 찾을 수 없습니다. AI_analysis 확인 중...")
            
            # AI 분석 결과 가져오기 (최신 것)
            analysis_ref = (
                contract_ref
                .collection("AI_analysis")
                .order_by("createdAt", direction=firestore.Query.DESCENDING)
                .limit(1)
            )
            
            analysis_docs = analysis_ref.stream()
            analysis_doc = next(analysis_docs, None)
            
            if not analysis_doc:
                print(f"AI 분석 결과를 찾을 수 없습니다.")
                return False
                
            analysis_data = analysis_doc.to_dict()
            
            # 문서 URL 가져오기
            if "imageUrls" in analysis_data:
                document_urls = analysis_data["imageUrls"]
            else:
                print("AI_analysis에서도 문서 URL을 찾을 수 없습니다.")
                return False

            # 분석 결과 가져오기
            if "result" not in analysis_data:
                print("AI_analysis에서 분석 결과를 찾을 수 없습니다.")
                return False
                
            document_results = analysis_data["result"]
        
        if not document_urls:
            print("어떤 컬렉션에서도 문서 URL을 찾을 수 없습니다.")
            return False
            
        # 2. 각 문서 타입별로 처리
        document_types = ["registry_document", "contract", "building_registry"]
        processed_any = False
        
        for doc_type in document_types:
            if doc_type not in document_results:
                print(f"{doc_type} 타입의 분석 결과가 없습니다.")
                continue
                
            if doc_type not in document_urls or not document_urls[doc_type]:
                print(f"{doc_type} 타입의 URL이 없습니다.")
                continue
                
            # 각 페이지 처리
            for page_key, page_data in document_results[doc_type].items():
                # 페이지 번호 추출 (예: "page1" -> 1)
                if not page_key.startswith("page"):
                    continue
                    
                try:
                    page_num = int(page_key[4:])
                except ValueError:
                    continue
                
                # 페이지에 해당하는 URL 찾기
                page_url = None
                # 먼저 ocr_results에서 직접 확인
                if "imageUrl" in page_data:
                    page_url = page_data["imageUrl"]
                # 없으면 URL 목록에서 검색
                else:
                    for url in document_urls[doc_type]:
                        if f"page{page_num}" in url:
                            page_url = url
                            break
                
                if not page_url:
                    print(f"{doc_type}의 {page_key}에 대한 URL을 찾을 수 없습니다.")
                    continue
                
                # OCR 결과 가져오기
                ocr_result = None
                
                # 먼저 페이지 데이터에서 OCR 결과 확인
                if "ocr_result" in page_data:
                    ocr_result = page_data["ocr_result"]
                # 없으면 ocr_results 컬렉션에서 직접 가져오기
                else:
                    ocr_ref = (
                        contract_ref
                        .collection("ocr_results")
                        .where("document_type", "==", doc_type)
                        .where("pageNumber", "==", page_num)
                        .limit(1)
                    )
                    
                    ocr_docs = ocr_ref.stream()
                    ocr_doc = next(ocr_docs, None)
                    
                    if ocr_doc:
                        ocr_data = ocr_doc.to_dict()
                        if "ocr_result" in ocr_data:
                            ocr_result = ocr_data["ocr_result"]
                
                if not ocr_result:
                    print(f"{doc_type}의 {page_key}에 대한 OCR 결과를 찾을 수 없습니다.")
                    continue
                
                # 이미지 다운로드 및 바운딩 박스 그리기 후 Firebase에 업로드
                process_image_with_boxes_and_upload(
                    page_url, ocr_result, doc_type, page_num, user_id, contract_id
                )
                processed_any = True
        
        if not processed_any:
            print("처리할 문서가 없습니다.")
            return False
            
        return True
    
    except Exception as e:
        print(f"바운딩 박스 시각화 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

# 실행 코드
if __name__ == "__main__":
    USER_ID = "test_user"
    CONTRACT_ID = "test_user-CT-2502275712"
    
    print(f"사용자 {USER_ID}의 계약서 {CONTRACT_ID}에 대한 바운딩 박스 시각화 및 업로드를 시작합니다...")
    success = visualize_bounding_boxes_and_upload(USER_ID, CONTRACT_ID)
    
    if success:
        print("바운딩 박스 시각화 및 Firebase 업로드가 완료되었습니다.")
    else:
        print("바운딩 박스 시각화 중 오류가 발생했습니다.")