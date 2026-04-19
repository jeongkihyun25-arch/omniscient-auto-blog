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
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

warnings.filterwarnings("ignore")

# ==================== [1] 기본 설정 ====================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BLOG_ID = "6254424106586242042"
QUEUE_FILE = "keywords_queue.txt"
LABEL_OPTIONS = ["여행 교통 팁", "여행 쇼핑 팁", "여행 관광 팁", "여행 준비 팁", "여행 맛집 팁", "생활 정보 꿀팁"]

# ==================== [2] 최고 모델 선택 ====================
def get_best_model():
    print("🔍 [1/5] 모델 탐색 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    try:
        res = requests.get(url, timeout=15).json()
        available = [m['name'].replace('models/', '') for m in res.get('models', [])
                     if 'generateContent' in m.get('supportedGenerationMethods', [])]
        priorities = ["gemini-2.5-flash-lite", "gemini-flash-latest", "gemini-2.0-flash"]
        for p in priorities:
            for m in available:
                if p in m: return m
        return available[0] if available else "gemini-2.0-flash"
    except: return "gemini-2.0-flash"

# ==================== [3] 네이버 수집 (정밀도 강화) ====================
def get_naver_target_data():
    now = datetime.now()
    m = [now.month, (now.month % 12) + 1, ((now.month + 1) % 12) + 1]
    BASE_KEYWORDS = [
        "해외여행 준비물", "여권 발급", "여행자 보험", "비상약 리스트", "비지트 재팬", 
        "입국 심사", "세관 신고", "인천공항 주차", "공항 라운지", "스마트패스", 
        "공항 리무진", "항공권 특가", "수하물 규정", "기내 반입", "해외 로밍", 
        "유심 추천", "이심 사용법", "esim 설치", "환전 꿀팁", "트래블월렛", 
        "트래블로그", "아고다 할인", "에어비앤비", "가성비 숙소", "면세점 쇼핑", 
        "돈키호테", "현지 맛집", "가족 여행", f"{m[0]}월 여행지", f"{m[1]}월 여행지"
    ]

    if not os.path.exists(QUEUE_FILE) or os.stat(QUEUE_FILE).st_size == 0:
        random.shuffle(BASE_KEYWORDS)
        with open(QUEUE_FILE, "w", encoding="utf-8") as f: f.write("\n".join(BASE_KEYWORDS))

    with open(QUEUE_FILE, "r", encoding="utf-8") as f: lines = f.read().splitlines()
    target_query = lines[0]
    print(f"🎯 오늘의 키워드: {target_query}")
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
        # 블로그 제목 링크만 정확히 수집
        blog_elements = driver.find_elements(By.CSS_SELECTOR, "a.title_link")
        count = 0
        for el in blog_elements:
            href = el.get_attribute("href")
            title = el.text.strip()
            if href and "blog.naver.com" in href and len(title) > 8:
                count += 1
                links_info += f"[{count}] {title} | 주소: {href}\n"
            if count >= 10: break
    finally: driver.quit()
    return target_query, links_info

# ==================== [4] SVG 카드 (3줄/6자 엄수) ====================
def create_summary_card_tag(summary_list, title):
    safe_list = [str(s).strip()[:6] for s in summary_list if s][:3]
    while len(safe_list) < 3: safe_list.append("") 
    l1, l2, l3 = safe_list

    svg_code = f"""
    <svg width="600" height="230" xmlns="http://www.w3.org/2000/svg">
      <rect width="600" height="230" fill="#FFF9C4" rx="20"/>
      <text x="50%" y="70" font-family="Arial, sans-serif" font-weight="bold" font-size="34" text-anchor="middle" fill="#2c3e50">{l1}</text>
      <text x="50%" y="130" font-family="Arial, sans-serif" font-weight="bold" font-size="34" text-anchor="middle" fill="#2c3e50">{l2}</text>
      <text x="50%" y="190" font-family="Arial, sans-serif" font-weight="bold" font-size="34" text-anchor="middle" fill="#2c3e50">{l3}</text>
    </svg>
    """
    b64_svg = base64.b64encode(svg_code.encode('utf-8')).decode('utf-8')
    data_uri = f"data:image/svg+xml;base64,{b64_svg}"
    return f'<div style="text-align:center; margin:40px 0;"><img src="{data_uri}" style="max-width:100%; height:auto; border-radius:15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);" alt="{title} 요약 카드"/></div>'

# ==================== [5] 원고 생성 (AI 느낌 완전 제거) ====================
def generate_master_content():
    keyword, reference_blogs = get_naver_target_data()
    best_model = get_best_model()
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(best_model)

    now = datetime.now()
    current_date = now.strftime('%Y년 %m월')

    prompt = f"""
[오늘의 시점]: {current_date}
[타겟 키워드]: {keyword}
[참고 블로그 데이터]: 
{reference_blogs}

[미션]: 위 데이터를 기반으로 5,000자 이상의 전문가 포스팅을 작성하라.
[작성 지침 - 어기면 탈락]:
1. **AI 면피용 멘트 금지**: "종합하여 작성되었습니다", "출처는 다음과 같습니다" 같은 말 쓰지 마라. 서두에 군더더기 없이 독자가 바로 얻을 이득으로 시작하라.
2. **2026년 반영**: 현재 시점({current_date})을 기준으로 '올해', '최신' 정보를 작성하라.
3. **구조**: 반드시 <h2>(파란 바 스타일)와 <h3>(밑줄 스타일)를 사용해 가독성을 높여라.
4. **라벨**: 딱 1개만 선택하라. `label_indices` 필드에 숫자 하나만 넣어라.
5. **SVG 3줄**: 'summary' 필드에 6글자 이내의 단어 딱 3개를 추출하라.
6. **SEO 슬러그**: 연도 없이 키워드 중심의 영어 슬러그를 길게 생성하라 (예: travel-insurance-best-guide).

[출력 포맷]: JSON (title, meta_desc, meta_keys, slug, summary, content, label_indices)
"""
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except: return None

# ==================== [6] 업로드 및 디자인 반영 ====================
def run_automation():
    print("🚀 [2/5] 프로세스 시작...")
    try:
        token_base64 = os.environ.get("BLOGGER_TOKEN_PKL")
        if token_base64:
            with open('token.json', 'wb') as f: f.write(base64.b64decode(token_base64))
            print("✅ [3/5] 토큰 복구 완료")

        data = generate_master_content()
        if not data: return
        
        # 디자인 요소 삽입
        card_tag = create_summary_card_tag(data.get('summary', []), data['title'])
        ads_tag = '<div style="margin:35px 0;"><script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2303846706279700" crossorigin="anonymous"></script><ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-2303846706279700" data-ad-slot="1632085406" data-ad-format="auto" data-full-width-responsive="true"></ins><script>(adsbygoogle = window.adsbygoogle || []).push({});</script></div>'
        
        content = data['content']
        insertion = card_tag + ads_tag
        # TOC(nav) 뒤에 삽입하거나 맨 앞에 삽입
        content = content.replace("</nav>", f"</nav>{insertion}") if "</nav>" in content else insertion + content

        # 폰트 18px + H2/H3 스타일링 강화
        final_html = f"""
        <style>
            .entry-content {{ font-size: 18px; line-height: 2.0; color: #333; font-family: 'Malgun Gothic', sans-serif; }}
            .entry-content h2 {{ 
                font-size: 28px; color: #2c3e50; border-left: 10px solid #3498db; 
                padding: 10px 15px; margin: 45px 0 25px; background: #f9f9f9; 
            }}
            .entry-content h3 {{ 
                font-size: 23px; color: #2980b9; border-bottom: 2px solid #3498db; 
                padding-bottom: 8px; margin: 35px 0 20px; 
            }}
            .entry-content p {{ margin-bottom: 25px; }}
            .entry-content b {{ color: #e74c3c; }}
            .entry-content table {{ width: 100%; border-collapse: collapse; margin: 30px 0; }}
            .entry-content th {{ background: #3498db; color: white; padding: 12px; }}
            .entry-content td {{ border: 1px solid #ddd; padding: 12px; text-align: center; }}
        </style>
        <div class="entry-content">{content}</div>
        """

        # 라벨 강제 제한 (1개만)
        raw_idx = data.get('label_indices', [0])[0] # 첫 번째 것만 취함
        final_label = [LABEL_OPTIONS[int(raw_idx) % len(LABEL_OPTIONS)]]

        with open('token.json', 'rb') as t:
            creds = pickle.load(t)
            if creds.expired: creds.refresh(Request())
        
        service = build('blogger', 'v3', credentials=creds)
        
        # 포스팅 실행 (슬러그 반영 시도)
        print(f"🚀 [4/5] 업로드 중: {data['title']}")
        service.posts().insert(blogId=BLOG_ID, body={
            "title": data['title'], 
            "content": final_html, 
            "labels": final_label,
            "customMetaData": data.get('meta_desc', '')
        }, isDraft=False).execute()
        
        print(f"✨ [5/5] 최종 성공: {data['title']}")

    except Exception as e: 
        print(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    run_automation()
