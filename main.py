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
    print("🔍 [1/5] 최고 모델 탐색 중...")
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

# ==================== [3] 네이버 수집 (큐 로직 포함) ====================
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

    # 큐 파일 관리
    if not os.path.exists(QUEUE_FILE) or os.stat(QUEUE_FILE).st_size == 0:
        random.shuffle(BASE_KEYWORDS)
        with open(QUEUE_FILE, "w", encoding="utf-8") as f: f.write("\n".join(BASE_KEYWORDS))

    with open(QUEUE_FILE, "r", encoding="utf-8") as f: lines = f.read().splitlines()
    target_query = lines[0]
    print(f"🎯 오늘의 키워드: {target_query}")
    
    with open(QUEUE_FILE, "w", encoding="utf-8") as f: f.write("\n".join(lines[1:]))

    # 셀레니움 수집
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
                    links_info += f"[{count}] {title} ({clean_url})\n"
            if count >= 10: break
    finally: driver.quit()
    return target_query, links_info

# ==================== [4] 유동적 SVG 요약 카드 ====================
def create_summary_card_tag(summary_list, title):
    safe_list = [str(s).strip()[:6] for s in summary_list if s][:3]
    while len(safe_list) < 3: safe_list.append("") 
    l1, l2, l3 = safe_list

    svg_code = f"""
    <svg width="600" height="230" xmlns="http://www.w3.org/2000/svg">
      <rect width="600" height="230" fill="#FFF9C4" rx="15"/>
      <text x="50%" y="65" font-family="Arial" font-weight="bold" font-size="28" text-anchor="middle" fill="#333">{l1}</text>
      <text x="50%" y="120" font-family="Arial" font-weight="bold" font-size="26" text-anchor="middle" fill="#333">{l2}</text>
      <text x="50%" y="175" font-family="Arial" font-weight="bold" font-size="24" text-anchor="middle" fill="#333">{l3}</text>
    </svg>
    """
    b64_svg = base64.b64encode(svg_code.encode('utf-8')).decode('utf-8')
    data_uri = f"data:image/svg+xml;base64,{b64_svg}"
    return f'<div style="text-align:center; margin:30px 0;"><img src="{data_uri}" style="max-width:100%; border-radius:10px;" alt="{title}"/></div>'

# ==================== [5] 원고 생성 로직 ====================
def generate_master_content():
    keyword, reference_blogs = get_naver_target_data()
    best_model = get_best_model()
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(best_model)

    prompt = f"""
[주제]: {keyword}
[참고]: {reference_blogs}
[미션]: 위 블로그 중 가장 우수한 글을 벤치마킹하여 5,000자 이상의 원고를 작성해.
[필수 사항]: 
1. 제목은 참고 글들의 스타일을 분석해 클릭률이 높게 작성.
2. 'summary' 필드에는 본문 핵심 키워드 3개(각 6자 이내) 필수 포함.
3. HTML 본문에 유효한 새창 링크 8개, 표 2개, 리스트 5개 포함.
4. 직접 경험한 듯한 전문적인 말투 사용 (출처 언급 절대 금지).
[출력 포맷]: JSON (title, meta_desc, meta_keys, slug, summary, content, label_indices)
"""
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except: return None

# ==================== [6] 실행 및 블로거 업로드 ====================
def run_automation():
    print("🚀 [2/5] 프로세스 시작...")
    try:
        # 🌟 깃허브 시크릿에서 토큰 복구
        token_base64 = os.environ.get("BLOGGER_TOKEN_PKL")
        if token_base64:
            with open('token.json', 'wb') as f:
                f.write(base64.b64decode(token_base64))
            print("✅ [3/5] 인증 토큰 복구 완료")

        data = generate_master_content()
        if not data: 
            print("❌ 원고 생성 실패")
            return
        
        # 카드 및 애드센스 삽입
        card_tag = create_summary_card_tag(data.get('summary', []), data['title'])
        ads_tag = '<div style="margin:25px 0;"><script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2303846706279700" crossorigin="anonymous"></script><ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-2303846706279700" data-ad-slot="1632085406" data-ad-format="auto" data-full-width-responsive="true"></ins><script>(adsbygoogle = window.adsbygoogle || []).push({});</script></div>'
        
        content = data['content']
        insertion = card_tag + ads_tag
        content = content.replace("</nav>", f"</nav>{insertion}") if "</nav>" in content else insertion + content

        final_html = f"""<style>
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; }}
            .intro {{ font-weight: bold; border-left: 5px solid #3498db; padding-left: 15px; margin-bottom: 20px; }}
        </style><div class="entry-content">{content}</div>"""

        # 라벨 번호 안전 처리
        raw_indices = data.get('label_indices', [0])
        safe_labels = []
        for i in raw_indices:
            try:
                idx = int(i) % len(LABEL_OPTIONS)
                safe_labels.append(LABEL_OPTIONS[idx])
            except:
                safe_labels.append(LABEL_OPTIONS[0])
        
        safe_labels = list(set(safe_labels))

        # 인증 파일 로드
        with open('token.json', 'rb') as t:
            creds = pickle.load(t)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
        
        service = build('blogger', 'v3', credentials=creds)
        
        print(f"🚀 [4/5] 블로그 업로드 중: {data['title']}")
        service.posts().insert(blogId=BLOG_ID, body={
            "title": data['title'], 
            "content": final_html,
            "labels": safe_labels
        }, isDraft=False).execute()
        
        print(f"✨ [5/5] 최종 성공: {data['title']}")

    except Exception as e: 
        print(f"❌ 에러 발생: {e}")

# ==================== [실행부] ====================
if __name__ == "__main__":
    run_automation()
