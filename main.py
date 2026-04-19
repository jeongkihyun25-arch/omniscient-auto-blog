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

# ==================== [3] 네이버 수집 (정밀 검색 로직) ====================
def get_naver_target_data():
    now = datetime.now()
    # 실시간 월별 키워드 생성 (2026년 고정 아님, 현재 날짜 기반)
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
        # 블로그 탭 결과 직접 타겟팅
        url = f"https://search.naver.com/search.naver?ssc=tab.blog.all&query={urllib.parse.quote(target_query)}"
        driver.get(url)
        time.sleep(5)
        
        # 실제 블로그 링크 10개 추출 (a.title_link 선택자 활용)
        blog_elements = driver.find_elements(By.CSS_SELECTOR, "a.title_link")
        count = 0
        for el in blog_elements:
            href = el.get_attribute("href")
            title = el.text.strip()
            if href and "blog.naver.com" in href and len(title) > 8:
                count += 1
                links_info += f"[{count}] 제목: {title} | 주소: {href}\n"
            if count >= 10: break
    finally: driver.quit()
    return target_query, links_info

# ==================== [4] 유동적 SVG 요약 카드 (3줄 고정) ====================
def create_summary_card_tag(summary_list, title):
    # 6글자씩 3개 준비
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
    return f'<div style="text-align:center; margin:40px 0;"><img src="{data_uri}" style="max-width:100%; height:auto; border-radius:15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);" alt="{title} 핵심 요약 카드"/></div>'

# ==================== [5] 원고 생성 (AI 말투 제거 + SEO 강화) ====================
def generate_master_content():
    keyword, reference_blogs = get_naver_target_data()
    best_model = get_best_model()
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(best_model)

    # 실시간 날짜 변수
    now = datetime.now()
    current_date = now.strftime('%Y년 %m월 %d일')
    current_year = now.year

    prompt = f"""
[오늘의 날짜]: {current_date}
[타겟 키워드]: {keyword}
[참고 데이터]: 
{reference_blogs}

[미션]: 위 블로그들을 분석하여 {current_year}년 최신 트렌드가 반영된 5,000자 이상의 고품질 SEO 원고를 작성하라.

[작성 지침 - 절대 엄수]:
1. **사람처럼 써라**: "다양한 출처를 종합했다", "전문적인 조언이다" 같은 AI 특유의 멘트는 절대 금지다. 서두에 군더더기 없이 바로 독자에게 필요한 혜택과 정보로 시작하라. (~합니다, ~하세요 어조 사용)
2. **2026년 반영**: 현재는 {current_year}년이다. 참고 데이터에 과거 연도가 있더라도 무시하고 무조건 {current_year}년 최신 정보라고 작성하라.
3. **SEO 구조화**: <h2>와 <h3> 태그를 체계적으로 사용하여 전문적인 가독성을 확보하라.
4. **슬러그(Slug)**: 연도를 제외한 키워드 중심의 영문 슬러그를 짧게 생성하라 (예: passport-issuance-guide).
5. **메타 정보**: meta_desc는 검색 결과 클릭을 유도하는 매력적인 문구로 작성하라.
6. **SVG 요약**: 'summary' 필드에 본문의 핵심 키워드 **6글자 이내** 단어 3개를 뽑아라.
7. **구성 요소**: 표(Table) 2개 이상, 리스트 5개 이상, 실존하는 유효한 외부 링크 8개 이상을 자연스럽게 포함하라.

[출력 포맷]: JSON (title, meta_desc, meta_keys, slug, summary, content, label_indices)
"""
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except: return None

# ==================== [6] 실행 및 블로거 업로드 (디자인 반영) ====================
def run_automation():
    print("🚀 [2/5] 프로세스 시작...")
    try:
        token_base64 = os.environ.get("BLOGGER_TOKEN_PKL")
        if token_base64:
            with open('token.json', 'wb') as f: f.write(base64.b64decode(token_base64))
            print("✅ [3/5] 인증 토큰 복구 완료")

        data = generate_master_content()
        if not data: return
        
        # 요약 카드 및 광고 삽입
        card_tag = create_summary_card_tag(data.get('summary', []), data['title'])
        ads_tag = '<div style="margin:30px 0;"><script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2303846706279700" crossorigin="anonymous"></script><ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-2303846706279700" data-ad-slot="1632085406" data-ad-format="auto" data-full-width-responsive="true"></ins><script>(adsbygoogle = window.adsbygoogle || []).push({});</script></div>'
        
        content = data['content']
        insertion = card_tag + ads_tag
        content = content.replace("</nav>", f"</nav>{insertion}") if "</nav>" in content else insertion + content

        # 기현님 스타일 반영 CSS (18px 큰 글씨 + 파란색 헤더 바)
        final_html = f"""
        <meta name="description" content="{data['meta_desc']}">
        <meta name="keywords" content="{data['meta_keys']}">
        <style>
            .entry-content {{ font-size: 18px; line-height: 2.0; color: #333; font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; }}
            .entry-content h2 {{ 
                font-size: 28px; color: #2c3e50; border-left: 10px solid #3498db; 
                padding: 10px 15px; margin: 45px 0 25px; background: #f9f9f9; 
            }}
            .entry-content h3 {{ 
                font-size: 23px; color: #2980b9; border-bottom: 2px solid #3498db; 
                padding-bottom: 8px; margin: 35px 0 20px; 
            }}
            .entry-content p {{ margin-bottom: 25px; }}
            .entry-content table {{ width: 100%; border-collapse: collapse; margin: 30px 0; }}
            .entry-content th {{ background: #3498db; color: white; padding: 12px; }}
            .entry-content td {{ border: 1px solid #ddd; padding: 12px; text-align: center; }}
            .intro {{ background: #f0f7ff; padding: 25px; border-radius: 15px; border-left: 5px solid #3498db; margin-bottom: 40px; font-weight: bold; }}
            b {{ color: #e74c3c; }} /* 중요 강조 빨간색 */
        </style>
        <div class="entry-content">{content}</div>
        """

        # 라벨 및 인증 처리
        raw_indices = data.get('label_indices', [0])
        safe_labels = []
        for i in raw_indices:
            try:
                idx = int(i) % len(LABEL_OPTIONS)
                safe_labels.append(LABEL_OPTIONS[idx])
            except:
                safe_labels.append(LABEL_OPTIONS[0])
        
        with open('token.json', 'rb') as t:
            creds = pickle.load(t)
            if creds.expired: creds.refresh(Request())
        
        service = build('blogger', 'v3', credentials=creds)
        
        print(f"🚀 [4/5] 블로그 업로드 중: {data['title']}")
        service.posts().insert(blogId=BLOG_ID, body={
            "title": data['title'], 
            "content": final_html, 
            "labels": list(set(safe_labels)),
            "customMetaData": data.get('meta_desc', ''),
            "location": {"name": "South Korea"}
        }, isDraft=False).execute()
        
        print(f"✨ [5/5] 최종 성공: {data['title']}")

    except Exception as e: 
        print(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    run_automation()
