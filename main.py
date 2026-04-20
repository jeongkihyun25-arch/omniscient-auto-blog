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

# ==================== [2] 핵심 유틸리티 ====================
def get_best_models():
    print("🔍 [1/6] 최고 모델 라인업 탐색 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    default_models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]

    try:
        res = requests.get(url, timeout=10).json()
        available = [m['name'].replace('models/', '') for m in res.get('models', [])
                     if 'generateContent' in m.get('supportedGenerationMethods', [])]

        if not available:
            return default_models

        priorities = [
            "gemini-2.5-flash",          
            "gemini-2.5-flash-lite",     
            "gemini-2.5-pro",            
            "gemini-2.5-flash-preview",  
        ]

        best_models = []
        seen = set()
        for p in priorities:
            for m in available:
                if p in m and "tts" not in m and "image" not in m and "embedding" not in m and m not in seen:
                    best_models.append(m)
                    seen.add(m)

        if best_models:
            print(f"✅ 선택된 텍스트 전용 모델 리스트: {best_models[:5]}")
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

def generate_alt_text(keyword, context):
    variants = [
        f"{keyword} {context} 설명",
        f"{keyword} {context} 사용 방법",
        f"{keyword} {context} 가이드 이미지",
        f"{keyword} {context} 실제 꿀팁 정리"
    ]
    return random.choice(variants)

def humanize_text(text):
    replacements = [
        ("합니다.", "해요."),
        ("입니다.", "이죠."),
        ("중요합니다.", "꽤 중요하더라고요."),
        ("추천합니다.", "찐으로 추천해요!"),
        ("좋습니다.", "확실히 편했어요.")
    ]
    for a, b in replacements:
        if random.random() < 0.3:
            text = text.replace(a, b)
    return text

def break_paragraphs(text):
    sentences = text.split(". ")
    result = ""
    for s in sentences:
        result += s + ". "
        if random.random() < 0.2:
            result += "\n\n"  
    return result

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

# ==================== [3] 네이버 수집 ====================
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

# ==================== [4] 유동적 SVG 요약 카드 ====================
def create_summary_card_tag(summary_list, alt_text):
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
    return f'<div style="text-align:center; margin:30px 0;"><img src="data:image/svg+xml;base64,{b64_svg}" style="max-width:100%; height:auto; border-radius:15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);" alt="{alt_text}"/></div>'

# ==================== [5] 원고 생성 ====================
def generate_master_content(keyword, target_blog_url, scraped_data, title_guide, context_posts, related_keyword, skeleton_title):
    models_to_try = get_best_models() 

    personas = [
        "가성비 헌터 블로거", "효율 극대화 출장러", "디테일 끝판왕 J형 여행가",
        "처음 여행하는 사람 시점", "귀찮음 극혐형 인간", "현지인 빙의 여행객",
        "프로 봇짐러", "사진에 미친 여행자"
    ]
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
초반에 반드시 "결론부터 말하면, 핵심은 단 하나입니다."와 같은 형태로 1가지 명확한 핵심을 던지고 시작하라.

[10개 블로그 분석 데이터]: 
{scraped_data}

[미션]: 독자가 즉시 '결정'을 하도록 유도하는, 4,000자~6,000자 분량의 초고밀도 전환형 포스팅을 작성하라.

[🔥 핵심 강제 지시사항 - 서식 깨짐 절대 방지 및 블로그 최적화]:
1. **HTML 포맷 및 목차(TOC) 강제 (매우 중요)**: 
   - 마크다운(`##`, `**`) 절대 금지! 오직 순수 HTML 태그만 사용.
   - 본문 최상단에 반드시 `<nav><div class='toc-title'>목차</div><ul>...</ul></nav>` 형태의 목차를 작성하라.
   - 목차의 링크는 `<a href='#sec1'>` 형태로 앵커를 달고, 본문의 소제목 <h2> 태그에는 반드시 `<h2 id='sec1'>` 처럼 id를 일치시켜 클릭 시 정확히 이동하게 하라.
2. **문맥형 내부링크 (자연 삽입 강제)**: 'Related:' 같은 단독 문단 금지. 문장 안에 자연스럽게 버튼 스타일을 적용해라. (예: <a href='URL' target='_blank' class='int-link'>꿀팁 알아보기 (🔗관련글)</a>)
3. **중간 CTA (수익 전환 포인트)**: 본문 중간에 클릭을 유도하는 링크를 1개 이상 배치하라. (예: 👉 지금 가장 많이 쓰는 요금제 확인하기)

4. **🔥무조건 접속되는 안전한 외부 링크 (3개 정도만)**: 
   - 가짜 URL(없는 공식 홈페이지 등)로 연결되어 에러가 나는 것을 방지하기 위해, 모든 외부 링크의 URL은 **반드시 구글 검색 결과 URL** 또는 **구글 맵 검색 URL**만 사용하라.
   - 장소 검색 예시: `<a href='https://www.google.com/maps/search/?api=1&query=검색할+장소명' target='_blank' class='ext-link'>장소 구글맵 확인 <span style='font-size:12px;'>(👉클릭하면 이동)</span></a>`
   - 정보 검색 예시: `<a href='https://www.google.com/search?q=검색할+단어+조합' target='_blank' class='ext-link'>최신 정보 구글 검색하기 <span style='font-size:12px;'>(👉클릭하면 이동)</span></a>`

5. **결정 버튼**: 본문 맨 마지막에 `<h2 id='conclusion'>결론: 그래서 뭐 쓰라고? (상황별 추천)</h2>` 태그를 사용해라.
6. **표(Table)와 리스트(List) 절대 엄수**: 
   - 비교/정리 정보는 반드시 `<div class='table-wrapper'><table><tr><th>...</th></tr><tr><td>...</td></tr></table></div>` 형태의 HTML 표로 작성하라.
   - 텍스트 나열은 `<p>` 대신 `<ul><li>...</li></ul>`를 적극 활용해 가독성을 높여라.
7. **SVG 길이**: JSON의 `summary` 단어들은 무조건 6글자 이하로 3개 작성.

[🌟 품질 필터 및 휴먼 톤(Human Tone) 작성 지침]:
- 기계식 서론 금지: 검색 과정 등 군더더기 금지. 곧바로 독자에게 필요한 '핵심 혜택'부터 강력하게 던져라.
- 리얼리티 경험담: 친한 회원에게 썰 푸는 말투(~했어요, 솔직히 말해서 등) 사용.
- 완벽한 정보 금지: 일부는 경험처럼 풀고, 반말 느낌이나 감탄문 1~2개 허용.
- 이유+결과 공식: 모든 문장은 "이유+결과"를 적어라.

🔥 [JSON 에러 절대 방지 강제 규칙]: 본문(content) 안에 들어가는 모든 HTML 속성(href, class, id, style 등)에는 반드시 **작은따옴표(')**만 사용하라! (예: <a href='링크' class='버튼' style='color:red;'>). 값 내부에 큰따옴표(")가 섞이면 시스템이 파괴되므로 무조건 금지한다.

[출력 형식 가이드]: 순수 JSON 형식 문자열로만 반환하라.
JSON Keys: 
- title: 클릭 유발 자극형 제목
- meta_desc: 150자 요약
- meta_keys: 쉼표 구분 키워드
- slug: 영문 짧은 주소
- summary: [짧은단어, 짧은단어, 짧은단어] (6글자 이하)
- map_location: 내용과 연관성 높은 랜드마크
- content: 최상단 <nav> 목차와 id가 부여된 <h2> 태그, 완벽한 table/ul 등이 포함된 순수 HTML 본문
- category: ["여행 교통 팁", "여행 쇼핑 팁", "여행 관광 팁", "여행 준비 팁", "여행 맛집 팁", "생활 정보 꿀팁"] 중 택1
"""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }

    for attempt, model_name in enumerate(models_to_try, 1):
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        try:
            print(f"✍️ [4/6] 시도 {attempt}: {model_name} 모델 사용 중...")
            res = requests.post(api_url, json=payload, timeout=180)
            res.raise_for_status() 
            
            raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
            raw_text = raw_text.replace("```json", "").replace("```", "").strip()
            
            data = json.loads(raw_text)
            data['used_references'] = [target_blog_url]
            return data 
            
        except Exception as e:
            if "503" in str(e) or "429" in str(e) or "unavailable" in str(e).lower():
                wait_time = 15 * attempt 
                print(f"⚠️ {model_name} 과부하 감지 → {wait_time}초 대기 후 다음 모델로 전환합니다.")
                time.sleep(wait_time)
                continue 
            else:
                print(f"🚨 모델 에러 ({model_name}): {e}")
                time.sleep(5)
                continue

    print("❌ 모든 모델 시도가 실패했습니다.")
    return None

# ==================== [6] 메인 실행 ====================
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
    
    alt_text = generate_alt_text(keyword, "핵심 요약")
    card_tag = create_summary_card_tag(data.get('summary', ["핵심정리", "비용절약", "시간단축"]), alt_text)
    
    content = data['content']
    
    content = humanize_text(content)
    content = break_paragraphs(content)

    content = re.sub(r'^##\s+(.+)$', r'<h2>\1</h2>', content, flags=re.MULTILINE)
    content = re.sub(r'^###\s+(.+)$', r'<h3>\1</h3>', content, flags=re.MULTILINE)
    content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
    
    if "<p>" not in content and "<br>" not in content:
        content = content.replace('\n\n', '<br><br>').replace('\n', '<br>')

    top_insertion = f"{card_tag}{ads_code}"
    nav_match = re.search(r'</nav>', content, re.IGNORECASE)
    if nav_match:
        content = insert_html_at_pos(content, top_insertion, nav_match.end())
    else:
        content = top_insertion + content

    content = re.sub(r'(<h2[^>]*>)', ads_code + r'\1', content, count=1)

    h2_matches = list(re.finditer(r'<h2[^>]*>(.*?)</h2>', content, re.IGNORECASE | re.DOTALL))
    map_inserted = False
    
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

    h2_matches = list(re.finditer(r'<h2[^>]*>', content, re.IGNORECASE))
    if len(h2_matches) >= 3:
        mid_idx = len(h2_matches) // 2
        content = insert_html_at_pos(content, ads_code, h2_matches[mid_idx].start())

    content += ads_code 

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
        
        .entry-content a {{ color: #2980b9; text-decoration: underline; font-weight: bold; transition: all 0.2s; }}
        .entry-content a:hover {{ color: #1f618d; }}
        .ext-link {{ color: #fff !important; background-color: #e67e22; padding: 4px 12px; border-radius: 6px; text-decoration: none !important; display: inline-block; margin: 5px 0; font-size: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-bottom: none; }}
        .ext-link:hover {{ background-color: #d35400; }}
        .int-link {{ color: #fff !important; background-color: #3498db; padding: 4px 12px; border-radius: 6px; text-decoration: none !important; display: inline-block; margin: 5px 0; font-size: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-bottom: none; }}
        .int-link:hover {{ background-color: #2980b9; }}
        .anchor-link {{ color: #27ae60 !important; background-color: #eafaf1; padding: 4px 10px; border-radius: 6px; text-decoration: none !important; font-size: 16px; display: inline-block; margin: 5px 0; border: 1px solid #2ecc71; }}
        
        .entry-content .intro {{ background: #f0f7ff; padding: 18px 22px; border-radius: 10px; border-left: 6px solid #3498db; margin-bottom: 30px; font-weight: bold; font-size: 17px; line-height: 1.7; }} 
    </style>
    <div class="entry-content">{content}</div>
    """

    chosen_category = data.get('category', '').strip()
    if chosen_category not in LABEL_OPTIONS: 
        chosen_category = "여행 준비 팁" 
        
    final_labels = [chosen_category, "여행 꿀팁"]
    
    sleep_time = random.randint(180, 600)
    print(f"⏳ [System] 봇으로 걸리지 않기 위해 {sleep_time}초 대기 후 발행합니다...")
    time.sleep(sleep_time)
    
    try:
        slug_text = data.get('slug', 'auto-post')
        print(f"🚀 [6/6] 최종 업로드 중... ({slug_text})")
        temp_post = service.posts().insert(blogId=BLOG_ID, body={"title": slug_text, "content": "loading...", "labels": final_labels}, isDraft=False).execute()
        service.posts().patch(blogId=BLOG_ID, postId=temp_post['id'], body={"title": data['title'], "content": final_html, "customMetaData": data.get('meta_desc', '')}).execute() 
        print(f"✨ [완료] {data['title']}")
    except Exception as e: 
        print(f"❌ 실패: {e}")
        with open(QUEUE_FILE, "a", encoding="utf-8") as f: 
            f.write("\n" + keyword)

if __name__ == "__main__":
    run_automation()