import numpy as np
import easyocr
from fastapi.responses import JSONResponse
from fastapi import FastAPI, File, UploadFile
from PIL import Image
import cv2
import io
from paddleocr import PaddleOCR
from sklearn.cluster import DBSCAN
import re
# ocr reader
# reader = easyocr.Reader(['ko', 'en'])

# OCR
# PaddleOCR 초기화 - 여러 언어 지원
ocr = None
try:
    ocr = PaddleOCR(
        use_angle_cls=True, 
        lang="korean",
        )
    print("✅ PaddleOCR korean_english 모델 초기화 성공")
except Exception as e:
    print(f"❌ PaddleOCR 초기화 실패: {e}")
    raise RuntimeError("OCR 초기화 실패")

stopwords = ["포장오", "드시겠어요", "드시겠어요?", "피y위ha", "릉요표", "피iyi위hay", "피iyhay"]


async def run_ocr(file: UploadFile = File(...)):
    global ocr

    image_bytes = await file.read()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image_np = np.array(image)

    # ----------- 밝은 부분만 마스킹 시작 -----------
    gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)

    # CLAHE로 대비 향상
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # 밝은 영역만 추출
    _, mask = cv2.threshold(enhanced, 90, 255, cv2.THRESH_BINARY)
    bright_only = cv2.bitwise_and(image_np, image_np, mask=mask)


    # OCR 수행
    ocr_result = ocr.ocr(bright_only)
    # print("OCR 결과:", ocr_result)


    # ocr_result = ocr.ocr(image_np)

    buttons = []

    for line in ocr_result:
        for box, (text, score) in line:
            if (score > 0.7 and
                re.search(r"[가-힣0-9]", text) and
                not re.match(r".+[을를이가은는도까로요겠]$", text) and
                text.strip() not in stopwords): # 신뢰도 기준
                x_coords = [int(p[0]) for p in box]
                y_coords = [int(p[1]) for p in box]
                x_min, x_max = min(x_coords), max(x_coords)
                y_min, y_max = min(y_coords), max(y_coords)
                buttons.append({
                    "text": text,
                    "confidence": float(score),
                    "bbox": {
                        "x": x_min,
                        "y": y_min,
                        "width": x_max - x_min,
                        "height": y_max - y_min
                    },
                    "center": [(x_min + x_max) // 2, (y_min + y_max) // 2]
                })

    print("buttons:", buttons)
    # 중심 좌표 추출
    centers = np.array([b["center"] for b in buttons])

    # DBSCAN 클러스터링 (eps: 거리 임계값, min_samples: 최소 그룹 크기)
    if len(centers) > 0:
        clustering = DBSCAN(eps=103, min_samples=1).fit(centers)
        for idx, label in enumerate(clustering.labels_):
            buttons[idx]["group"] = int(label)

    # group별로 묶어서 반환
    grouped_buttons = {}
    for b in buttons:
        group_id = b.get("group", 0)
        grouped_buttons.setdefault(group_id, []).append(b)

    # 그룹별 text, bbox 합치기
    merged_groups = []
    for group_id, group in grouped_buttons.items():
        texts = [item["text"] for item in group]
        # bbox 합치기: 모든 박스를 감싸는 최소 사각형
        x_min = min(item["bbox"]["x"] for item in group)
        y_min = min(item["bbox"]["y"] for item in group)
        x_max = max(item["bbox"]["x"] + item["bbox"]["width"] for item in group)
        y_max = max(item["bbox"]["y"] + item["bbox"]["height"] for item in group)
        merged_groups.append({
            "group": group_id,
            "text": " ".join(texts),
            "bbox": {
                "x": x_min,
                "y": y_min,
                "width": x_max - x_min,
                "height": y_max - y_min
            },
            "count": len(group)
        })

    sidebar_img, box = detect_right_sidebar(image_np)
    return JSONResponse(content={
        "groups": merged_groups,
        "count": len(buttons),
        "sidebar_exists": box
    })

# 프로젝트가 완료될때까지 지우시마시오. 언제 이 방법으로 돌아갈지 모름 !!
# async def run_ocr(file: UploadFile = File(...)):
#     # image load
#     image_bytes = await file.read()
#     image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
#     image_np = np.array(image)

#     # opencv용 bgr로 변환
#     image_bgr = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)

#     gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

#     # 3. CLAHE 객체 생성 (clipLimit 높일수록 대비 강해짐)
#     clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
#     contrast_enhanced = clahe.apply(gray)

#     # 밝은 영역만 마스킹 (threshold 적용)
#     _, bright_mask = cv2.threshold(contrast_enhanced, 100, 255, cv2.THRESH_BINARY)
#     bright_only = cv2.bitwise_and(image_bgr, image_bgr, mask=bright_mask)
#     bright_rgb = cv2.cvtColor(bright_only, cv2.COLOR_BGR2RGB)

#     # detect text and position
#     results = reader.readtext(bright_rgb)

#     buttons = []
#     for (bbox, text, prob) in results:
#         if prob > 0.5:  # 신뢰도 기준
#             (tl, tr, br, bl) = bbox
#             x_min = int(min(tl[0], bl[0]))
#             y_min = int(min(tl[1], tr[1]))
#             x_max = int(max(tr[0], br[0]))
#             y_max = int(max(bl[1], br[1]))
#             buttons.append({
#                 "text": text,
#                 "bbox": {
#                     "x": x_min,
#                     "y": y_min,
#                     "width": x_max - x_min,
#                     "height": y_max - y_min
#                 }
#             })

#     visible_button_texts = [b['text'] for b in buttons]

#     return JSONResponse(content={
#         "buttons": buttons,
#     })

def detect_right_sidebar(image_np, sidebar_width=30, gray_min=100, gray_max=200, min_height_ratio=0.3):
    """
    이미지에서 회색 계열의 사이드바(스크롤바 등)를 찾아 bounding box 추출
    """
    h, w = image_np.shape[:2]
    gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)

    # 회색 계열 마스크 만들기
    mask = cv2.inRange(gray, gray_min, gray_max)

    # 윤곽선 탐지
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    sidebar_boxes = []

    for cnt in contours:
        x, y, ww, hh = cv2.boundingRect(cnt)
        if hh > h * min_height_ratio and ww >=1:
            sidebar_boxes.append((x, y, ww, hh))

    # 가장 오른쪽에 있는 박스를 사이드바로 간주
    if sidebar_boxes:
        sidebar = max(sidebar_boxes, key=lambda box: box[0])
        x, y, ww, hh = sidebar
        sidebar_img = image_np[y:y+hh, x:x+ww]
        return sidebar_img, (x, y, ww, hh)
    else:
        return None, None