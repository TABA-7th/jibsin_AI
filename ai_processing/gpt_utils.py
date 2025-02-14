# gpt_utils.py
import openai
import base64

def read_image_multi(client, image_paths, MODEL, df_list):
    """
    여러 장의 등기부 등본 이미지를 OCR 처리 후 GPT에 전달하여 분석
    :param client: OpenAI API 클라이언트
    :param image_paths: 이미지 파일 경로 리스트 (등기부 등본 여러 장)
    :param MODEL: GPT 모델 (예: gpt-4o)
    :param df_list: OCR 결과 리스트 (각 페이지의 OCR DataFrame)
    :return: GPT 응답 (JSON 형식)
    """
    
    base64_images = []
    for image_path in image_paths:
        with open(image_path, "rb") as image_file:
            base64_images.append(base64.b64encode(image_file.read()).decode("utf-8"))
    
    # 모든 OCR 데이터를 JSON 문자열로 변환
    df_json_list = [df.to_json(orient="records", force_ascii=False) for df in df_list]
    
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": (
                        f"다음은 등기부 등본의 OCR 분석을 위한 데이터입니다.\n\n"
                        f"✅ **OCR 데이터 (페이지별):**\n"
                        + "\n\n".join([f"📄 **페이지 {i+1}**\n{df_json}" for i, df_json in enumerate(df_json_list)])
                        + f"\n\n💡 **작업 목표:**\n"
                        f"- 모든 페이지의 OCR 데이터를 통합하여 정보 추출\n"
                        f"- `소유자현황`보다 y1이 낮은 부분에서 '도로명주소', '호명칭'을 찾아서 연결\n"
                        f"- `공용부분`보다 y1이 낮고 `전유부분`보다 높은 부분에서 '면적(m2)', '성명(명칭)' 정보를 추출\n"
                        f"- 여러 개의 면적이 있으면 가장 위에 있는 값만 사용\n\n"
                        f"🔹 **반환 형식:**\n"
                        f"JSON 형태로 출력하며, 각 항목에 바운딩 박스를 포함해야 합니다.\n\n"
                        f"💡 **반환 예시:**\n"
                        f"{{\n"
                        f"  \"도로명주소\": {{\"text\": \"서울특별시 강남구 테헤란로 123\", \"bounding_box\": {{\"x1\": 100, \"y1\": 200, \"x2\": 400, \"y2\": 250}}}},\n"
                        f"  \"호명칭\": {{\"text\": \"101호\", \"bounding_box\": {{\"x1\": 120, \"y1\": 220, \"x2\": 380, \"y2\": 270}}}},\n"
                        f"  \"면적(m2)\": {{\"text\": \"85.3\", \"bounding_box\": {{\"x1\": 140, \"y1\": 240, \"x2\": 360, \"y2\": 290}}}},\n"
                        f"  \"성명(명칭)\": {{\"text\": \"홍길동\", \"bounding_box\": {{\"x1\": 150, \"y1\": 250, \"x2\": 350, \"y2\": 300}}}}\n"
                        f"}}\n\n"
                        f"⚠️ **주의사항:**\n"
                        f"- 페이지 구분 없이 OCR 데이터를 통합하여 분석\n"
                        f"- 여러 개의 바운딩 박스가 존재하면 가장 적절한 값 선택\n"
                        f"- JSON 형식이 정확하도록 반환해야 함"
                    )},
                    *[
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}}
                        for img in base64_images
                    ]
                ]
            }
        ],
        max_tokens=1500
    )

    return response.choices[0].message.content.strip()
