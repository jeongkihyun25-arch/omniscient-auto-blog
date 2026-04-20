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

PRIORITY_KEYWORDS = ["eSIM", "로밍", "환전", "수하물", "스마트패스", "유심"]
LOW_PERFORMANCE_KEYWORDS = ["일본 환전 꿀팁", "여행자 보험 꼭 필요한가", "가성비 숙소 고르는 법"]

CONTENT_FLOW = {
    "공항": ["eSIM", "수하물 추가 요금", "스마트패스"],
    "eSIM": ["로밍 요금", "데이터 안터질 때", "환전"],
    "유심": ["로밍 요금", "eSIM 추천"],
    "일본": ["비지트 재팬", "일본 환전", "일본 쇼핑리스트"],
    "베트남": ["베트남 환전", "가성비 숙소"],
    "태국": ["태국 환전", "현지 맛집 찾는 방법"],
    "미국": ["여행자 보험", "해외 로밍 요금"]
}

# ==================== [2] 핵심 유틸리티 (지도 생성 포함) ====================
def get_best_model():
    print("🔍 [1/6] 최고 모델 탐색 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    try:
        res = requests.get(url, timeout=15).json()
        available = [m['name'].replace('models/', '') for m in res.get('models', [])
                     if 'generateContent' in m.get('supportedGenerationMethods', [])]
        priorities = ["gemini-1.5-pro", "gemini-2.0-pro", "gemini-2.5-flash-lite", "gemini-2.0-flash"]
        for p in priorities:
            for m in available:
                if p in m: return m
        return available[0] if available else "gemini-2.0-flash"
    except: return "gemini-2.0-flash"

def prioritize_keywords(keywords):
    p = [k for k in keywords if any(x in k for x in PRIORITY_KEYWORDS)]
    n = [k for k in keywords if k not in p]
    return p + n

def generate_title_variants(keyword):
    variants = [
        f"{keyword} 이거 안 하면 비용 2배 (실제 후기)",
        f"{keyword} 완벽 비교 가이드: 30분 아끼는 꿀팁",
        f"여행 고수들이 몰래 쓰는 {keyword} 핵심 1가지"
    ]
    return random.choice(variants)

def get_recent_posts(service, blog_id):
    try:
        posts = service.posts().list(blogId=blog_id, maxResults=10, fetchBodies=False).execute()
        return [{"title": p["title"], "url": p["url"]} for p in posts.get("items", [])]
    except Exception as e:
        print(f"⚠️ 내부링크 수집 실패: {e}")
        return []

def get_content_chain(keyword):
    for key, flows in CONTENT_FLOW.items():
        if key in keyword: return flows[0]
    return "여행 준비물"

def get_related_posts_by_keyword(posts, keyword):
    first_word = keyword.split()[0]
    return [p for p in posts if first_word in p['title']]

def extract_location_keyword(keyword):
    locations = ["일본", "도쿄", "오사카", "후쿠오카", "삿포로", "오키나와",
                 "베트남", "다낭", "나트랑", "호찌민", "푸꾸옥",
                 "태국", "방콕", "치앙마이",
                 "대만", "타이베이", "홍콩", "마카오",
                 "미국", "하와이", "괌", "사이판", "인천공항", "김포공항"]
    for loc in locations:
        if loc in keyword: return loc
    return keyword.split()[0]

def create_map_embed(location):
    search_term = f"{location} 공항" if "공항" not in location else location
    query = urllib.parse.quote(search_term)
    return f'''
    <div style="margin:40px 0; border-radius:12px; overflow:hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
        <iframe 
            src="https://maps.google.com/maps?q={query}&t=&z=13&ie=UTF8&iwloc=&output=embed"
            width="100%" height="350" style="border:0;"
            allowfullscreen="" loading="lazy">
        </iframe>
        <p style="text-align:center; font-size:14px; color:#7f8c8d; margin-top:10px;">👆 {location} 관련 핵심 위치 참고</p>
    </div>
    '''

# ==================== [3] 네이버 수집 (🔥 15개 중 10개 믹스 + 쿼리 셔플 + 재활용) ====================
def get_naver_target_data():
    now = datetime.now()
    COUNTRY_GROUPS = [
        ["일본", "대만", "홍콩", "중국"],           
        ["베트남", "태국", "필리핀", "인도네시아"],  
        ["미국", "캐나다", "하와이"],               
        ["프랑스", "이탈리아", "스페인", "영국"]    
    ]
    group_index = now.month % len(COUNTRY_GROUPS)
    current_group = COUNTRY_GROUPS[group_index]
    main_country = current_group[0] 
    sub_country = random.choice(current_group[1:]) if len(current_group) > 1 else main_country
    
    BASE_KEYWORDS = [
        "인천공항 주차 요금", "인천공항 혼잡 시간", "출국 수속 시간", "스마트패스 사용법", 
        "공항 라운지 무료 이용", "공항 리무진 시간표", "기내 반입 규정", "수하물 추가 요금",
        "공항 대기 시간", "출국 몇시간 전",
        "해외 로밍 요금", "eSIM 추천", "eSIM 안될 때", "유심 vs eSIM 비교", 
        "데이터 안터질 때", "환전 수수료 줄이기", "여행 비용 줄이는 법",
        f"{main_country} 입국신고서", f"{main_country} 교통패스", f"{main_country} 쇼핑리스트", 
        f"{main_country} 유심 eSIM 추천", f"{main_country} 맛집 실패 안하는 법",
        f"{sub_country} 여행 준비물", f"{sub_country} 가볼만한곳",
        "해외여행 준비물 체크리스트", "여행자 보험 꼭 필요한가", "비상약 리스트", 
        "세관 신고 기준", "가족 여행 준비 팁", "가성비 숙소 고르는 법"
    ]

    if not os.path.exists(QUEUE_FILE) or os.stat(QUEUE_FILE).st_size == 0:
        sorted_keys = prioritize_keywords(BASE_KEYWORDS)
        sorted_keys = sorted_keys + PRIORITY_KEYWORDS  
        with open(QUEUE_FILE, "w", encoding="utf-8") as f: f.write("\n".join(sorted_keys))

    with open(QUEUE_FILE, "r", encoding="utf-8") as f: lines = f.read().splitlines()
    if not lines: 
        lines = prioritize_keywords(BASE_KEYWORDS) + PRIORITY_KEYWORDS
        
    if random.random() < 0.2 and LOW_PERFORMANCE_KEYWORDS:
        target_query = random.choice(LOW_PERFORMANCE_KEYWORDS)
        print(f"♻️ [System] 20% 확률 발동: 저성과 키워드({target_query})를 심폐소생합니다.")
    elif random.random() < 0.2 and len(lines) > 5:
        target_query = random.choice(lines[1:])
        lines.remove(target_query)
        lines.insert(0, target_query) 
        print("♻️ [System] 20% 확률 발동: 큐 내 기존 키워드 재활용(SEO 누적)을 실행합니다.")
    else:
        target_query = lines[0]
    
    if random.random() < 0.5:
        title_guide = generate_title_variants(target_query)
    else:
        title_guide = f"{target_query} 완벽 가이드 (실제 후기)"
        
    related_keyword = get_content_chain(target_query)
    
    if target_query == lines[0]:
        lines = lines[1:] + [target_query]
        with open(QUEUE_FILE, "w", encoding="utf-8") as f: f.write("\n".join(lines))

    search_suffix = [" 장단점", " 설정 오류", " 아이폰 꿀팁", " 실제 후기", " 주의사항"]
    actual_search_query = f"{target_query}{random.choice(search_suffix)}"
    
    print(f"🎯 [2/6] 키워드: {target_query} (검색어: {actual_search_query} / 브릿지 연결: {related_keyword})")

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    valid_links = []
    scraped_data = ""
    target_blog_url = ""

    try:
        url = f"https://search.naver.com/search.naver?ssc=tab.blog.all&query={urllib.parse.quote(actual_search_query)}"
        driver.get(url)
        time.sleep(5)
        
        all_links = driver.find_elements(By.TAG_NAME, "a")
        seen_urls = set()
        for link in all_links:
            href = link.get_attribute("href")
            title = link.text.strip()
            if href and "blog.naver.com" in href and len(title) > 5:
                clean_url = href.split('?')[0].rstrip('/')
                if re.search(r'/\d+$', clean_url) and clean_url not in seen_urls:
                    seen_urls.add(clean_url)
                    valid_links.append({"title": title, "url": clean_url})
            if len(valid_links) >= 15: break

        if len(valid_links) >= 5:
            main_idx = random.randint(0, min(2, len(valid_links)-1))
            main_link = valid_links.pop(main_idx)
            sub_links = random.sample(valid_links, min(9, len(valid_links)))
            selected_links = [main_link] + sub_links
        else:
            selected_links = valid_links

        if selected_links:
            target_blog_url = selected_links[0]['url'] 
            print(f"🔍 [3/6] 총 {len(selected_links)}개 블로그 딥다이브 추출 중... (뼈대: {selected_links[0]['title']})")
            
            for i, item in enumerate(selected_links):
                mobile_url = item['url'].replace("blog.naver.com", "m.blog.naver.com")
                driver.get(mobile_url)
                time.sleep(1.5)
                try: text = driver.find_element(By.CSS_SELECTOR, ".se-main-container").text
                except:
                    try: text = driver.find_element(By.TAG_NAME, "body").text
                    except: text = "수집 실패"
                
                if i == 0:
                    role = "Main Skeleton"
                    scraped_data += f"--- [{role}: {item['title']}] ---\n{text[:2000]}\n\n"
                else:
                    role = "Real Review Insight"
                    scraped_data += f"--- [{role}: {item['title']}] ---\n{text[:500]}\n\n"
    finally: driver.quit()
    return target_query, target_blog_url, scraped_data, title_guide, related_keyword

# ==================== [4] 유동적 SVG 요약 카드 ====================
def create_summary_card_tag(summary_list, title):
    safe_list = [str(s).strip()[:15] for s in summary_list if s][:3]
    while len(safe_list) < 3: safe_list.append("") 
    svg_code = f"""
    <svg width="600" height="230" xmlns="http://www.w3.org/2000/svg">
      <rect width="600" height="230" fill="#FFF9C4" rx="20"/>
      <text x="50%" y="70" font-family="'Apple Color Emoji', 'Segoe UI Emoji', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="30" text-anchor="middle" fill="#2c3e50">{safe_list[0]}</text>
      <text x="50%" y="130" font-family="'Apple Color Emoji', 'Segoe UI Emoji', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="30" text-anchor="middle" fill="#2c3e50">{safe_list[1]}</text>
      <text x="50%" y="190" font-family="'Apple Color Emoji', 'Segoe UI Emoji', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="30" text-anchor="middle" fill="#2c3e50">{safe_list[2]}</text>
    </svg>
    """
    b64_svg = base64.b64encode(svg_code.encode('utf-8')).decode('utf-8')
    return f'<div style="text-align:center; margin:40px 0;"><img src="data:image/svg+xml;base64,{b64_svg}" style="max-width:100%; height:auto; border-radius:15px;" alt="{title}"/></div>'

# ==================== [5] 원고 생성 (🔥 E-E-A-T, 문맥 반영 외부링크) ====================
def generate_master_content(keyword, target_blog_url, scraped_data, title_guide, context_posts, related_keyword):
    model_name = get_best_model()
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"

    personas = ["가성비 헌터 블로거", "효율 극대화 프로 출장러", "디테일 끝판왕 J형 여행가"]
    current_persona = random.choice(personas)
    recent_posts_str = "\n".join([f"- 제목: {p['title']} (URL: {p['url']})" for p in context_posts])

    prompt = f"""
[타겟 키워드]: {keyword}
[권장 제목 뼈대]: {title_guide}
[페르소나]: {current_persona} (이 성격에 빙의하여 직접 경험한 듯이 작성하라)
[내 블로그의 다른 글 리스트]: 
{recent_posts_str}

[10개 블로그 분석 데이터 (뼈대 1 + 리얼 후기 9)]: 
{scraped_data}

[미션]: 독자가 글을 읽고 즉시 '결정'을 하도록 유도하는, 4,000자에서 6,000자 사이의 '밀도가 매우 높은' 99점짜리 전환형 포스팅을 작성하라. 억지로 글자만 늘리지 마라. 핵심 위주로 쫀쫀하게 구성해라.

[🔥 품질 및 전환율 폭발 필터 - 절대 엄수]:
1. **후킹 및 원-메시지 (Hook)**: 서론 첫 문장에는 "손해", "시간", "돈" 중 하나를 반드시 포함하여 강렬하게 시작하라. 서론 직후에 반드시 **"결론부터 말하면, [{keyword}]에서 손해 안 보는 핵심은 단 하나입니다: [핵심내용]"** 이라는 문장으로 흩어진 정보를 하나로 묶어 이탈을 막아라.
2. **문맥형 내부링크 핀셋 삽입 (핵심)**: 억지로 '관련 글:' 이라 적지 마라! 본문을 전개하는 문장 속에 자연스럽게 <a> 태그를 사용하여 [내 블로그의 다른 글 리스트] 중 2~3개를 연결하라. (예: "... 공항에서 시간 낭비 없이 바로 인터넷을 쓰려면 <a href='URL'>인천공항 주차 꿀팁</a>도 같이 알아두는 게 좋습니다.")
3. **중간 CTA (수익 전환 포인트)**: 설명만 나열하지 말고, 본문 중간(2~3번째 h2 아래)에 독자의 행동을 유도하는 눈에 띄는 텍스트 링크(CTA)를 넣어라. (예: "👉 <a href='#'>지금 가장 많이 쓰는 이심 요금제 50% 할인가 확인하기</a>")
4. **E-E-A-T 신뢰도 외부 링크 (주제에 맞게 딱 3~4개만)**: 신뢰도 상승을 위해 본문 적재적소에 외부 링크를 3~4개 삽입하라. 무조건 똑같은 패턴을 반복하지 말고, **현재 주제와 내용에 가장 알맞은 조합**으로 구성하라. (target="_blank" 필수)
   - 예시 (주제에 맞춰 유연하게 적용): 구글맵 장소 링크 (공항, 현지 명소. 띄어쓰기는 '+' 치환), 관련 판매/예약처 공식 사이트, 통신사/공식 안내 참고 사이트 등.
5. **결정 버튼 (Decision Maker)**: 글 마지막에 '<h3>결론: 그래서 뭐 쓰라고? (상황별 추천)</h3>' 섹션을 무조건 넣어라. "3~5일 짧은 여행 = eSIM 압승", "장기 여행 = 로밍" 등 고민을 완전히 종결지어라.
6. **숫자와 손해 회피 심리 자극**: 비용(원)과 시간(분)을 명확한 숫자로 적어라. (예: "공항 유심 구매 → 30분 소요", "로밍 → 하루 10,000원")
7. **동적 구조 및 시인성**: <table> 1개 이상, <ul><li> 리스트 1개 이상 반드시 사용. <nav>와 본문의 <h2> id는 문맥을 나타내는 영단어(예: id="esim-error-fix")로 매번 다르게 생성하라.

[출력 형식 가이드]: 순수 JSON 형식 문자열로만 반환하라. 절대 마크다운 표기를 포함하지 마라.
JSON Keys: 
- title: 클릭 유발 자극형 제목
- meta_desc: 150자 요약
- meta_keys: 쉼표 구분 키워드
- slug: 영문 짧은 주소
- summary: [이모지+단어] 3개 리스트
- content: HTML 본문
- category: 다음 중 택1 ["여행 교통 팁", "여행 쇼핑 팁", "여행 관광 팁", "여행 준비 팁", "여행 맛집 팁", "생활 정보 꿀팁"]
"""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"✍️ [4/6] {current_persona} 모드로 4,000~6,000자 초고밀도 원고 생성 중... (시도 {attempt + 1})")
            res = requests.post(api_url, json=payload, timeout=180)
            res.raise_for_status()
            
            raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
            raw_text = raw_text.replace("```json", "").replace("```", "").strip()
            
            data = json.loads(raw_text)
            data['used_references'] = [target_blog_url]
            return data
            
        except Exception as e: 
            print(f"⚠️ 제미나이 API 호출 오류: {e}")
            time.sleep(5)
            
    return None

# ==================== [6] 메인 실행 (🔥 지능형 지도 삽입, 광고 최적화) ====================
def run_automation():
    print("🚀 블로그 자동 성장 시스템 가동...")
    
    creds = None
    token_base64 = os.environ.get("BLOGGER_TOKEN_PKL")
    if token_base64:
        with open('token.json', 'wb') as f: 
            f.write(base64.b64decode(token_base64))
            
    if os.path.exists('token.json'):
        with open('token.json', 'rb') as t: 
            creds = pickle.load(t)
        if creds and creds.expired and creds.refresh_token: 
            creds.refresh(Request())
            
    if not creds: 
        print("❌ 인증 정보가 없습니다.")
        return
        
    service = build('blogger', 'v3', credentials=creds)
    print("✅ [1/6] Blogger 인증 완료")

    recent_posts = get_recent_posts(service, BLOG_ID)
    keyword, target_url, scraped_data, title_guide, related_keyword = get_naver_target_data()
    
    filtered_posts = get_related_posts_by_keyword(recent_posts, keyword)
    context_posts = filtered_posts if len(filtered_posts) >= 2 else recent_posts

    data = generate_master_content(keyword, target_url, scraped_data, title_guide, context_posts, related_keyword)
    
    if not data: 
        print("❌ 생성 실패. 키워드를 큐에 재등록합니다.")
        with open(QUEUE_FILE, "a", encoding="utf-8") as f: 
            f.write("\n" + keyword)
        return

    # 🔥 지도 생성 로직 (키워드에서 국가/도시 추출 후 iframe 생성)
    location = extract_location_keyword(keyword)
    map_html = create_map_embed(location)
    print(f"🗺️ [System] '{location}' 기반 구글맵 코드를 생성했습니다.")

    # 하단 보조용 내부링크 (본문에 이미 잘 들어갔겠지만 보강용)
    related_html = ""
    if context_posts:
        related_html = "<div class='related-posts'><h3>📌 같이 보면 돈이 되는 글</h3><ul>"
        for p in random.sample(context_posts, min(3, len(context_posts))): 
            related_html += f'<li><a href="{p["url"]}">{p["title"]}</a></li>'
        related_html += "</ul></div>"

    ads_code = """
    <div style="margin:45px 0;">
        <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2303846706279700" crossorigin="anonymous"></script>
        <ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-2303846706279700" data-ad-slot="1632085406" data-ad-format="auto" data-full-width-responsive="true"></ins>
        <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
    </div>
    """
    card_tag = create_summary_card_tag(data.get('summary', ["핵심정리", "비용절약", "시간단축"]), data['title'])
    content = data['content']

    # HTML 조립 (관련글 -> SVG -> 상단광고 -> 본문)
    top_insertion = f"{related_html}{card_tag}{ads_code}"
    
    if re.search(r'</nav>', content, re.IGNORECASE): 
        content = re.sub(r'(</nav>)', f'\\1{top_insertion}', content, flags=re.IGNORECASE, count=1)
    else: 
        content = top_insertion + content

    # 🔥 지능형 구글맵 위치 선정 로직 (무조건 1번째가 아니라 문맥에 맞는 h2를 찾음)
    h2_pattern = re.compile(r'(<h2[^>]*>.*?</h2>)', re.IGNORECASE)
    h2_tags = h2_pattern.findall(content)
    map_inserted = False
    
    location_keywords = ["위치", "공항", "지도", "가는", "어디", location]
    
    for h2_tag in h2_tags:
        if any(k in h2_tag for k in location_keywords):
            # 위치 키워드가 포함된 h2 바로 아래에 삽입
            content = content.replace(h2_tag, h2_tag + map_html, 1)
            map_inserted = True
            break
            
    if not map_inserted and len(h2_tags) > 0:
        # 적절한 키워드의 h2가 없으면 2번째 h2 (또는 1번째) 아래에 삽입
        target_h2 = h2_tags[1] if len(h2_tags) > 1 else h2_tags[0]
        content = content.replace(target_h2, target_h2 + map_html, 1)

    # 🔥 광고 위치 추가 최적화 (첫 번째 h2 상단 + 중간 + 하단)
    content = re.sub(r'(<h2)', ads_code + r'\1', content, count=1) 
    
    h2_parts = content.split("<h2") 
    if len(h2_parts) >= 4: 
        mid_index = len(h2_parts) // 2
        h2_parts[mid_index] = ads_code + "<h2" + h2_parts[mid_index]
        content = "<h2".join(h2_parts)
        
    content = content + ads_code 

    final_html = f"""
    <meta name="description" content="{data.get('meta_desc', '')}">
    <meta name="keywords" content="{data.get('meta_keys', '')}">
    <style>
        html {{ scroll-behavior: smooth; }} 
        .entry-content {{ font-size: 18px; line-height: 2.1; color: #333; font-family: 'Malgun Gothic', sans-serif; break-word: keep-all; }} 
        .entry-content h2 {{ font-size: 28px; color: #2c3e50; border-left: 10px solid #3498db; padding: 10px 15px; margin: 55px 0 25px; background: #f9f9f9; scroll-margin-top: 120px; }} 
        .entry-content h3 {{ font-size: 23px; color: #2980b9; border-bottom: 2px solid #3498db; padding-bottom: 8px; margin: 35px 0 20px; scroll-margin-top: 120px; }} 
        .entry-content p {{ margin-bottom: 25px; }} 
        .entry-content table {{ width: 100%; border-collapse: collapse; margin: 30px 0; border: 1px solid #ddd; }} 
        .entry-content th {{ background: #3498db; color: white; padding: 12px; }} 
        .entry-content td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }} 
        .entry-content .intro {{ background: #f0f7ff; padding: 15px 20px; border-radius: 10px; border-left: 5px solid #3498db; margin-bottom: 30px; font-weight: bold; font-size: 18px; }} 
        .entry-content nav {{ background: #f8f9fa; padding: 25px; border-radius: 10px; border: 1px solid #eee; margin-bottom: 30px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }} 
        .entry-content nav ul {{ list-style: none; padding-left: 0; }} 
        .entry-content nav a {{ color: #2980b9; text-decoration: none; font-weight: bold; }} 
        .related-posts {{ background: #fdfdfd; padding: 20px; border-radius: 10px; border: 2px dashed #3498db; margin-bottom: 30px; }} 
        .related-posts h3 {{ margin-top: 0; color: #e74c3c; font-size: 20px; }} 
        .related-posts a {{ color: #2c3e50; text-decoration: none; }} 
        b {{ color: #e74c3c; }}
    </style>
    <div class="entry-content">{content}</div>
    """

    chosen_category = data.get('category', '').strip()
    if chosen_category not in LABEL_OPTIONS: 
        chosen_category = "여행 준비 팁" 
        
    final_labels = [chosen_category, "여행 꿀팁"]
    
    try:
        slug_text = data.get('slug', 'auto-post')
        print(f"🚀 [6/6] 업로드 중... ({slug_text})")
        temp_post = service.posts().insert(blogId=BLOG_ID, body={"title": slug_text, "content": "loading...", "labels": final_labels}, isDraft=False).execute()
        service.posts().patch(blogId=BLOG_ID, postId=temp_post['id'], body={"title": data['title'], "content": final_html, "customMetaData": data.get('meta_desc', '')}).execute() 
        print(f"✨ [완료] {data['title']}")
    except Exception as e: 
        print(f"❌ 실패: {e}")
        with open(QUEUE_FILE, "a", encoding="utf-8") as f: 
            f.write("\n" + keyword)

if __name__ == "__main__":
    run_automation()
