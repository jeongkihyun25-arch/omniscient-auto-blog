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

# ==================== [2] 핵심 유틸리티 (모델 리스트 최적화) ====================
def get_best_models():
    """서버 과부하 대비 최강의 모델 라인업 
    - 2.0-flash 완전 제거 (Retirement 대비 안정성 확보)
    - Flash-Lite를 과부하 방어용으로 앞쪽 배치
    """
    print("🔍 [1/6] 최고 모델 라인업 탐색 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    
    # 최종 안전망 (2.5 시리즈 고정)
    default_models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]

    try:
        res = requests.get(url, timeout=10).json()
        available = [m['name'].replace('models/', '') for m in res.get('models', [])
                     if 'generateContent' in m.get('supportedGenerationMethods', [])]

        if not available:
            return default_models

        # 과부하 대비 우선순위 (Lite를 2순위로 전진 배치)
        priorities = [
            "gemini-2.5-flash",          # 1순위
            "gemini-2.5-flash-lite",     # 2순위 (과부하 대피소)
            "gemini-2.5-pro",            # 3순위
            "gemini-2.5-flash-preview",  # 4순위
        ]

        best_models = []
        seen = set()
        for p in priorities:
            for m in available:
                if p in m and m not in seen:
                    best_models.append(m)
                    seen.add(m)

        if best_models:
            print(f"✅ 선택된 모델 리스트: {best_models[:5]}")
            return best_models

        return default_models

    except Exception as e:
        print(f"⚠️ 모델 리스트 호출 실패: {e} → 기본 리스트 사용")
        return default_models

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

def create_map_embed(location):
    query = urllib.parse.quote(location)
    map_link = f"https://maps.google.com/maps?q={query}"
    
    return f'''
    <div style="margin:40px 0; border-radius:12px; overflow:hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.1); background:#fff; padding:15px; text-align:center;">
        <iframe 
            src="{map_link}&t=&z=13&ie=UTF8&iwloc=&output=embed"
            width="100%" height="350" style="border:0; border-radius:8px;"
            allowfullscreen="" loading="lazy">
        </iframe>
        <a href="{map_link}" target="_blank" style="display:inline-block; margin-top:15px; padding:12px 25px; background-color:#3498db; color:#fff; font-weight:bold; font-size:16px; border-radius:8px; text-decoration:none; box-shadow: 0 2px 5px rgba(0,0,0,0.2);">🗺️ {location} 지도를 클릭해서 위치를 참고하세요 (새창 열기)</a>
    </div>
    '''

def insert_html_at_pos(html_content, insert_str, pos):
    return html_content[:pos] + insert_str + html_content[pos:]

# ==================== [3] 네이버 수집 (🔥 기존 완벽한 로직 100% 유지) ====================
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
    
    print(f"🎯 [2/6] 키워드: {target_query} (검색어: {actual_search_query})")

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    valid_links = []
    scraped_data = ""
    target_blog_url = ""
    skeleton_title = "" 

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
            skeleton_title = selected_links[0]['title'] 
            print(f"🔍 [3/6] 총 {len(selected_links)}개 블로그 추출 중... (뼈대: {skeleton_title})")
            
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
    return target_query, target_blog_url, scraped_data, title_guide, related_keyword, skeleton_title

# ==================== [4] 유동적 SVG 요약 카드 (🔥 6글자 강제 커팅으로 깨짐 완벽 방지) ====================
def create_summary_card_tag(summary_list, title):
    # 🔥 파이썬 단에서 무조건 6글자로 강제 커팅하여 세로 깨짐 완벽 차단
    safe_list = [str(s).strip()[:6] for s in summary_list if s][:3]
    while len(safe_list) < 3: safe_list.append("") 
    svg_code = f"""
    <svg width="100%" height="200" viewBox="0 0 600 200" xmlns="http://www.w3.org/2000/svg">
      <rect width="600" height="200" fill="#FFF9C4" rx="15"/>
      <text x="50%" y="65" font-family="'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="24" text-anchor="middle" fill="#2c3e50">{safe_list[0]}</text>
      <text x="50%" y="110" font-family="'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="24" text-anchor="middle" fill="#2c3e50">{safe_list[1]}</text>
      <text x="50%" y="155" font-family="'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="24" text-anchor="middle" fill="#2c3e50">{safe_list[2]}</text>
    </svg>
    """
    b64_svg = base64.b64encode(svg_code.encode('utf-8')).decode('utf-8')
    return f'<div style="text-align:center; margin:30px 0;"><img src="data:image/svg+xml;base64,{b64_svg}" style="max-width:100%; height:auto; border-radius:15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);" alt="{title} 핵심 요약"/></div>'

# ==================== [5] 원고 생성 (🔥 문맥 링크, 지능형 장소 반환, 외부링크 강제) ====================
def generate_master_content(keyword, target_blog_url, scraped_data, title_guide, context_posts, related_keyword, skeleton_title):
    # 1. 모델 리스트를 먼저 확보합니다. (복수형 s 확인 완료)
    models_to_try = get_best_models() 

    personas = ["가성비 헌터 블로거", "효율 극대화 프로 출장러", "디테일 끝판왕 J형 여행가"]
    current_persona = random.choice(personas)
    recent_posts_str = "\n".join([f"- 제목: {p['title']} (URL: {p['url']})" for p in context_posts])

    prompt = f"""
[타겟 키워드]: {keyword}
[권장 제목 뼈대]: {title_guide}
[페르소나]: {current_persona} 
[내 블로그 다른 글 리스트]: 
{recent_posts_str}

[🔥 이번 글의 핵심 메인 테마]: 
제공된 뼈대 블로그의 제목인 **[{skeleton_title}]**이 다루는 특정 상황, 심층 꿀팁을 이번 포스팅의 핵심 앵글로 삼아라. 

[10개 블로그 분석 데이터]: 
{scraped_data}

[미션]: 독자가 즉시 '결정'을 하도록 유도하는, 4,000자~6,000자 분량의 초고밀도 전환형 포스팅을 작성하라.

[🔥 핵심 강제 지시사항 - 에러 방지 및 신뢰도 폭발]:
1. **문맥형 내부링크 (매우 중요)**: '관련 글 박스'나 'Related:' 같은 단독 문단을 절대 만들지 마라! 오직 본문을 설명하는 문장 중간에 자연스럽게 <a> 태그를 녹여서 [내 블로그 다른 글 리스트] 중 1~2개를 연결하되, 반드시 버튼 스타일 클래스와 새창열기를 적용하라. (예: "...이럴 때는 <a href='URL' target='_blank' class='int-link'>미리 예약하는 꿀팁 (🔗관련글 보기)</a>을 참고하면 좋습니다.")
2. **외부 링크 무조건 3개 이상 강제 삽입 (신뢰도 E-E-A-T)**: 글의 내용과 연관된 유효한 외부 링크를 반드시 3개 이상 본문 적재적소에 배치하라. 아래 형태의 `<a class="ext-link">` 코드를 반드시 써라!
   - 구글맵 검색 링크 (예: <a href="https://www.google.com/maps/search/?api=1&query=신주쿠+교엔" target="_blank" class="ext-link">신주쿠 교엔 위치 확인 (👉외부링크 이동)</a>)
   - 구글 정보 검색 링크 (예: <a href="https://www.google.com/search?q=일본+eSIM+추천" target="_blank" class="ext-link">일본 eSIM 최신 할인 정보 검색 (👉외부링크 이동)</a>)
   - 공식 홈페이지 또는 예약처 링크 1개 이상 필수.
3. **결정 버튼**: 본문 맨 마지막에 `<h2>결론: 그래서 뭐 쓰라고? (상황별 추천)</h2>` 태그를 사용해라. (<h3> 태그 절대 금지)
4. **표(Table) 깨짐 방지**: 대조가 필요한 정보는 반드시 `<div class="table-wrapper"><table>...</table></div>` 형태의 표를 사용하라.
5. **SVG 텍스트 길이 제한**: JSON의 `summary` 배열 안의 단어들은 무조건 띄어쓰기 포함 **6글자 이하**의 짧은 핵심 명사로만 3개 적어라. (예: ["환전 꿀팁", "경비 절약", "실제 후기"])

[출력 형식 가이드]: 순수 JSON 형식 문자열로만 반환하라. 절대 마크다운 표기를 포함하지 마라.
JSON Keys: 
- title: 클릭 유발 자극형 제목
- meta_desc: 150자 요약
- meta_keys: 쉼표 구분 키워드
- slug: 영문 짧은 주소
- summary: [짧은단어, 짧은단어, 짧은단어] (각각 무조건 6글자 이하)
- map_location: 이 글의 내용과 가장 관련성 높은 구체적인 랜드마크, 공항, 또는 지역명 (예: 오사카 간사이 공항, 다낭 한시장, 인천공항 제1여객터미널. 일반 정보 글이면 인천공항으로 설정)
- content: HTML 본문
- category: 다음 중 택1 ["여행 교통 팁", "여행 쇼핑 팁", "여행 관광 팁", "여행 준비 팁", "여행 맛집 팁", "생활 정보 꿀팁"]
"""
payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }

# 2. 🔥 모델 리스트를 하나씩 순회하며 시도합니다.
    for attempt, model_name in enumerate(models_to_try, 1):
        
        # ✅ [이 줄이 반드시 여기에 있어야 합니다!] 
        # 루프 안에서 매번 'model_name'을 받아와서 주소를 생성해야 합니다.
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        
        try:
            print(f"✍️ [4/6] 시도 {attempt}: {model_name} 모델 사용 중...")
            res = requests.post(api_url, json=payload, timeout=180)
            res.raise_for_status() 
            
            raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
            raw_text = raw_text.replace("```json", "").replace("```", "").strip()
            
            data = json.loads(raw_text)
            data['used_references'] = [target_blog_url]
            return data # 성공 시 즉시 반환하며 종료
            
        except Exception as e:
            # 서버 과부하(503)나 요청제한(429) 시 대기 후 다음 모델로 이동
            if "503" in str(e) or "429" in str(e) or "unavailable" in str(e).lower():
                wait_time = 8 * attempt 
                print(f"⚠️ {model_name} 과부하 감지 → {wait_time}초 대기 후 다음 모델로 전환합니다.")
                time.sleep(wait_time)
                continue # 다음 모델로 루프 재시작
            else:
                print(f"🚨 모델 에러 ({model_name}): {e}")
                time.sleep(5)
                continue

    print("❌ 모든 모델 시도가 실패했습니다.")
    return None

# ==================== [6] 메인 실행 (🔥 로직 최적화) ====================
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
    keyword, target_url, scraped_data, title_guide, related_keyword, skeleton_title = get_naver_target_data()
    
    filtered_posts = get_related_posts_by_keyword(recent_posts, keyword)
    context_posts = filtered_posts if len(filtered_posts) >= 2 else recent_posts

    data = generate_master_content(keyword, target_url, scraped_data, title_guide, context_posts, related_keyword, skeleton_title)
    
    if not data: 
        print("❌ 생성 실패. 키워드를 큐에 재등록합니다.")
        with open(QUEUE_FILE, "a", encoding="utf-8") as f: 
            f.write("\n" + keyword)
        return

    # 🔥 지도 생성 (제미나이가 직접 추출한 가장 연관성 높은 장소 활용!)
    location = data.get('map_location', '인천공항 제1여객터미널').strip()
    map_html = create_map_embed(location)
    print(f"🗺️ [System] AI가 분석한 '{location}' 기반 구글맵 코드를 생성했습니다.")

    ads_code = """
    <div style="margin:45px 0;">
        <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2303846706279700" crossorigin="anonymous"></script>
        <ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-2303846706279700" data-ad-slot="1632085406" data-ad-format="auto" data-full-width-responsive="true"></ins>
        <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
    </div>
    """
    
    # SVG 카드는 파이썬 단에서 강제로 6글자 슬라이싱 적용
    card_tag = create_summary_card_tag(data.get('summary', ["핵심정리", "비용절약", "시간단축"]), data['title'])
    content = data['content']

    # 1. 상단 삽입 (관련글 박스 아예 뺌, 오직 문맥 링크만 유지)
    top_insertion = f"{card_tag}{ads_code}"
    nav_match = re.search(r'</nav>', content, re.IGNORECASE)
    if nav_match:
        content = insert_html_at_pos(content, top_insertion, nav_match.end())
    else:
        content = top_insertion + content

    # 2. 지도 삽입 (위치/공항 등 관련 단어가 들어간 h2 닫는 태그 직후)
    h2_matches = list(re.finditer(r'<h2[^>]*>(.*?)</h2>', content, re.IGNORECASE | re.DOTALL))
    map_inserted = False
    
    # AI가 뽑아준 위치나 관련 단어가 소제목에 있으면 바로 밑에 삽입
    location_keywords = ["위치", "공항", "지도", "가는", "어디", location.split()[0]]
    
    for match in h2_matches:
        h2_text = match.group(1)
        if any(k in h2_text for k in location_keywords):
            content = insert_html_at_pos(content, map_html, match.end())
            map_inserted = True
            break
            
    if not map_inserted and len(h2_matches) > 0:
        target_match = h2_matches[1] if len(h2_matches) > 1 else h2_matches[0]
        content = insert_html_at_pos(content, map_html, target_match.end())

    # 3. 중간 및 하단 광고 삽입 
    h2_matches = list(re.finditer(r'<h2[^>]*>', content, re.IGNORECASE))
    if len(h2_matches) >= 3:
        mid_idx = len(h2_matches) // 2
        content = insert_html_at_pos(content, ads_code, h2_matches[mid_idx].start())

    content += ads_code 

    # 🔥 CSS (표, 리스트 안정화 및 외부/내부 링크 디자인 완벽 분리)
    final_html = f"""
    <meta name="description" content="{data.get('meta_desc', '')}">
    <meta name="keywords" content="{data.get('meta_keys', '')}">
    <style>
        html {{ scroll-behavior: smooth; }} 
        .entry-content {{ font-size: 16px; line-height: 1.8; color: #333; font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; word-break: keep-all; }} 
        .entry-content h2 {{ font-size: 24px !important; color: #2c3e50; border-left: 6px solid #3498db; padding: 8px 15px; margin: 45px 0 20px; background: #f8f9fa; scroll-margin-top: 100px; }} 
        .entry-content h3 {{ font-size: 20px !important; color: #2980b9; border-bottom: 2px solid #3498db; padding-bottom: 8px; margin: 30px 0 15px; scroll-margin-top: 100px; }} 
        .entry-content p {{ margin-bottom: 20px; font-size: 16px; }} 
        
        .table-wrapper {{ width: 100%; overflow-x: auto; margin: 25px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border-radius: 8px; }}
        .entry-content table {{ width: 100%; min-width: 500px; border-collapse: collapse; background: #fff; font-size: 15px; }} 
        .entry-content th {{ background: #3498db; color: white; padding: 12px; border: 1px solid #2980b9; font-weight:bold; white-space: nowrap; }} 
        .entry-content td {{ border: 1px solid #ddd; padding: 12px; text-align: left; vertical-align: middle; }} 
        
        .entry-content ul {{ background: #fdfdfd; border-radius: 8px; padding: 20px 20px 20px 40px; border: 1px solid #eee; margin: 20px 0; }}
        .entry-content li {{ margin-bottom: 10px; font-size: 16px; line-height: 1.7; }}
        
        .entry-content nav {{ background: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #eee; margin-bottom: 30px; }} 
        .toc-title {{ font-size: 18px; font-weight: bold; color: #2c3e50; margin-bottom: 15px; border-bottom: 2px solid #3498db; padding-bottom: 8px; }}
        .entry-content nav ul {{ background: transparent; border: none; padding: 0; margin: 0; list-style: none; }} 
        .entry-content nav li {{ margin-bottom: 10px; }}
        .entry-content nav a {{ color: #34495e; text-decoration: none; font-size: 16px; font-weight: 600; border-bottom: 1px dashed #bdc3c7; transition: color 0.3s; }} 
        .entry-content nav a:hover {{ color: #3498db; border-bottom-color: #3498db; }}
        
       /* 🔥 링크 디자인 완벽 분리 */
        .entry-content a { color: #2980b9; text-decoration: underline; font-weight: bold; transition: all 0.2s; }
        .entry-content a:hover { color: #1f618d; }
        .ext-link { color: #fff !important; background-color: #e67e22; padding: 4px 12px; border-radius: 6px; text-decoration: none !important; display: inline-block; margin: 5px 0; font-size: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-bottom: none; }
        .ext-link:hover { background-color: #d35400; }
        .int-link { color: #fff !important; background-color: #3498db; padding: 4px 12px; border-radius: 6px; text-decoration: none !important; display: inline-block; margin: 5px 0; font-size: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-bottom: none; }
        .int-link:hover { background-color: #2980b9; }
        .anchor-link { color: #27ae60 !important; background-color: #eafaf1; padding: 4px 10px; border-radius: 6px; text-decoration: none !important; font-size: 16px; display: inline-block; margin: 5px 0; border: 1px solid #2ecc71; }
        
        .entry-content .intro {{ background: #f0f7ff; padding: 18px 22px; border-radius: 10px; border-left: 6px solid #3498db; margin-bottom: 30px; font-weight: bold; font-size: 17px; line-height: 1.7; }} 
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
