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
    "공항": ["eSIM", "수하물 규정", "스마트패스", "라운지 무료", "환전 수수료"],
    "eSIM": ["로밍 요금", "데이터 안터질 때", "아이폰 eSIM 설정", "포켓와이파이 비교"],
    "유심": ["로밍 요금", "eSIM 추천", "비행기 유심 교체"],
    "일본": ["비지트 재팬", "돈키호테 쇼핑", "다이소 추천템", "교통패스 비교", "트래블로그"],
    "베트남": ["다낭 마사지", "그랩 사용법", "베트남 환전 꿀팁", "호이안 투어", "가성비 숙소"],
    "태국": ["방콕 맛집", "GLN 스캔 결제", "태국 환전", "마사지 팁", "짜뚜짝 시장"],
    "미국": ["ESTA 비자", "여행자 보험", "팁 문화", "렌터카 주의사항", "뉴욕 패스"],
    "유럽": ["소매치기 방지", "유레일 패스", "텍스리펀", "솅겐 조약", "유럽 로밍"],
    "숙소": ["아고다 할인코드", "에어비앤비 캐시백", "호텔 디파짓", "얼리 체크인"],
    "비행기": ["좌석 지정 꿀팁", "기내 반입 금지", "항공권 싸게 사는 법", "비상구 좌석"]
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
    # 🔥 현재 시간을 가져와서 제목에 자동 반영 (예: 2026년 4월 최신판!)
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    # 1. 시선을 끄는 서두 (Prefix) - 현재 연/월 자동 적용
    prefixes = [
        f"{current_year}년 최신판!", f"{current_month}월 여행 준비,", "찐후기 주의,", 
        "현지인만 아는", "안 보면 무조건 손해!", "솔직히 말해서", 
        "공유하기 아까운", "결론부터 말하면", "초보자 필독!", 
        "실제 경험담:", "광고 없음!", "10년 차 여행가의", 
        "역대급 꿀팁,", "드디어 공개!", "급하신 분들만 보세요,"
    ]
    
    # 2. 핵심 가치 제안 (Value Hook)
    hooks = [
        f"{keyword} 비용 0원 비법", f"{keyword} 딱 3 가지만 기억하세요",
        f"실패 없는 {keyword} 전략", f"남들 다 속는 {keyword}의 진실",
        f"{keyword} 3분 만에 끝내는 요약", f"의외로 모르는 {keyword} 디테일",
        f"{keyword} 때문에 시간 버리지 마세요", f"{keyword} 완벽 비교 분석",
        f"돈 버는 {keyword} 활용법", f"가장 쉬운 {keyword} 가이드",
        f"{keyword} 장단점 팩트체크", f"{keyword} 설정 오류 해결법"
    ]
    
    # 3. 신뢰 및 감정 요소 (Emotion/Proof)
    proofs = [
        "(직접 해본 결과)", "(Feat. 내돈내산)", "(실제 후기 포함)", 
        "(진짜 핵심만)", "(부작용 주의)", "(의외의 정답)", 
        "(정리 끝판왕)", "(꿀팁 방출)", "(현장 사진 포함)"
    ]
    
    # 4. 마지막 자극 (Suffix)
    suffixes = [
        "확인해 보세요 🚀", "지금 바로 보기", "전격 비교!", 
        "이 글 하나로 끝내세요", "놓치면 후회합니다", "정답 공개 ✨", 
        "꼭 알고 가세요", "완벽 정리 완료"
    ]

    p = random.choice(prefixes)
    h = random.choice(hooks)
    pr = random.choice(proofs)
    s = random.choice(suffixes)

    return f"{p} {h} {pr} {s}"

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

# 기존 get_recent_posts 함수 전체를 이걸로 교체하세요.
def get_recent_posts(service, blog_id):
    try:
        # 🔥 최근 40개의 글을 가져와서 중복을 피합니다!
        posts = service.posts().list(blogId=blog_id, maxResults=40, fetchBodies=False).execute()
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
def get_naver_target_data(recent_posts): # 매개변수 추가됨!
    recent_titles = [p['title'] for p in recent_posts]
    now = datetime.now()
    
    COUNTRY_GROUPS = [
        ["일본", "대만", "홍콩", "중국", "마카오"],            
        ["베트남", "태국", "필리핀", "인도네시아", "발리"],  
        ["미국", "캐나다", "하와이", "괌", "사이판"],                
        ["프랑스", "이탈리아", "스페인", "영국", "스위스"]     
    ]
    group_index = now.month % len(COUNTRY_GROUPS)
    current_group = COUNTRY_GROUPS[group_index]
    main_country = current_group[0] 
    sub_country = random.choice(current_group[1:]) if len(current_group) > 1 else main_country
    
    BASE_KEYWORDS = [
        "인천공항 주차 요금", "인천공항 혼잡 시간", "출국 수속 시간", "스마트패스 사용법", "공항 라운지 무료 이용",
        "해외 로밍 요금", "eSIM 추천", "eSIM 안될 때", "유심 vs eSIM 비교", "트래블로그 트래블월렛 비교",
        "GLN 결제 방법", "아고다 할인코드", "항공권 싸게 사는 법", "여행자 보험 꼭 필요한가", "기내 반입 금지 품목",
        f"{main_country} 입국신고서", f"{main_country} 교통패스", f"{main_country} 돈키호테 쇼핑리스트", 
        f"{main_country} 유심 eSIM 추천", f"{main_country} 택스리펀", f"{main_country} 날씨 옷차림",
        f"{sub_country} 여행 준비물", f"{sub_country} 가볼만한곳", f"{sub_country} 가성비 숙소", f"{sub_country} 그랩 사용법"
    ]

    if not os.path.exists(QUEUE_FILE) or os.stat(QUEUE_FILE).st_size == 0:
        sorted_keys = prioritize_keywords(BASE_KEYWORDS) + PRIORITY_KEYWORDS  
        with open(QUEUE_FILE, "w", encoding="utf-8") as f: f.write("\n".join(sorted_keys))

    with open(QUEUE_FILE, "r", encoding="utf-8") as f: lines = f.read().splitlines()
    if not lines: 
        lines = prioritize_keywords(BASE_KEYWORDS) + PRIORITY_KEYWORDS

    # 🔥 중복 방지 핵심 로직: 큐에 있는 키워드가 최근 40개 글 제목에 있으면 패스!
    target_query = None
    for query in lines:
        core_word = query.split()[0] # 예: "일본 환전"에서 "일본" 추출
        if not any(core_word in title for title in recent_titles):
            target_query = query
            break
            
    # 만약 큐에 있는 게 전부 다 겹치면(그럴 확률은 적지만), 랜덤으로 하나 뽑음
    if not target_query: 
        target_query = random.choice(lines)
    
    title_guide = generate_title_variants(target_query)
    related_keyword = get_content_chain(target_query)
    
    # 사용한 키워드는 맨 아래로 보냄
    if target_query in lines:
        lines.remove(target_query)
        lines.append(target_query)
        with open(QUEUE_FILE, "w", encoding="utf-8") as f: f.write("\n".join(lines))

   # 🔥 검색어 꼬리표를 대폭 확장하여 네이버에서 매번 새로운 뼈대 글을 수집하게 만듭니다.
    search_suffix = [
        # 기본 정보 & 꿀팁
        " 장단점", " 꿀팁", " 사용법", " 완벽 가이드", " 총정리", " 비교 추천",
        # 문제 해결 & 주의사항
        " 설정 오류", " 안터짐", " 환불", " 주의사항", " 실패 후기", " 치명적 단점",
        # 신뢰도 & 후기
        " 실제 후기", " 내돈내산", " 팩트체크", " 솔직 리뷰", " 한달 사용기",
        # 비용 & 혜택
        " 가격 비교", " 할인 팁", " 비용 절약", " 무료 혜택", " 최저가 예약"
    ]
    actual_search_query = f"{target_query}{random.choice(search_suffix)}"
    
    print(f"🎯 [2/6] 키워드: {target_query} (검색어: {actual_search_query})")
    
    # 셀레니움 수집 로직 (이하 기존과 동일)
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
    # 🔥 이모지 포함되도록 글자수 컷을 10글자로 넉넉하게!
    safe_list = [str(s).strip()[:10] for s in summary_list if s][:3]
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

# ==================== [5] 원고 생성 (🔥 하네스: 5000자 밀도 / 1등 DNA 흡수 / 지능형 지도 / 휴먼톤 & 개인정보 변형) ====================
def generate_master_content(keyword, target_blog_url, scraped_data, title_guide, context_posts, related_keyword, skeleton_title):
    models_to_try = get_best_models() 

    personas = [
        "가성비 헌터 블로거", "효율 극대화 출장러", "디테일 끝판왕 J형 여행가",
        "처음 여행하는 사람 시점", "귀찮음 극혐형 인간", "현지인 빙의 여행객",
        "프로 봇짐러", "사진에 미친 여행자"
    ]
    current_persona = random.choice(personas)
    
    # 내부링크용 메뉴판 생성 (최대 10개)
    menu_posts = context_posts[:10] 
    recent_titles_str = "\n".join([f"- [ID: {i}] 제목: {p['title']}" for i, p in enumerate(menu_posts)])

    # -------------------------------------------------------------------
    # 👨‍🎨 [1단계 API] 메인 작가 AI (본문 HTML 작성 - 초고밀도 & 진화형 모방)
    # -------------------------------------------------------------------
    prompt_writer = f"""
[타겟 키워드]: {keyword}
[페르소나]: {current_persona} 
[내 블로그 관련 글 메뉴판]: 
{recent_titles_str}

[🔥 5,000자 초고밀도 '모방 후 진화' 미션]: 
제공된 [10개 블로그 분석 데이터]와 뼈대 제목 **[{skeleton_title}]**을 분석하여, 원본보다 2배 더 풍성하고 전문적인 정보를 제공하라.
1. **차별화(Evolution)**: 원본 글이 놓친 디테일이나 2026년 최신 트렌드를 네 지능으로 보완하여 '상위 호환' 문서를 작성하라.
2. **복사 느낌 제거**: 원본에 나오는 특정 날짜, 개인적 에피소드, 특정 인물 이름 등은 100% 가공하거나 일반화하여 '기현님만의 새로운 경험담'으로 재구성하라.
3. **밀도 강제**: 수박 겉핥기식 서술 절대 금지. 구체적인 비용, 준비물 리스트, 단계별 방법론을 꽉꽉 채워 5,000자 수준의 압도적 분량을 확보하라.
4. **서론 앵무새 금지**: "결론부터 말하면" 같은 반복 멘트 엄금. "솔직히 이거 모르면 손해죠.", "요즘 가장 핫한 방법부터 풉니다." 등 매번 다른 사람 냄새 나는 시작을 하라.

[🚨 하네스 외부 링크 강제 규칙]: 
- 모든 외부 링크는 반드시 아래 형태의 **'구글 검색 결과 URL'**로만 작성하라. (특정 브랜드 공식 홈 URL 직접 작성 금지)
- 형식: <a href='https://www.google.com/search?q=검색키워드' target='_blank' class='ext-link'>내용 (👉클릭)</a>

[🔥 핵심 강제 규칙]:
- 서식: <nav> 목차, <h2> id 부여 필수. <table> 최소 1개 필수.
- 내부링크: 메뉴판 번호표 `[내부링크_ID번호]` 문맥에 맞춰 2~3개 삽입.
- 중간 CTA: 수익형 링크 1개 이상 삽입 (구글 검색 URL 활용).
- 보안: 본문 내 모든 HTML 속성은 반드시 작은따옴표(')만 사용하라.

[🌟 리얼 휴먼 톤 지침]:
- 문장 길이를 섞고, 말투를 살짝씩 비틀어라. (존댓말 위주지만 한두 문장은 "이건 좀 아니지 않나요?" 같은 감정 섞인 반말 느낌 허용)
- 모든 주장은 "이유+결과" 공식으로 신뢰도를 높여라.

결과물은 부연 설명 없는 순수 HTML 본문 코드만 반환하라.
"""
    
    print(f"✍️ [4/6] 1단계: 메인 작가 AI가 5,000자 초고밀도 진화형 본문을 집필 중입니다...")
    draft_html = None
    for attempt, model_name in enumerate(models_to_try, 1):
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        try:
            res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt_writer}]}]}, timeout=240)
            res.raise_for_status()
            draft_html = res.json()['candidates'][0]['content']['parts'][0]['text'].replace("```html", "").replace("```", "").strip()
            break
        except Exception as e:
            if "503" in str(e) or "429" in str(e) or "unavailable" in str(e).lower():
                time.sleep(20 * attempt)
            else:
                time.sleep(5)
            
    if not draft_html:
        print("❌ 1단계 본문 생성 실패")
        return None

    # -------------------------------------------------------------------
    # 🕵️‍♂️ [2단계 API] 편집장 AI (SEO DNA 퓨전 제목 & 초정밀 지능형 지도)
    # -------------------------------------------------------------------
    prompt_editor = f"""
당신은 완벽한 SEO 편집장입니다. 아래 작성된 [초안 블로그 본문]을 읽고 메타데이터를 생성하라.

[초안 블로그 본문]:
{draft_html[:3000]} ... (중략)

**[🔥 최종 제목(title) 생성 - 1등 SEO DNA 퓨전 로직]**:
- 네이버 1등 뼈대 제목: **[{skeleton_title}]**
- 파이썬 자동 생성 뼈대: {title_guide}
- 필수 키워드: {keyword}

🚨 [하네스 강제 조합 룰]:
1. **DNA 추출**: 위 1등 제목에서 사람들을 홀린 '자극적 단어/숫자/상황'을 뽑아라.
2. **완벽 퓨전**: 추출한 DNA를 {title_guide}에 이식하여 원본보다 더 강력한 제목을 만들어라. 
3. **생존**: {keyword}는 반드시 원형 그대로 포함하라. (서론 복붙 절대 금지)

**[🎯 초정밀 능동형 지도(map_location) 선정 하네스 규칙]**:
본문의 목적을 추론하여 독자가 가장 가고 싶어 할 장소를 핀셋 지정하라.
1. **해외 현지**: "간사이 국제공항", "다낭 한시장" 등 핵심 랜드마크.
2. **국내 출국**: "인천공항 마티나 라운지", "신라면세점 서울점", "서울역 도심공항터미널" 등.
3. **온라인/무형(환전/보험 등)**: "명동 환전소", "인천공항 로밍센터", "외교부 여권민원실" 등 상징적 장소.

[출력 형식 가이드]: 반드시 순수 JSON 형식 문자열로만 반환하라.
JSON Keys: title, meta_desc, meta_keys, slug, summary (이모지 1개+6글자 3세트), map_location, category
"""
    
    print(f"✨ [5/6] 2단계: 편집장 AI가 1등 SEO 제목과 능동형 지도를 분석 중입니다...")
    final_data = None
    for attempt, model_name in enumerate(models_to_try, 1):
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        try:
            res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt_editor}]}], "generationConfig": {"responseMimeType": "application/json"}}, timeout=180)
            res.raise_for_status()
            final_data = json.loads(res.json()['candidates'][0]['content']['parts'][0]['text'].replace("```json", "").replace("```", "").strip())
            break
        except Exception as e:
            time.sleep(5)
            
    if not final_data:
        print("❌ 2단계 메타데이터 생성 실패")
        return None

    # -------------------------------------------------------------------
    # 🐍 [3단계] 파이썬 조립: 본문 + 내부링크 HTML 치환
    # -------------------------------------------------------------------
    for i, p in enumerate(menu_posts):
        link_html = f" <a href='{p['url']}' target='_blank' class='int-link'>🔗 {p['title']} (새창)</a> "
        draft_html = draft_html.replace(f"[내부링크_{i}]", link_html)
        
    final_data['content'] = draft_html 
    final_data['used_references'] = [target_blog_url]
    
    return final_data

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
    keyword, target_url, scraped_data, title_guide, related_keyword, skeleton_title = get_naver_target_data(recent_posts) # <-- recent_posts 추가!
    
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

    # 🔥 '여행 꿀팁'을 삭제하고, 6개 옵션 중 딱 1개만 선택하도록 수정
    chosen_category = data.get('category', '').strip()
    if chosen_category not in LABEL_OPTIONS: 
        chosen_category = "여행 준비 팁" # 리스트에 없는 카테고리가 올 경우 기본값 적용
        
    final_labels = [chosen_category] # 오직 선택된 1개의 라벨만 사용
    
    sleep_time = random.randint(180, 600)
    print(f"⏳ [System] 봇으로 걸리지 않기 위해 {sleep_time}초 대기 후 발행합니다...")
    time.sleep(sleep_time)
    
    # 🔥 이 한 줄만 추가하세요! (8분 쉬어서 끊어진 연결을 다시 붙이는 겁니다)
    service = build('blogger', 'v3', credentials=creds)
    
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
