# @csrf_exempt
# def fetch_and_process_latest_images(request):
#     """
#     ✅ Firestore에서 사용자의 가장 최근 촬영 세션의 이미지를 가져와 OCR 실행 후 반환
#     """
#     try:
#         user_id = request.GET.get("user_id")  # 유저 ID 기준 필터링
#         session_threshold = timedelta(minutes=5)  # 5분 이내 업로드된 이미지를 같은 세션으로 판단

#         docs_ref = db.collection("scanned_documents")  # Firestore 컬렉션 접근
#         query = docs_ref.order_by("uploadDate", direction=firestore.Query.DESCENDING)  # 최신순 정렬

#         if user_id:
#             query = query.where("userId", "==", user_id)  # 특정 유저 ID로 필터링

#         docs = list(query.stream())  # 모든 문서 가져오기

#         if not docs:
#             return JsonResponse({"error": "No images found"}, status=404)

#         # ✅ 최신 세션의 기준 시간 찾기 (가장 최근 업로드된 이미지의 timestamp)
#         latest_upload_time = docs[0].to_dict().get("uploadDate")

#         # ✅ 같은 세션 내에서 업로드된 이미지만 필터링 (예: 5분 이내 업로드된 것들만 같은 세션으로 판단)
#         latest_session_images = []

#         for doc in docs:
#             data = doc.to_dict()
#             image_upload_time = data.get("uploadDate")

#             # 같은 세션(5분 이내) 내에서 업로드된 이미지만 포함
#             if image_upload_time and abs(image_upload_time - latest_upload_time) <= session_threshold:
#                 latest_session_images.append(data["imageUrl"])
#             else:
#                 break  # 최신 세션이 끝났으므로 더 이상 가져오지 않음

#         if not latest_session_images:
#             return JsonResponse({"error": "No images found in recent session"}, status=404)

#         # ✅ Firebase Storage에서 이미지 다운로드 후 OCR 수행
#         ocr_results = []
#         for image_url in latest_session_images:
#             with tempfile.NamedTemporaryFile(delete=True, suffix=".jpg") as temp_file:
#                 response = requests.get(image_url, stream=True)

#                 # ✅ Firebase 이미지 다운로드 확인
#                 if response.status_code != 200:
#                     print(f"❌ 이미지 다운로드 실패: {image_url} (Status Code: {response.status_code})")
#                     continue  # 실패한 이미지는 OCR 수행하지 않고 건너뛰기

#                     temp_file.write(response.content)
#                     temp_file.flush()

#                     # ✅ OCR 수행
#                     ocr_result = registry_ocr(temp_file.name)
#                     if ocr_result.empty:
#                         print(f"❌ OCR 결과가 없음: {image_url}")
#                     else:
#                         print(f"✅ OCR 성공: {image_url}")
                        
#                     ocr_results.append(ocr_result.to_dict(orient="records"))  # DataFrame → JSON 변환

#         return JsonResponse({"ocr_results": ocr_results}, status=200)

#     except Exception as e:
#         return JsonResponse({"error": str(e)}, status=500)
