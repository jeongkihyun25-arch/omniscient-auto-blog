import os
import pickle
import time
import json
import base64
import requests
import re
import warnings
import random
import urllib.parse
from datetime import datetime
import google.generativeai as genai
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

warnings.filterwarnings("ignore")

# ==================== [1] 기본 설정 (Secrets 활용) ====================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BLOG_ID = "6254424106586242042"
QUEUE_FILE = "keywords_queue.txt"
LABEL_OPTIONS = ["여행 교통 팁", "여행 쇼핑 팁", "여행 관광 팁", "여행 준비 팁", "여행 맛집 팁", "생활 정보 꿀팁"]

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# ==================== [2] 모델 선택 (기현님 코드 고대로) ====================
def get_best_model():
    print("🔍 [1/5] 최고 모델 탐색 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    try:
        res = requests.get(url, timeout=15).json()
        available = [m['name'].replace('models/', '') for m in res.get('models', [])
                     if 'generateContent' in m.get('supportedGenerationMethods', [])]
        priorities = ["gemini-2.5-flash-lite", "gemini-flash-latest", "gemini-2.0-flash"]
        for p in priorities:
            for m in available:
                if p in m:
                    print(f"🎯 선택 모델: {m}")
                    return m
        return available[0] if available else "gemini-2.0-flash"
    except:
        return "gemini-2.0-flash"

# ==================== [3] 네이버 상위 10개 정밀 수집 (셔플 로직) ====================
def get_naver_target_data():
    now = datetime.now()
    m = [now.month, (now.month % 12) + 1, ((now.month + 1) % 12) + 1]
    BASE_KEYWORDS = [
        "해외여행 준비물", "여권 발급", "여행자 보험", "비상약 리스트", "비지트 재팬", 
        "입국 심사", "세관 신고", "인천공항 주차", "공항 라운지", "스마트패스", 
        "공항 리무진", "항공권 특가", "수하물 규정", "기내 반입", "해외 로밍", 
        "유심 추천", "이심 사용법", "esim 설치", "환전 꿀팁", "트래블월렛", 
        "트래블로그", "아고다 할인", "에어비앤비", "가성비 숙소", "면세점 쇼핑", 
        "돈키호테", "현지 맛집", "가족 여행", f"{m[0]}월 여행지", f"{m[1]}월 여행지", f"{m[2]}월 여행지"
    ]

    if not os.path.exists(QUEUE_FILE) or os.stat(QUEUE_FILE).st_size == 0:
        random.shuffle(BASE_KEYWORDS)
        with open(QUEUE_FILE, "w", encoding="utf-8") as f: f.write("\n".join(BASE_KEYWORDS))

    with open(QUEUE_FILE, "r", encoding="utf-8") as f: lines = f.read().splitlines()
    target_query = lines[0]
    with open(QUEUE_FILE, "w", encoding="utf-8") as f: f.write("\n".join(lines[1:]))

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    links_info = ""
    try:
        url = f"https://search.naver.com/search.naver?ssc=tab.blog.all&query={urllib.parse.quote(target_query)}"
        driver.get(url)
        time.sleep(5)
        all_links = driver.find_elements(By.TAG_NAME, "a")
        count = 0
        for link in all_links:
            href = link.get_attribute("href")
            title = link.text.strip()
            if href and "blog.naver.com" in href and len(title) > 8:
                clean_url = href.split('?')[0].rstrip('/')
                if re.search(r'/\d+$', clean_url):
                    count += 1
                    links_info += f"[{count}] 제목: {title} | URL: {clean_url}\n"
            if count >= 10: break
    finally:
        driver.quit()
    return target_query, links_info

# ==================== [4] 원고 생성 (5,000자 + 제목/키워드 모방) ====================
def generate_master_content():
    keyword, reference_blogs = get_naver_target_data()
    best_model = get_best_model()
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(best_model)

    prompt = f"""
[현재 날짜]: {datetime.now().strftime("%Y-%m-%d")}
[메인 키워드]: {keyword}
[참고할 네이버 상위 10개 리스트]:
{reference_blogs}

[미션]: 위 10개 블로그 중 가장 잘 쓴 글 1개를 골라 내용을 분석하고, 5,000자 이상의 프리미엄 원고를 작성해.

[작성 규칙]:
1. **제목(Title) 모방**: 상위권 블로그들의 제목 스타일(키워드 배치, 문구)을 참고하여 가장 클릭률이 높을 법한 비슷한 느낌의 제목을 지어.
2. **내용 모방 및 확장**: 참고 글의 핵심 정보를 뼈대로 삼되, 네가 아는 정보를 듬뿍 추가해 훨씬 풍성하게 써. (출처 절대 언급 금지)
3. **퍼머링크(Slug)**: 키워드가 포함된 영어 슬러그를 생성해.
4. **라벨(Label)**: 제공된 옵션 중 가장 적절한 인덱스를 2개 골라.
5. HTML 형식 유지 (intro 태그, 새창 링크 8개, 표 2개, 리스트 5개)

[출력 포맷]: JSON
{{
  "title": "모방한 임팩트 제목",
  "meta_desc": "SEO 설명 (150자)",
  "meta_keys": "{keyword}, 여행 팁",
  "slug": "url-slug-with-keyword",
  "summary": ["키워드1", "키워드2", "키워드3"],
  "content": "HTML 본문",
  "label_indices": [인덱스1, 인덱스2]
}}
"""
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"}, request_options={"timeout": 600})
        return json.loads(response.text)
    except Exception as e:
        print(f"⚠️ 생성 실패: {e}")
        return None

# ==================== [5] 실행 및 업로드 ====================
def run_automation():
    data = generate_master_content()
    if not data: return

    # (기존 기현님 코드의 이미지 태그 및 광고 삽입 로직 실행)
    content = data['content']
    # ... (생략된 기존 블로그 업로드 코드: creds 로드 및 service.posts().insert 실행) ...
    print(f"🚀 업로드 완료: {data['title']}")

if __name__ == "__main__":
    run_automation()
