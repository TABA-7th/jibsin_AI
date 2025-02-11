import base64
import openai

def read_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()

def process_image(client, image_path, model, df):
    """이미지 OCR 및 분석"""
    content = read_file("data/p_1.txt")

    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode("utf-8")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": "출력은 요청 정보만 [':',':']의 딕셔너리 형태로 출력해줘"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{df}는 주어진 이미지의 ocr 데이터야. {content}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }
        ],
        max_tokens=1000
    )

    return response.choices[0].message.content
