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
    print("[1/6] 최고 모델 라인업 탐색 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    default_models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]

    try:
        res = requests.get(url, timeout=10).json()
        available = [
            m['name'].replace('models/', '')
            for m in res.get('models', [])
            if 'generateContent' in m.get('supportedGenerationMethods', [])
        ]

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
            print(f"선택된 텍스트 전용 모델 리스트: {best_models[:5]}")
            return best_models

        return default_models

    except Exception as e:
        print(f"모델 리스트 호출 실패: {e} -> 기본 리스트 사용")
        return default_models


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
        print(f"내부링크 수집 실패: {e}")
        return []


def get_content_chain(keyword):
    for key, flows in CONTENT_FLOW.items():
        if key in keyword:
            return flows[0]
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
        <a href="{map_link}" target="_blank" style="display:inline-block; margin-top:15px; padding:12px 25px; background-color:#3498db; color:#fff; font-weight:bold; font-size:16px; border-radius:8px; text-decoration:none; box-shadow: 0 2px 5px rgba(0,0,0,0.2);">{location} 지도를 클릭해서 위치를 참고하세요 (새창 열기)</a>
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
        "삿포로 겨울여행 준비", "오타루 당일치기 동선", "유후인 료칸 예약", "벳푸 온천 여행", "하코네 프리패스",
        "가마쿠라 당일치기", "다카마쓰 소도시 여행", "마쓰야마 무료셔틀", "요나고 돗토리 이동", "미야코지마 자유여행",
        "타이중 근교 투어", "가오슝 자유여행 동선", "나트랑 리조트 픽업", "푸꾸옥 빈원더스 동선", "다낭 바나힐 케이블카",
        "치앙마이 올드타운 숙소", "방콕 파타야 이동", "싱가포르 유니버설스튜디오", "마카오 페리 터미널", "상하이 무비자 입국",
        f"{main_country} 입국신고서", f"{sub_country} 공항 이동"
    ]

    if not os.path.exists(QUEUE_FILE) or os.stat(QUEUE_FILE).st_size == 0:
        sorted_keys = prioritize_keywords(BASE_KEYWORDS) + PRIORITY_KEYWORDS
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted_keys))

    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.read().splitlines() if line.strip()]
    if not lines:
        lines = prioritize_keywords(BASE_KEYWORDS) + PRIORITY_KEYWORDS

    target_query = None
    for query in lines:
        core_word = query.split()[0]
        if not any(core_word in title for title in recent_titles):
            target_query = query
            break

    if not target_query:
        target_query = random.choice(lines)

    title_guide = generate_title_variants(target_query)
    related_keyword = get_content_chain(target_query)

    if target_query in lines:
        lines.remove(target_query)
        lines.append(target_query)
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    search_suffix = [
        " 장단점", " 꿀팁", " 사용법", " 완벽 가이드", " 총정리", " 비교 추천",
        " 설정 오류", " 안터짐", " 환불", " 주의사항", " 실패 후기", " 치명적 단점",
        " 실제 후기", " 내돈내산", " 팩트체크", " 솔직 리뷰", " 한달 사용기",
        " 가격 비교", " 할인 팁", " 비용 절약", " 무료 혜택", " 최저가 예약"
    ]
    actual_search_query = f"{target_query}{random.choice(search_suffix)}"

    print(f"[2/6] 키워드: {target_query} (검색어: {actual_search_query})")

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
            if len(valid_links) >= 15:
                break

        if len(valid_links) >= 5:
            main_idx = random.randint(0, min(2, len(valid_links) - 1))
            main_link = valid_links.pop(main_idx)
            sub_links = random.sample(valid_links, min(9, len(valid_links)))
            selected_links = [main_link] + sub_links
        else:
            selected_links = valid_links

        if selected_links:
            target_blog_url = selected_links[0]['url']
            skeleton_title = selected_links[0]['title']
            print(f"[3/6] 총 {len(selected_links)}개 블로그 추출 중... (뼈대: {skeleton_title})")

            for i, item in enumerate(selected_links):
                mobile_url = item['url'].replace("blog.naver.com", "m.blog.naver.com")
                driver.get(mobile_url)
                time.sleep(1.5)
                try:
                    text = driver.find_element(By.CSS_SELECTOR, ".se-main-container").text
                except Exception:
                    try:
                        text = driver.find_element(By.TAG_NAME, "body").text
                    except Exception:
                        text = "수집 실패"

                if i == 0:
                    role = "Main Skeleton"
                    scraped_data += f"--- [{role}: {item['title']}] ---\n{text[:2000]}\n\n"
                else:
                    role = "Real Review Insight"
                    scraped_data += f"--- [{role}: {item['title']}] ---\n{text[:500]}\n\n"
    finally:
        driver.quit()

    return target_query, target_blog_url, scraped_data, title_guide, related_keyword, skeleton_title


# ==================== [4] 유동적 SVG 요약 카드 ====================
def create_summary_card_tag(summary_list, alt_text):
    if not isinstance(summary_list, list):
        summary_list = ["핵심 요약", "비용 절약", "실전 가이드"]

    safe_list = [str(s).strip()[:10] for s in summary_list if s][:3]
    while len(safe_list) < 3:
        safe_list.append("")

    svg_code = f"""
    <svg width="100%" height="200" viewBox="0 0 600 200" xmlns="http://www.w3.org/2000/svg">
      <rect width="600" height="200" fill="#FFF9C4" rx="15"/>
      <text x="50%" y="60" font-family="'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="32" text-anchor="middle" fill="#2c3e50">{safe_list[0]}</text>
      <text x="50%" y="110" font-family="'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="32" text-anchor="middle" fill="#2c3e50">{safe_list[1]}</text>
      <text x="50%" y="160" font-family="'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="32" text-anchor="middle" fill="#2c3e50">{safe_list[2]}</text>
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

    menu_posts = context_posts[:10]
    recent_titles_str = "\n".join([f"- [내부링크_{i}] 제목: {p['title']} (URL: {p['url']})" for i, p in enumerate(menu_posts)])

    now_year = datetime.now().year
    now_month = datetime.now().month

    prompt_writer = f"""
[타겟 키워드]: {keyword}
[페르소나]: {current_persona}
[내 블로그 다른 글 리스트]:
{recent_titles_str}

[이번 글의 핵심 메인 테마 및 제목 작성 가이드]:
제공된 뼈대 블로그의 제목인 **[{skeleton_title}]**이 다루는 특정 상황, 심층 꿀팁을 이번 포스팅의 핵심 앵글로 삼아라.
절대 백과사전처럼 포괄적인 장단점이나 뻔한 소개를 줄줄이 나열하지 마라.
특정 타겟(예: 가족 여행객, 뚜벅이)이나 특정 상황(예: 수수료 폭탄 방지, 환불 꿀팁, 사기 피하기) 중 딱 하나의 뾰족한 주제(Niche)에만 딥다이브(Deep-dive)해서 써라.

[앵무새 방지 및 자연스러운 톤 지침]:
- "결론부터 말하면", "핵심은 단 하나" 같은 고정된 문구를 매번 첫 문장에 쓰지 마세요.
- 독자의 고민에 공감하며 자연스럽게 말을 거는 서론으로 시작하세요.
- 기계적인 인사는 빼고, 독자에게 즉시 이득이 되는 정보로 시원하게 본론을 여세요.

[10개 블로그 분석 데이터]:
{scraped_data}

[미션]: 독자가 즉시 '결정'을 하도록 유도하는, 4,000자~6,000자 분량의 초고밀도 전환형 포스팅을 작성하라.
위 10개 블로그 데이터를 베이스로 삼되, 원본에 노출된 '특정 날짜, 타인의 실명, 개인적인 에피소드'는 100% 가공하여 네 페르소나에 맞는 '새로운 나의 경험담'으로 완전히 탈바꿈시켜라. 경쟁 글의 장점은 흡수하되, 남의 글을 복사한 티가 절대 나면 안 된다. 더 디테일하고 발전된 형태의 정보를 제공하라. 또한 현재 시점({now_year}년 {now_month}월)과 계절에 맞는 정보와 날짜를 기준으로 작성하고, 2024년·2025년 등 과거 연도나 현재 계절과 맞지 않는 과거 월은 절대 표기하지 마라.

[핵심 강제 지시사항 - 순수 HTML만 반환 (JSON 포장 절대 금지)]:
1. HTML 포맷 및 목차(TOC) 강제:
  - 마크다운(`##`, `**`) 절대 금지. 오직 순수 HTML 태그만 사용.
  - 본문 서론 다음에는 반드시 `<nav><div class='toc-title'>목차</div><ul>...</ul></nav>` 형태의 목차를 작성하라.
  - 목차의 링크는 `<a href='#sec1'>` 형태로 앵커를 달고, 본문의 소제목 <h2> 태그에는 반드시 `<h2 id='sec1'>` 처럼 id를 일치시켜 클릭 시 정확히 이동하게 하라.
2. 문맥형 최신 내부링크 (무조건 3개 자연 삽입 강제):
  - 'Related:' 같은 단독 문단 절대 금지. 문장 안에 [내 블로그 다른 글 리스트] 중 3개를 골라 자연스럽게 버튼 스타일로 녹여라.
  - 직접 <a>태그를 만들지 말고 반드시 `자세한 내용은 [내부링크_0]를 참고하세요.` 와 같이 기호로만 적어라.
3. 중간 CTA (수익 전환 포인트): 본문 중간에 클릭을 유도하는 링크를 1개 이상 배치하라.
4. 안전한 구글 외부 링크 (무조건 문맥에 맞는 링크 3개 강제):
  - 가짜 오류 URL 방지를 위해, 모든 외부 링크는 반드시 구글 검색 결과 URL 또는 구글 맵 검색 URL로만 정확히 3개 작성하라.
  - 예시: `<a href='https://www.google.com/search?q=관련+검색어' target='_blank' class='ext-link'>관련 최신정보 구글 검색하기 <span style='font-size:12px;'>(클릭하면 이동)</span></a>`
5. 결정 섹션: 본문 맨 마지막에 `<h2 id='conclusion'>상황별 최종 선택 가이드</h2>` 형태로 주제에 맞는 결론 소제목을 사용해라.
6. 표(Table)와 리스트(List) 절대 엄수:
  - 제품 비교나 장단점 설명 시 반드시 `<div class='table-wrapper'><table>...</table></div>` 형태의 HTML 표로 작성하라.
  - 텍스트 나열은 `<p>` 대신 `<ul><li>...</li></ul>`를 적극 활용해라.
7. 본문 안의 모든 HTML 속성은 반드시 작은따옴표(')만 써라.
8. 글 맨 끝에 부연 설명("네 알겠습니다", "작성 완료" 등)을 단 한 글자도 적지 마라. 오직 HTML 소스코드만 출력하라.

[품질 필터 및 휴먼 톤 작성 지침]:
- 기계식 서론 금지: 검색 과정 등 군더더기 금지. 곧바로 핵심 혜택 시작.
- 리얼리티 경험담: 자연스러운 구어체(~했어요, 솔직히 말해서 등) 사용.
- 이유+결과 공식: 모든 문장은 "이유+결과"를 적어라.
- 문장 길이 섞기, 반복 패턴 깨기, 개인정보 및 모방 사이트 이름 금지.
"""

    print("[4/6] 1단계: 메인 작가 AI가 본문을 창작 중입니다...")
    draft_html = None
    for attempt, model_name in enumerate(models_to_try, 1):
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        try:
            res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt_writer}]}]}, timeout=180)
            res.raise_for_status()
            draft_html = res.json()['candidates'][0]['content']['parts'][0]['text'].replace("```html", "").replace("```", "").strip()
            break
        except Exception as e:
            if "503" in str(e) or "429" in str(e) or "unavailable" in str(e).lower():
                time.sleep(15 * attempt)
            else:
                time.sleep(5)

    if not draft_html:
        return None

    prompt_editor = f"""
당신은 완벽한 SEO 편집장입니다. 아래 작성된 [초안 블로그 본문]을 읽고, 메타데이터 JSON을 생성하라.

[초안 블로그 본문]:
{draft_html[:3000]} ... (중략)

[최종 제목(title) 생성 규칙]:
- 현재 시점은 {now_year}년 {now_month}월이다. 제목과 본문에 2024년, 2025년 등 과거 연도나 현재 계절과 맞지 않는 과거 월(예: 11월에 4월/5월)을 절대 표기하지 마라.
- "2026년 최신판!", "확인해 보세요" 같은 인위적 수식어와 "J형 여행가", "프로 봇짐러" 같은 반복 페르소나 문구를 제목에 넣지 마라.
- '{keyword}'를 포함하여 핵심 해결책이 드러나는 자연스럽고 담백한 정보형 제목을 작성하라.

[초정밀 능동형 지도(map_location) 하네스 규칙]:
본문을 읽고 독자가 가장 길을 찾고 싶어 할 실물 장소를 능동적으로 추론하여 단답형으로 지정하라.
1. 해외 현지 (맛집/관광): "간사이 국제공항", "다낭 한시장", "신주쿠역" 등 해당 지역의 핵심 랜드마크.
2. 국내 출국 (편의시설): "인천공항 마티나 라운지", "신라면세점 서울점", "서울역 도심공항터미널" 등 구체적인 시설명.
3. 온라인/무형 (환전/보험/통신/비자): "명동 환전소", "인천공항 제1여객터미널", "인천공항 로밍센터", "외교부 여권민원실" 등 대표 오프라인 장소.
- 스쳐 지나가는 화장실, 수영장, 단순 도로명 등은 절대 금지.

[출력 형식 가이드]: 순수 JSON 문자열만 반환하라.
JSON Keys:
- title: 검색 의도에 맞춘 자연스러운 정보형 제목 (과거 연도 및 과도한 어그로 금지)
- meta_desc: 150자 요약
- meta_keys: '{keyword}'가 포함된 쉼표 구분 키워드
- slug: 영문 짧은 주소
- summary: ["핵심요약", "비용절약", "필수체크"] (6글자 이하 3개)
- map_location: 능동적 추론 장소명 1개
- category: ["여행 교통 팁", "여행 쇼핑 팁", "여행 관광 팁", "여행 준비 팁", "여행 맛집 팁", "생활 정보 꿀팁"] 중 1개
"""

    print("[5/6] 2단계: 편집장 AI가 제목과 메타데이터(JSON)를 생성 중입니다...")
    final_data = None
    for attempt, model_name in enumerate(models_to_try, 1):
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        try:
            res = requests.post(
                api_url,
                json={
                    "contents": [{"parts": [{"text": prompt_editor}]}],
                    "generationConfig": {"responseMimeType": "application/json"}
                },
                timeout=180
            )
            res.raise_for_status()
            final_data = json.loads(
                res.json()['candidates'][0]['content']['parts'][0]['text']
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )
            break
        except Exception:
            time.sleep(5)

    if not final_data:
        return None

    for i, p in enumerate(menu_posts):
        link_html = f" <a href='{p['url']}' target='_blank' class='int-link'>{p['title']} (새창)</a> "
        draft_html = draft_html.replace(f"[내부링크_{i}]", link_html)

    final_data['content'] = draft_html
    final_data['used_references'] = [target_blog_url]

    return final_data


# ==================== [6] 메인 실행 ====================
def run_automation():
    print("블로그 자동 성장 시스템 가동...")

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
        print("인증 정보가 없습니다.")
        return

    service = build('blogger', 'v3', credentials=creds)
    print("[1/6] Blogger 인증 완료")

    recent_posts = get_recent_posts(service, BLOG_ID)
    keyword, target_url, scraped_data, title_guide, related_keyword, skeleton_title = get_naver_target_data(recent_posts)

    filtered_posts = get_related_posts_by_keyword(recent_posts, keyword)
    context_posts = filtered_posts if len(filtered_posts) >= 2 else recent_posts

    data = generate_master_content(keyword, target_url, scraped_data, title_guide, context_posts, related_keyword, skeleton_title)

    if not data:
        print("생성 실패. 키워드를 큐에 재등록합니다.")
        with open(QUEUE_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + keyword)
        return

    location = data.get('map_location', '인천공항 제1여객터미널').strip()
    map_html = create_map_embed(location)
    print(f"[System] AI가 분석한 '{location}' 기반 구글맵 코드를 생성했습니다.")

    ads_code = """
    <div style="margin:45px 0;">
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

    final_labels = [chosen_category]

    sleep_time = random.randint(180, 600)
    print(f"[System] {sleep_time}초 대기 후 발행합니다...")
    time.sleep(sleep_time)

    service = build('blogger', 'v3', credentials=creds)

    try:
        slug_text = data.get('slug', 'auto-post')
        print(f"[6/6] 최종 업로드 중... ({slug_text})")
        temp_post = service.posts().insert(
            blogId=BLOG_ID,
            body={"title": slug_text, "content": "loading...", "labels": final_labels},
            isDraft=False
        ).execute()
        service.posts().patch(
            blogId=BLOG_ID,
            postId=temp_post['id'],
            body={"title": data['title'], "content": final_html, "customMetaData": data.get('meta_desc', '')}
        ).execute()
        print(f"[완료] {data['title']}")
    except Exception as e:
        print(f"실패: {e}")
        with open(QUEUE_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + keyword)


if __name__ == "__main__":
    run_automation()
