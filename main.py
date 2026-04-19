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

# ==================== [3] 네이버 수집 (가장 확실한 무적 로직) ====================
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
        
        # 🌟 기현님 테스트에서 성공한 가장 확실한 전체 <a> 태그 수집 로직
        all_links = driver.find_elements(By.TAG_NAME, "a")
        count = 0
        seen_urls = set()
        
        for link in all_links:
            href = link.get_attribute("href")
            title = link.text.strip()
            
            if href and "blog.naver.com" in href and len(title) > 5:
                clean_url = href.split('?')[0].rstrip('/')
                # 본문 포스팅 번호 확인
                if re.search(r'/\d+$', clean_url):
                    if clean_url not in seen_urls:
                        count += 1
                        seen_urls.add(clean_url)
                        links_info += f"[{count}] {title} | 주소: {clean_url}\n"
            
            if count >= 10: break
    finally: driver.quit()
    return target_query, links_info

# ==================== [4] 유동적 SVG 요약 카드 ====================
def create_summary_card_tag(summary_list, title):
    safe_list = [str(s).strip()[:5] for s in summary_list if s][:3]
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

# ==================== [5] 원고 생성 (프롬프트 완벽 강화) ====================
def generate_master_content():
    keyword, reference_blogs = get_naver_target_data()
    best_model = get_best_model()
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(best_model)

    now = datetime.now()
    current_year = now.year

    prompt = f"""
[오늘의 시점]: {now.strftime('%Y년 %m월 %d일')}
[타겟 키워드]: {keyword}
[참고 데이터]: {reference_blogs}

[미션]: 위 데이터를 분석하여 {current_year}년 최신 기준으로 5,000자 이상의 전문가 SEO 포스팅을 작성하라.
[필수 구성 및 태그]:
1. **서론**: 호기심을 유발하는 짧고 강렬한 문장으로 시작하고 반드시 `<p class="intro">` 태그를 사용하라.
2. **목차**: 서론 바로 다음에 올 수 있도록 `<nav>` 태그로 목차(TOC)를 생성하라. 내부 앵커 링크 포함.
3. **본문**: <h2>(파란 바 스타일)와 <h3>(밑줄 스타일)를 체계적으로 사용하라.
4. **요소**: 표(Table) 3개 이상, 리스트(UL/OL) 5개 이상 필수 포함.
5. **새창 링크**: 본문 내에 유효한 새창 링크(`<a href="..." target="_blank">`) 최소 8개 이상 포함 (구글 검색 링크 등 활용 가능).
6. **AI 말투 제거**: "출처를 종합했다", "조언이다", "작성되었습니다" 같은 AI 면피용 문구 절대 금지. 사람이 직접 쓴 것처럼 정보를 바로 꽂아라.
7. **2026년 고정**: 참고 데이터에 과거 연도가 있더라도 무시하고 {current_year}년 최신 정보라고 작성하라.
8. **하단 섹션**: 문서 맨 아래에 '더 알아보기' 섹션을 만들고 관련 키워드 새창 링크 4개 이상을 리스트로 작성하라.
9. **데이터**: 'summary' 필드에 본문 핵심 키워드 5자 이내 3개를 담아라. 'slug' 필드에 연도가 포함되지 않은 영어 퍼머링크를 생성하라.

[출력 포맷]: JSON (title, meta_desc, meta_keys, slug, summary, content, label_indices)
"""
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except: return None

# ==================== [6] 실행 및 블로거 업로드 (에러 방지 및 구조 개선) ====================
def run_automation():
    print("🚀 [2/5] 프로세스 시작...")
    try:
        # 깃허브 시크릿에서 토큰 복구
        token_base64 = os.environ.get("BLOGGER_TOKEN_PKL")
        if token_base64:
            with open('token.json', 'wb') as f:
                f.write(base64.b64decode(token_base64))
            print("✅ [3/5] 인증 토큰 복구 완료")

        data = generate_master_content()
        if not data: 
            print("❌ 원고 생성 실패")
            return
        
        # 1. 요약 카드 및 애드센스 태그 준비
        card_tag = create_summary_card_tag(data.get('summary', []), data['title'])
        ads_tag = '<div style="margin:30px 0;"><script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2303846706279700" crossorigin="anonymous"></script><ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-2303846706279700" data-ad-slot="1632085406" data-ad-format="auto" data-full-width-responsive="true"></ins><script>(adsbygoogle = window.adsbygoogle || []).push({});</script></div>'
        
        content = data['content']
        insertion = f"{card_tag}{ads_tag}"

        # 2. 🌟 HTML 구조 강제 재배치 (서론 -> 목차 -> 카드/광고 -> 본문)
        if "</nav>" in content:
            content = content.replace("</nav>", f"</nav>{insertion}")
        else:
            content = insertion + content

        # 3. 스타일링 적용
        final_html = f"""
        <meta name="description" content="{data.get('meta_desc', '')}">
        <meta name="keywords" content="{data.get('meta_keys', '')}">
        <style>
            .entry-content {{ font-size: 18px; line-height: 2.0; color: #333; font-family: 'Malgun Gothic', sans-serif; }}
            .entry-content h2 {{ font-size: 28px; color: #2c3e50; border-left: 10px solid #3498db; padding: 10px 15px; margin: 45px 0 25px; background: #f9f9f9; }}
            .entry-content h3 {{ font-size: 23px; color: #2980b9; border-bottom: 2px solid #3498db; padding-bottom: 8px; margin: 35px 0 20px; }}
            .entry-content p {{ margin-bottom: 25px; }}
            .entry-content table {{ width: 100%; border-collapse: collapse; margin: 30px 0; }}
            .entry-content th {{ background: #3498db; color: white; padding: 12px; }}
            .entry-content td {{ border: 1px solid #ddd; padding: 12px; text-align: center; }}
            .entry-content .intro {{ background: #f0f7ff; padding: 25px; border-radius: 15px; border-left: 5px solid #3498db; margin-bottom: 40px; font-weight: bold; font-size: 20px; }}
            .entry-content nav {{ background: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #eee; margin-bottom: 30px; }}
            .entry-content nav ul {{ list-style: none; padding-left: 0; }}
            .entry-content nav li {{ margin-bottom: 10px; }}
            .entry-content nav a {{ color: #2c3e50; text-decoration: none; font-weight: bold; }}
            b {{ color: #e74c3c; }}
        </style>
        <div class="entry-content">{content}</div>
        """

        # 4. 🌟 라벨 인덱스 에러 방어 로직 (int() dict 에러 완전 해결)
        raw_indices = data.get('label_indices', [0])
        if not isinstance(raw_indices, list): raw_indices = [raw_indices]
        
        final_labels = []
        for item in raw_indices:
            try:
                # 딕셔너리일 경우 값만 추출, 아닐 경우 바로 int 변환
                val = item.get('index', 0) if isinstance(item, dict) else item
                idx = int(val) % len(LABEL_OPTIONS)
                final_labels.append(LABEL_OPTIONS[idx])
            except:
                continue
        
        # 라벨이 비어있으면 기본값, 중복 제거 후 최대 2개까지만
        if not final_labels: final_labels = [LABEL_OPTIONS[0]]
        final_labels = list(set(final_labels))[:2]

        # 5. 인증 및 업로드
        with open('token.json', 'rb') as t:
            creds = pickle.load(t)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
        
        service = build('blogger', 'v3', credentials=creds)
        
        print(f"🚀 [4/5] 블로그 업로드 중: {data['title']}")
        service.posts().insert(blogId=BLOG_ID, body={
            "title": data['title'], 
            "content": final_html, 
            "labels": final_labels,
            "customMetaData": data.get('meta_desc', '')
        }, isDraft=False).execute()
        
        print(f"✨ [5/5] 최종 성공: {data['title']}")

    except Exception as e: 
        print(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    run_automation()
