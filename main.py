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
        
        all_links = driver.find_elements(By.TAG_NAME, "a")
        count = 0
        seen_urls = set()
        
        for link in all_links:
            href = link.get_attribute("href")
            title = link.text.strip()
            
            if href and "blog.naver.com" in href and len(title) > 5:
                clean_url = href.split('?')[0].rstrip('/')
                if re.search(r'/\d+$', clean_url):
                    if clean_url not in seen_urls:
                        count += 1
                        seen_urls.add(clean_url)
                        links_info += f"[{count}] {title} | 주소: {clean_url}\n"
            
            if count >= 10: break
    finally: driver.quit()
    return target_query, links_info

# ==================== [4] 유동적 SVG 요약 카드 (이모지 & 글자수 방어) ====================
def create_summary_card_tag(summary_list, title):
    safe_list = [str(s).strip()[:15] for s in summary_list if s][:3]
    while len(safe_list) < 3: safe_list.append("") 
    l1, l2, l3 = safe_list

    svg_code = f"""
    <svg width="600" height="230" xmlns="http://www.w3.org/2000/svg">
      <rect width="600" height="230" fill="#FFF9C4" rx="20"/>
      <text x="50%" y="70" font-family="'Apple Color Emoji', 'Segoe UI Emoji', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="30" text-anchor="middle" fill="#2c3e50">{l1}</text>
      <text x="50%" y="130" font-family="'Apple Color Emoji', 'Segoe UI Emoji', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="30" text-anchor="middle" fill="#2c3e50">{l2}</text>
      <text x="50%" y="190" font-family="'Apple Color Emoji', 'Segoe UI Emoji', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="30" text-anchor="middle" fill="#2c3e50">{l3}</text>
    </svg>
    """
    b64_svg = base64.b64encode(svg_code.encode('utf-8')).decode('utf-8')
    data_uri = f"data:image/svg+xml;base64,{b64_svg}"
    return f'<div style="text-align:center; margin:40px 0;"><img src="{data_uri}" style="max-width:100%; height:auto; border-radius:15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);" alt="{title} 핵심 요약 카드"/></div>'

# ==================== [5] 원고 생성 (1타겟 모방 딥다이브 + 구글링크 보정) ====================
def generate_master_content():
    keyword, reference_blogs = get_naver_target_data()
    best_model = get_best_model()
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(best_model)

    prompt = f"""
[타겟 키워드]: {keyword}
[수집된 네이버 블로그 10개]: 
{reference_blogs}

[미션]: 위 10개의 블로그 중 **가장 정보가 뛰어나고 유용한 블로그 딱 1개만 선택**하라. 해당 블로그의 주제와 흐름을 아주 깊이 있게 분석한 뒤, 누락된 정보를 덧붙여 5,000자 이상의 초고품질 딥다이브(Deep-dive) 포스팅으로 완벽하게 재창조하라. 
단, 원본의 출처나 흔적이 남지 않도록 뉘앙스와 말투를 완전히 다르게 변형하여 네가 직접 경험하고 쓴 것처럼 작성하라.

[작성 지침 - 절대 엄수]:
1. **1개 블로그 집중 모방**: 전체를 얕게 요약하지 마라. 선택한 1개의 블로그 내용을 바닥까지 파고들어라.
2. **시간적 표현 절대 금지**: "2026년", "최신", "올해", "현재", "최근" 같은 단어는 제목, 본문 어디에도 절대 쓰지 마라. (사용한 즉시 탈락)
3. **AI 말투 삭제**: "출처를 종합했다", "작성되었습니다", "알아보겠습니다" 같은 기계적인 멘트 금지.
4. **서론 및 목차(앵커)**: 서론은 호기심을 유발하는 문장으로 `<p class="intro">` 태그 안에 작성하라. 서론 바로 밑에 `<nav>` 태그로 목차를 만들고, `<a href="#sec1">` 형태의 앵커 링크와 `<h2 id="sec1">` 형태의 본문 소제목 ID를 일치시켜 클릭 시 스크롤 이동하게 하라.
5. **작동하는 실제 링크 분류 적용 (최소 8개)**: 임의로 만든 가짜 링크나 'googleusercontent' 같은 잘못된 형식은 절대 금지!
   - **장소 (식당, 숙소, 관광지 등)**: 구글 지도 검색 링크 사용 -> <a href="https://www.google.com/maps/search/장소명7" target="_blank">
   - **정보/교통 (교통편, 예매, 팁 등)**: 구글 일반 검색 링크 사용 -> <a href="https://www.google.com/search?q=정확한검색어" target="_blank">
6. **SVG 3줄 요약**: 'summary' 필드에 단어를 한 글자씩 쪼개지 마라! 반드시 **[이모지 1개 + 띄어쓰기 포함 6글자 이하의 명사형 단어]** 조합으로 말이 되는 딱 3개의 구문을 배열로 반환하라. (예: ["🛂 여권 준비물", "✈️ 모바일 티켓", "🎒 기내 수하물"])
7. **구조화 요소**: 표(Table) 3개 이상, 리스트(UL/OL) 5개 이상 필수 포함.
8. **하단 '더 알아보기' 섹션**: 문서 맨 아래에 관련 키워드로 구글 검색 새창 링크 4개 이상을 리스트로 작성하라.
9. **참고 출처 추적**: 네가 선택해서 집중 모방한 1개의 블로그 주소를 'used_references' 배열에 딱 1개만 반환하라.
10. **슬러그**: 'slug' 필드에 연도가 없는 짧은 영문 퍼머링크를 생성하라. (예: travel-tips-korea)
11. **내용 중복 방지 (독창성)**: 1년 내내 매일 글이 발행되어도 소재가 고갈되거나 겹치지 않도록, 누구나 아는 뻔한 내용은 과감히 생략하고 아주 구체적이고 희소성 있는 '니치(Niche)'한 정보와 꿀팁 위주로 글을 구성하라.

[출력 포맷]: JSON (title, meta_desc, meta_keys, slug, summary, content, label_indices, used_references)
"""
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except: return None

# ==================== [6] 실행 및 블로거 업로드 (애드센스 3개 + 완벽 CSS + 2단계 업로드) ====================
def run_automation():
    print("🚀 [2/5] 프로세스 시작...")
    try:
        token_base64 = os.environ.get("BLOGGER_TOKEN_PKL")
        if token_base64:
            with open('token.json', 'wb') as f:
                f.write(base64.b64decode(token_base64))
            print("✅ [3/5] 인증 토큰 복구 완료")

        data = generate_master_content()
        if not data: 
            print("❌ 원고 생성 실패")
            return
        
        # 🌟 제미나이가 타겟으로 삼아 모방한 딱 1개의 블로그 출처 로그 출력
        print("-" * 50)
        print(f"📚 [딥다이브 타겟 블로그 (모방 출처)]")
        for ref in data.get('used_references', []):
            print(f"🔗 {ref}")
        print("-" * 50)
        
        # 기현님 애드센스 코드 (상/중/하단 배치용)
        ads_code = """
        <div style="margin:45px 0;">
            <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2303846706279700" crossorigin="anonymous"></script>
            <ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-2303846706279700" data-ad-slot="1632085406" data-ad-format="auto" data-full-width-responsive="true"></ins>
            <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
        </div>
        """
        
        card_tag = create_summary_card_tag(data.get('summary', []), data['title'])
        content = data['content']

        # 🌟 1. 상단 삽입 (서론 -> 목차 -> 요약카드 -> 애드센스 1 -> 본문)
        top_insertion = f"{card_tag}{ads_code}"
        if "</nav>" in content:
            content = content.replace("</nav>", f"</nav>{top_insertion}")
        else:
            content = top_insertion + content

        # 🌟 2. 중간 삽입 (본문 중간의 h2 태그 위에 애드센스 2)
        h2_parts = content.split("<h2") 
        if len(h2_parts) >= 3:
            mid_index = len(h2_parts) // 2
            h2_parts[mid_index] = ads_code + "<h2" + h2_parts[mid_index]
            content = "<h2".join(h2_parts)

        # 🌟 3. 하단 삽입 (문서 맨 끝에 애드센스 3)
        content = content + ads_code

        # CSS 스크롤 보정 (scroll-margin-top: 120px)
        final_html = f"""
        <meta name="description" content="{data.get('meta_desc', '')}">
        <meta name="keywords" content="{data.get('meta_keys', '')}">
        <style>
            html {{ scroll-behavior: smooth; }}
            .entry-content {{ font-size: 18px; line-height: 2.0; color: #333; font-family: 'Malgun Gothic', sans-serif; }}
            .entry-content h2 {{ font-size: 28px; color: #2c3e50; border-left: 10px solid #3498db; padding: 10px 15px; margin: 55px 0 25px; background: #f9f9f9; scroll-margin-top: 120px; }}
            .entry-content h3 {{ font-size: 23px; color: #2980b9; border-bottom: 2px solid #3498db; padding-bottom: 8px; margin: 35px 0 20px; scroll-margin-top: 120px; }}
            .entry-content p {{ margin-bottom: 25px; }}
            .entry-content table {{ width: 100%; border-collapse: collapse; margin: 30px 0; }}
            .entry-content th {{ background: #3498db; color: white; padding: 12px; }}
            .entry-content td {{ border: 1px solid #ddd; padding: 12px; text-align: center; }}
            .entry-content .intro {{ background: #f0f7ff; padding: 25px; border-radius: 15px; border-left: 5px solid #3498db; margin-bottom: 40px; font-weight: bold; font-size: 20px; line-height: 1.8; }}
            .entry-content nav {{ background: #f8f9fa; padding: 25px; border-radius: 10px; border: 1px solid #eee; margin-bottom: 30px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            .entry-content nav ul {{ list-style: none; padding-left: 0; }}
            .entry-content nav li {{ margin-bottom: 12px; font-size: 19px; }}
            .entry-content nav a {{ color: #2980b9; text-decoration: none; font-weight: bold; }}
            .entry-content nav a:hover {{ text-decoration: underline; color: #e74c3c; }}
            b {{ color: #e74c3c; }}
        </style>
        <div class="entry-content">{content}</div>
        """

        # 라벨 인덱스 (1개 강제)
        raw_indices = data.get('label_indices', [0])
        if not isinstance(raw_indices, list): raw_indices = [raw_indices]
        
        final_labels = []
        for item in raw_indices:
            try:
                val = item.get('index', 0) if isinstance(item, dict) else item
                idx = int(val) % len(LABEL_OPTIONS)
                final_labels.append(LABEL_OPTIONS[idx])
            except: continue
        
        if not final_labels: final_labels = [LABEL_OPTIONS[0]]
        final_labels = list(set(final_labels))[:1]

        # 블로그 API 인증
        with open('token.json', 'rb') as t:
            creds = pickle.load(t)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
        
        service = build('blogger', 'v3', credentials=creds)
        
        # 🌟 1단계: 영어 슬러그 확보용 초안 생성 (퍼머링크 고정)
        print(f"🚀 [4/5] 1단계: 영어 슬러그 확보용 초안 생성 ({data.get('slug', 'auto-post')})")
        slug_text = data.get('slug', 'auto-post')
        if not slug_text.strip(): slug_text = "auto-post"
        
        temp_post = service.posts().insert(blogId=BLOG_ID, body={
            "title": slug_text, 
            "content": "가독성을 위해 본문이 조립 중입니다...",
            "labels": final_labels
        }, isDraft=True).execute()

        # 🌟 2단계: 최종 원고(한글 제목)로 내용 덮어쓰기 및 발행
        print(f"🚀 [4/5] 2단계: 최종 원고 업데이트 및 발행 ({data['title']})")
        service.posts().patch(blogId=BLOG_ID, postId=temp_post['id'], body={
            "title": data['title'], 
            "content": final_html,
            "customMetaData": data.get('meta_desc', '')
        }, isDraft=False).execute()
        
        print(f"✨ [5/5] 최종 성공: {data['title']}")

    except Exception as e: print(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    run_automation()
