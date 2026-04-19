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

# ==================== [3] 네이버 수집 (🔥 1타겟 고정 + 4서브 랜덤 본문 스크래핑) ====================
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
    
    valid_links = []
    scraped_data = ""
    target_blog_url = ""
    links_info_selected = ""

    try:
        url = f"https://search.naver.com/search.naver?ssc=tab.blog.all&query={urllib.parse.quote(target_query)}"
        driver.get(url)
        time.sleep(5)
        
        all_links = driver.find_elements(By.TAG_NAME, "a")
        seen_urls = set()
        
        # 1. 먼저 상위 15개의 유효 블로그 링크 확보
        for link in all_links:
            href = link.get_attribute("href")
            title = link.text.strip()
            
            if href and "blog.naver.com" in href and len(title) > 5:
                clean_url = href.split('?')[0].rstrip('/')
                if re.search(r'/\d+$', clean_url):
                    if clean_url not in seen_urls:
                        seen_urls.add(clean_url)
                        valid_links.append({"title": title, "url": clean_url})
            
            if len(valid_links) >= 15: break

        # 2. 1위 글 고정 + 나머지 중 4개 랜덤 추출 (내용 중복 방지)
        if len(valid_links) > 5:
            selected_links = [valid_links[0]] + random.sample(valid_links[1:], 4)
        else:
            selected_links = valid_links

        if selected_links:
            target_blog_url = selected_links[0]['url'] # 출처 기록용 메인 타겟
            print(f"\n🔍 [본문 추출 시작: 1위 고정 + 서브 랜덤 4개]")
            
            # 3. 5개 블로그 순회하며 진짜 본문 스크래핑
            for i, item in enumerate(selected_links):
                mobile_url = item['url'].replace("blog.naver.com", "m.blog.naver.com")
                driver.get(mobile_url)
                time.sleep(2)
                
                try: text = driver.find_element(By.CSS_SELECTOR, ".se-main-container").text
                except:
                    try: text = driver.find_element(By.TAG_NAME, "body").text
                    except: text = "수집 실패"

                clean_text = text.replace('\n', ' ')[:1500]
                role = "메인 타겟(뼈대)" if i == 0 else "서브 타겟(후기 추출용)"
                scraped_data += f"--- [{role}] {item['title']} ---\n{clean_text}...\n\n"
                links_info_selected += f"[{i+1}] {role} | {item['title']} \n"
                print(f"  👉 [{role}] 텍스트 확보 완료!")

    finally: driver.quit()
    return target_query, links_info_selected, target_blog_url, scraped_data

# ==================== [4] 유동적 SVG 요약 카드 ====================
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

# ==================== [5] 원고 생성 (실제 본문 5개 분석 & AI 냄새 완벽 제거) ====================
def generate_master_content():
    # 이제 진짜 본문 텍스트 합본(scraped_data)을 가져옵니다!
    keyword, reference_blogs, target_blog_url, scraped_data = get_naver_target_data()
    best_model = get_best_model()
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(best_model)

    prompt = f"""
[타겟 키워드]: {keyword}
[참고 네이버 블로그 리스트]: 
{reference_blogs}
[🔥 집중 분석 타겟 (실제 1위 블로그 뼈대 + 서브 블로그 4개 후기 합본)]: 
{scraped_data}

[미션]: 위 [집중 분석 타겟]의 '실제 텍스트 본문'을 완벽하게 해부하여 5,000자 이상의 초고품질 딥다이브 포스팅으로 재창조하라. 

[A급 블로그 카피라이팅 지시사항 - 절대 엄수]:
1. **AI 냄새나는 가짜 소설 금지! (소스 세탁)**: "지난번 일본 여행 갈 때~", "돈이 시간을 사준다" 같은 전형적이고 뻔한 AI 소설을 억지로 지어내지 마라! 반드시 내가 제공한 [집중 분석 타겟] 본문 안에 있는 '실제 사람의 정보, 꿀팁, 문제점' 팩트를 활용하라. 단, 원작자의 너무 사적인 TMI는 쳐내고, 말투와 뉘앙스만 자연스러운 1인칭으로 세탁(가공)하라.
2. **클릭을 유발하는 자극형 제목**: 사전적 제목 금지. "안 하면 줄 40분 서는 이유", "출국 10분 줄이려면 필수" 처럼 '손실 회피' 심리를 자극하라. 끝에 "(실제 후기)", "(꿀팁)"을 붙여라.
3. **🔥 자연스러운 "비교 분석" 파트**: 억지 비교 절대 금지. 본문 내용을 바탕으로 사람들이 진짜로 헷갈려하는 2가지(예: 일반줄 vs 스마트패스 시간차이)를 찾아 대조하라.
4. **시간적 표현 절대 금지**: "2026년", "최신", "올해", "현재", "최근" 같은 단어는 제목, 본문 어디에도 절대 금지.
5. **AI 멘트 원천 차단**: "출처를 종합했다", "작성되었습니다", "알아보겠습니다" 같은 기계적인 멘트 금지.
6. **작동하는 실제 링크 적용 (최소 8개 이상, 모두 target="_blank")**: 
   - **장소 (식당, 공항, 숙소, 관광지 등)**: 구글 지도 공식 검색 링크 사용 여러 단어 조합해서 쓰지말것 -> <a href="https://www.google.com/maps/search/장소명" target="_blank">
   - **정보/교통 (교통편, 예매, 팁 등)**: 구글 일반 검색 링크 사용 -> <a href="https://www.google.com/search?q=정확한검색어" target="_blank">
7. **SVG 3줄 요약**: 'summary' 필드에 반드시 **[이모지 1개 + 띄어쓰기 포함 6글자 이하의 명사형 단어]** 조합으로 딱 3개의 구문을 배열로 반환하라.
8. **구조화 요소**: 서론은 `<p class="intro">` 사용. 서론 밑에 `<nav>` 목차 및 `<h2 id="...">` 앵커 연동. 표 3개, 리스트 5개 이상.
9. **하단 섹션**: 맨 아래 관련 키워드로 구글 일반 검색 새창 링크 4개 리스트 추가.
10. **슬러그**: 한글 제목에서 핵심 키워드 2~3개만 뽑아 짧은 영어 단어들의 조합으로 생성 (예: vietnam-travel-tips).
11. **내용 중복 방지**: 누구나 아는 뻔한 내용은 생략하고, 본문에서 추출한 구체적이고 희소성 있는 '니치(Niche)'한 꿀팁 위주로 작성.

[출력 포맷]: JSON (title, meta_desc, meta_keys, slug, summary, content, label_indices)
"""
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(response.text)
        data['used_references'] = [target_blog_url]
        return data
    except Exception as e: 
        print(f"제미나이 호출 오류: {e}")
        return None

# ==================== [6] 실행 및 블로거 업로드 (퍼머링크 트릭 적용) ====================
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
        
        print("-" * 50)
        print(f"📚 [딥다이브 타겟 블로그 (실제 본문 스크래핑 완료)]")
        for ref in data.get('used_references', []):
            print(f"🔗 {ref}")
        print("-" * 50)
        
        ads_code = """
        <div style="margin:45px 0;">
            <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2303846706279700" crossorigin="anonymous"></script>
            <ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-2303846706279700" data-ad-slot="1632085406" data-ad-format="auto" data-full-width-responsive="true"></ins>
            <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
        </div>
        """
        
        card_tag = create_summary_card_tag(data.get('summary', []), data['title'])
        content = data['content']

        top_insertion = f"{card_tag}{ads_code}"
        if "</nav>" in content:
            content = content.replace("</nav>", f"</nav>{top_insertion}")
        else:
            content = top_insertion + content

        h2_parts = content.split("<h2") 
        if len(h2_parts) >= 3:
            mid_index = len(h2_parts) // 2
            h2_parts[mid_index] = ads_code + "<h2" + h2_parts[mid_index]
            content = "<h2".join(h2_parts)

        content = content + ads_code

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

        with open('token.json', 'rb') as t:
            creds = pickle.load(t)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
        
        service = build('blogger', 'v3', credentials=creds)
        
        # 🌟 1단계: 영어 슬러그로 먼저 던져서 예쁜 주소 확보!
        slug_text = data.get('slug', 'auto-post')
        if not slug_text.strip(): slug_text = "auto-post"
        print(f"🚀 [4/5] 주소 생성용 트릭 실행 중... ({slug_text})")
        
        temp_post = service.posts().insert(blogId=BLOG_ID, body={
            "title": slug_text, 
            "content": "loading...",
            "labels": final_labels
        }, isDraft=False).execute()

        # 🌟 2단계: 진짜 한글 제목과 본문으로 덮어쓰기
        print(f"🚀 [4/5] 진짜 한글 제목 덮어쓰는 중... ({data['title']})")
        service.posts().patch(blogId=BLOG_ID, postId=temp_post['id'], body={
            "title": data['title'], 
            "content": final_html,
            "customMetaData": data.get('meta_desc', '')
        }).execute() 
        
        print(f"✨ [5/5] 최종 성공: {data['title']}")

    except Exception as e: print(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    run_automation()
