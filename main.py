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

PRIORITY_KEYWORDS = ["스마트패스", "입국신고서", "라운지", "수하물", "여행자보험", "렌터카", "디파짓", "텍스리펀", "DCC", "지연 보상"]
LOW_PERFORMANCE_KEYWORDS = ["일본 환전 꿀팁", "여행자 보험 꼭 필요한가", "가성비 숙소 고르는 법"]

# 계절별 자동 발행 키워드 (검색 수요 1개월 선행 기준)
SEASONAL_KEYWORDS = {
    "winter": [  # 11, 12, 1월
        "삿포로 겨울여행", "오타루 당일치기", "유후인 료칸 예약", "벳푸 온천 여행",
        "노보리베츠 온천", "치앙마이 건기 여행", "푸꾸옥 건기 여행", "코타키나발루 건기",
        "시드니 여름 여행", "유럽 크리스마스마켓", "연말 항공권 예약", "겨울 온천 준비물"
    ],
    "spring": [  # 2, 3, 4월
        "교토 벚꽃 명소", "도쿄 벚꽃 개화시기", "후쿠오카 벚꽃 여행", "오사카성 벚꽃",
        "타이베이 봄 옷차림", "다낭 3월 날씨", "나트랑 봄 여행", "파리 봄 옷차림",
        "스페인 4월 날씨", "진해 군항제 동선", "경주 벚꽃 드라이브", "제주 유채꽃 코스"
    ],
    "summer": [  # 5, 6, 7월
        "홋카이도 여름여행", "후라노 비에이 투어", "오키나와 스노클링", "발리 건기 여행",
        "발리 우붓 리조트", "시드니 겨울 여행", "스위스 여름 트레킹", "돌로미티 여름 코스",
        "캐나다 록키 여행", "괌 투몬비치 호텔", "사이판 마나가하섬", "여름 휴가 항공권"
    ],
    "autumn": [  # 8, 9, 10월
        "교토 단풍 시기", "닛코 단풍 코스", "아라시야마 단풍", "캐나다 메이플로드",
        "타이베이 가을 여행", "추석연휴 해외여행", "방콕 10월 날씨", "홍콩 가을 날씨",
        "이탈리아 가을 여행", "설악산 단풍 코스", "내장산 단풍 시기", "제주 억새 명소"
    ]
}

CONTENT_FLOW = {
    "공항": ["스마트패스 등록", "인천공항 장기주차장", "공항 라운지 무료", "위탁수하물 무게 초과", "셀프백드랍 이용법"],
    "입국": ["비지트재팬웹 등록", "대만 입국신고서", "태국 입국신고서", "미국 ESTA 신청", "세관신고서 작성 기준"],
    "결제": ["원화결제 DCC 차단", "해외 ATM 출금", "GLN QR결제", "신용카드 해외승인 취소", "유럽 텍스리펀 절차"],
    "보험": ["해외여행자보험 휴대폰", "여행자보험 치료비 청구", "항공기 지연 보상", "수하물 파손 배상"],
    "일본": ["비지트재팬웹 등록", "나리타 익스프레스", "간사이공항 라피트", "스이카 아이폰 발급", "신칸센 지정석 예매"],
    "베트남": ["나트랑 리조트 픽업", "푸꾸옥 빈원더스 동선", "다낭 바나힐 케이블카", "그랩 택시 이용법"],
    "태국": ["태국 입국신고서", "방콕 수완나품 공항철도", "방콕 BTS 래빗카드", "볼트 택시 사용법", "치앙마이 올드타운 숙소"],
    "대만": ["대만 입국신고서", "타이베이 이지카드", "타오위안 공항철도", "타이중 근교 투어", "가오슝 자유여행 동선"],
    "유럽": ["유럽 텍스리펀 절차", "유레일패스 좌석예약", "스위스 트래블패스", "영국 ETA 비자", "렌터카 자차보험 비교"],
    "숙소": ["호텔 디파짓 환불", "얼리체크인 요청", "리조트피 현지결제", "무료취소 결제 시점", "커넥팅룸 예약 방법"],
    "항공": ["기내반입 액체류", "보조배터리 기내반입", "저비용항공 좌석 지정", "경유 수하물 연결", "항공권 이름 수정"]
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

def get_current_season_keywords(month):
    if month in [11, 12, 1]:
        return SEASONAL_KEYWORDS["winter"]
    elif month in [2, 3, 4]:
        return SEASONAL_KEYWORDS["spring"]
    elif month in [5, 6, 7]:
        return SEASONAL_KEYWORDS["summer"]
    else:
        return SEASONAL_KEYWORDS["autumn"]

def requeue_if_needed(keyword):
    all_seasonal = {k for v in SEASONAL_KEYWORDS.values() for k in v}
    if keyword in all_seasonal:
        return
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            existing = {line.strip() for line in f.read().splitlines() if line.strip()}
        if keyword in existing:
            return
    with open(QUEUE_FILE, "a", encoding="utf-8") as f:
        f.write("\n" + keyword)

def prioritize_keywords(keywords):
    p = [k for k in keywords if any(x in k for x in PRIORITY_KEYWORDS)]
    n = [k for k in keywords if k not in p]
    return p + n

def generate_title_variants(keyword):
    return f"{keyword} 핵심 정보"

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
def get_naver_target_data(recent_posts):
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
    
    # 사계절 상시 키워드 (계절 전용 키워드는 SEASONAL_KEYWORDS에서 자동 매칭)
    BASE_KEYWORDS = [
        "스마트패스 등록", "인천공항 장기주차장", "인천공항 주차대행", "공항 라운지 무료", "마티나라운지 이용",
        "스카이허브라운지 할인", "기내반입 액체류", "보조배터리 기내반입", "위탁수하물 무게 초과", "셀프백드랍 이용법",
        "모바일 체크인 방법", "경유 수하물 연결", "저비용항공 좌석 지정", "비상구 좌석 조건", "항공권 이름 수정",
        "항공기 지연 보상", "수하물 파손 배상", "여권 유효기간 6개월", "긴급여권 발급 방법", "국제운전면허증 발급",
        "영문운전면허증 사용국가", "공항철도 직통열차", "서울역 도심공항터미널", "공항리무진 버스 예매", "패스트트랙 이용 조건",
        "비지트재팬웹 등록", "대만 입국신고서", "태국 입국신고서", "싱가포르 SG입국카드", "필리핀 이트래블",
        "말레이시아 MDAC", "인도네시아 전자비자", "미국 ESTA 신청", "캐나다 eTA 발급", "호주 ETA 신청",
        "영국 ETA 비자", "세관신고서 작성 기준", "유럽 텍스리펀 절차", "일본 소비세 면세", "공항 택스리펀 환급",
        "원화결제 DCC 차단", "해외결제 수수료 절감", "해외 ATM 출금", "GLN QR결제", "알리페이 해외결제",
        "위챗페이 카드등록", "애플페이 해외사용", "컨택리스 카드 결제", "신용카드 해외승인 취소", "해외결제 한도 증액",
        "해외여행자보험 휴대폰", "여행자보험 치료비 청구", "여행자보험 수하물 지연", "가족 여행자보험 비교", "카드 분실 해외대처",
        "해외 팁 문화 기준", "환율 우대 쿠폰", "출장 경비 영수증",
        "나리타 익스프레스", "스카이라이너 예매", "간사이공항 라피트", "하루카 특급열차", "스이카 아이폰 발급",
        "이코카 카드 충전", "신칸센 지정석 예매", "오사카 주유패스", "교토 버스 패스", "산큐패스 노선",
        "타이베이 이지카드", "타오위안 공항철도", "홍콩 옥토퍼스카드", "홍콩 AEL 공항철도", "방콕 수완나품 공항철도",
        "방콕 BTS 래빗카드", "그랩 택시 이용법", "볼트 택시 사용법", "우버 해외결제", "유레일패스 좌석예약",
        "스위스 트래블패스", "렌터카 자차보험 비교", "오키나와 렌터카 예약", "괌 렌터카 보험",
        "호텔 디파짓 환불", "얼리체크인 요청", "레이트체크아웃 비용", "리조트피 현지결제", "숙박세 현장결제",
        "무료취소 결제 시점", "노쇼 위약금 규정", "조식 추가 현장결제", "연박 객실 청소", "커넥팅룸 예약 방법",
        "엑스트라베드 추가요금", "호캉스 라운지 혜택", "일일투어 취소 규정", "패스트패스 입장권", "포켓와이파이 대여",
        "데이터 로밍 차단", "해외 전화 수신요금", "멀티어댑터 전압 확인",
        "하코네 프리패스", "가마쿠라 당일치기", "다카마쓰 소도시 여행", "마쓰야마 무료셔틀", "요나고 돗토리 이동",
        "미야코지마 자유여행", "타이중 근교 투어", "가오슝 자유여행 동선", "나트랑 리조트 픽업", "푸꾸옥 빈원더스 동선",
        "다낭 바나힐 케이블카", "치앙마이 올드타운 숙소", "방콕 파타야 이동", "싱가포르 유니버설스튜디오",
        "마카오 페리 터미널", "상하이 무비자 입국",
        f"{main_country} 입국신고서", f"{sub_country} 공항 이동"
    ]

    if not os.path.exists(QUEUE_FILE) or os.stat(QUEUE_FILE).st_size == 0:
        sorted_keys = prioritize_keywords(BASE_KEYWORDS)
        with open(QUEUE_FILE, "w", encoding="utf-8") as f: f.write("\n".join(sorted_keys))

    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.read().splitlines() if line.strip()]
    if not lines: 
        lines = prioritize_keywords(BASE_KEYWORDS)

    # 현재 월 기준 계절 키워드 자동 선별 (35% 확률로 미발행 계절 키워드 우선 발행)
    target_query = None
    is_seasonal = False
    season_candidates = [
        q for q in get_current_season_keywords(now.month)
        if not any(q.split()[0] in title for title in recent_titles)
    ]

    if season_candidates and random.random() < 0.35:
        target_query = random.choice(season_candidates)
        is_seasonal = True

    # 계절 키워드가 선택되지 않은 경우 사계절 큐에서 미발행 키워드 추출
    if not target_query:
        for query in lines:
            core_word = query.split()[0]
            if not any(core_word in title for title in recent_titles):
                target_query = query
                break

    if not target_query: 
        target_query = random.choice(lines)
    
    title_guide = generate_title_variants(target_query)
    related_keyword = get_content_chain(target_query)
    
    # 사계절 큐 키워드만 순환 저장 (계절 키워드는 큐 파일에 섞지 않음)
    if not is_seasonal and target_query in lines:
        lines.remove(target_query)
        lines.append(target_query)
        with open(QUEUE_FILE, "w", encoding="utf-8") as f: f.write("\n".join(lines))

    search_suffix = [
        " 장단점", " 꿀팁", " 사용법", " 완벽 가이드", " 총정리", " 비교 추천",
        " 설정 오류", " 안터짐", " 환불", " 주의사항", " 실패 후기", " 치명적 단점",
        " 실제 후기", " 내돈내산", " 팩트체크", " 솔직 리뷰", " 한달 사용기",
        " 가격 비교", " 할인 팁", " 비용 절약", " 무료 혜택", " 최저가 예약"
    ]
    actual_search_query = f"{target_query}{random.choice(search_suffix)}"
    
    mode_tag = "계절 자동" if is_seasonal else "사계절 큐"
    print(f"🎯 [2/6] [{mode_tag}] 키워드: {target_query} (검색어: {actual_search_query})")
    
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
                mobile_url = item['url'].replace
