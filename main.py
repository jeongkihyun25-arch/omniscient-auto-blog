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

# 🔥 돈 되는 키워드 (수익 우선 처리용)
PRIORITY_KEYWORDS = ["eSIM", "로밍", "환전", "수하물", "스마트패스", "유심"]

# ==================== [2] 최고 모델 및 유틸리티 함수 ====================
def get_best_model():
    print("🔍 [1/6] 최고 모델 탐색 중...")
    url = f"[https://generativelanguage.googleapis.com/v1beta/models?key=](https://generativelanguage.googleapis.com/v1beta/models?key=){GEMINI_API_KEY}"
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

def prioritize_keywords(keywords):
    # 우선순위 키워드가 포함된 것을 앞으로, 나머지를 뒤로 정렬
    p = [k for k in keywords if any(x in k for x in PRIORITY_KEYWORDS)]
    n = [k for k in keywords if k not in p]
    return p + n

def generate_title_variants(keyword):
    # 🔥 제목 CTR 자동 최적화 테스트 로직
    variants = [
        f"{keyword} 이거 안 하면 비용 2배 (실제 후기)",
        f"{keyword} 완벽 가이드 총정리",
        f"여행 고수들이 몰래 쓰는 {keyword} 핵심 1가지"
    ]
    return random.choice(variants)

def get_recent_posts(service, blog_id):
    # 🔥 내부링크 자동 삽입을 위한 최근 글 5개 불러오기
    try:
        posts = service.posts().list(blogId=blog_id, maxResults=5, fetchBodies=False).execute()
        return [{"title": p["title"], "url": p["url"]} for p in posts.get("items", [])]
    except Exception as e:
        print(f"⚠️ 내부링크 수집 실패: {e}")
        return []

# ==================== [3] 네이버 수집 (🔥 순환형 큐 + 클러스터) ====================
def get_naver_target_data():
    now = datetime.now()
    m = [now.month, (now.month % 12) + 1, ((now.month + 1) % 12) + 1]
    
    # 🔥 클러스터 그룹 (매달 다른 지역 집중 공략)
    COUNTRY_GROUPS = [
        ["일본", "대만", "홍콩", "중국"],           # 1, 5, 9월
        ["베트남", "태국", "필리핀", "인도네시아"],  # 2, 6, 10월
        ["미국", "캐나다", "하와이"],               # 3, 7, 11월
        ["프랑스", "이탈리아", "스페인", "영국"]    # 4, 8, 12월
    ]
    
    group_index = now.month % len(COUNTRY_GROUPS)
    current_group = COUNTRY_GROUPS[group_index]
    
    main_country = current_group[0] 
    sub_country = random.choice(current_group[1:]) if len(current_group) > 1 else main_country
    
    # 기본 키워드 덱 (최초 1회 생성용)
    BASE_KEYWORDS = [
        "인천공항 주차 요금", "인천공항 혼잡 시간", "출국 수속 시간", "스마트패스 사용법", 
        "공항 라운지 무료 이용", "공항 리무진 시간표", "기내 반입 규정", "수하물 추가 요금",
        "공항 대기 시간", "출국 몇시간 전",
        "해외 로밍 요금", "eSIM 추천", "eSIM 안될 때", "유심 vs eSIM 비교", 
        "데이터 안터질 때", "무료 와이파이 위험", "환전 수수료 줄이기", 
        "eSIM 오류 해결", "데이터 느림 이유", "환전 타이밍", "여행 비용 줄이는 법",
        f"{main_country} 입국신고서", f"{main_country} 교통패스", f"{main_country} 쇼핑리스트", 
        f"{main_country} 환전 꿀팁", f"{main_country} 유심 eSIM 추천", f"{main_country} 맛집 실패 안하는 법",
        f"{sub_country} 여행 준비물", f"{sub_country} 가볼만한곳",
        "해외여행 준비물 체크리스트", "여행자 보험 꼭 필요한가", "비상약 리스트", 
        "입국 심사 질문", "세관 신고 기준", "가족 여행 준비 팁",
        "가성비 숙소 고르는 법", "에어비앤비 위험", "호텔 체크인 꿀팁", 
        "현지 맛집 찾는 방법", "면세점 쇼핑 팁", f"{m[0]}월 해외여행지 추천"
    ]

    # 1. 큐 파일이 없으면 우선순위 정렬 후 생성
    if not os.path.exists(QUEUE_FILE) or os.stat(QUEUE_FILE).st_size == 0:
        BASE_KEYWORDS = prioritize_keywords(BASE_KEYWORDS)
        with open(QUEUE_FILE, "w", encoding="utf-8") as f: f.write("\n".join(BASE_KEYWORDS))

    # 2. 큐 읽어오기
    with open(QUEUE_FILE, "r", encoding="utf-8") as f: lines = f.read().splitlines()
    
    if not lines:
        lines = prioritize_keywords(BASE_KEYWORDS)
        
    target_query = lines[0]
    title_guide = generate_title_variants(target_query) # CTR 테스트용 추천 제목
    
    # 3. 🔥 핵심: 순환형 큐 (글이 마르지 않고 계속 쌓이게 함)
    lines = lines[1:] + [target_query]
    with open(QUEUE_FILE, "w", encoding="utf-8") as f: f.write("\n".join(lines))

    print(f"🎯 [2/6] 오늘의 키워드: {target_query} (메인: {main_country}, 서브: {sub_country})")

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
        url = f"[https://search.naver.com/search.naver?ssc=tab.blog.all&query=](https://search.naver.com/search.naver?ssc=tab.blog.all&query=){urllib.parse.quote(target_query)}"
        driver.get(url)
        time.sleep(5)
        
        all_links = driver.find_elements(By.TAG_NAME, "a")
        seen_urls = set()
        
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

        if len(valid_links) > 5:
            selected_links = [valid_links[0]] + random.sample(valid_links[1:], 4)
        else:
            selected_links = valid_links

        if selected_links:
            target_blog_url = selected_links[0]['url'] 
            print(f"\n🔍 [3/6] 본문 추출 시작: 1위 고정 + 서브 랜덤 4개")
            
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
    return target_query, links_info_selected, target_blog_url, scraped_data, title_guide

# ==================== [4] 유동적 SVG 요약 카드 ====================
def create_summary_card_tag(summary_list, title):
    safe_list = [str(s).strip()[:15] for s in summary_list if s][:3]
    while len(safe_list) < 3: safe_list.append("") 
    l1, l2, l3 = safe_list

    svg_code = f"""
    <svg width="600" height="230" xmlns="[http://www.w3.org/2000/svg](http://www.w3.org/2000/svg)">
      <rect width="600" height="230" fill="#FFF9C4" rx="20"/>
      <text x="50%" y="70" font-family="'Apple Color Emoji', 'Segoe UI Emoji', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="30" text-anchor="middle" fill="#2c3e50">{l1}</text>
      <text x="50%" y="130" font-family="'Apple Color Emoji', 'Segoe UI Emoji', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="30" text-anchor="middle" fill="#2c3e50">{l2}</text>
      <text x="50%" y="190" font-family="'Apple Color Emoji', 'Segoe UI Emoji', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="30" text-anchor="middle" fill="#2c3e50">{l3}</text>
    </svg>
    """
    b64_svg = base64.b64encode(svg_code.encode('utf-8')).decode('utf-8')
    data_uri = f"data:image/svg+xml;base64,{b64_svg}"
    return f'<div style="text-align:center; margin:40px 0;"><img src="{data_uri}" style="max-width:100%; height:auto; border-radius:15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);" alt="{title} 핵심 요약 카드"/></div>'

# ==================== [5] 원고 생성 (🔥 궁극의 SEO 최적화) ====================
def generate_master_content(keyword, target_blog_url, scraped_data, title_guide):
    best_model = get_best_model()
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(best_model)

    prompt = f"""
[타겟 키워드]: {keyword}
[CTR 최적화 추천 제목 뼈대]: {title_guide}
[🔥 집중 분석 타겟 (실제 1위 블로그 뼈대 + 서브 블로그 4개 후기 합본)]: 
{scraped_data}

[미션]: 억지로 분량을 늘린 내용 없이, 핵심만 담은 '밀도 높은' 초고품질 딥다이브 포스팅으로 작성하라. 독자가 '결정'하게 만들고 '손해를 막아주는' 콘텐츠여야 한다.

[🔥 상위 노출 & 체류시간 폭발 지시사항 - 절대 엄수]:
1. **제목 최적화**: [추천 제목 뼈대]를 참고하되, 키워드와 맥락에 맞게 가장 클릭하고 싶은 제목으로 다듬어라.
2. **🔥 검색 의도(타입)별 맞춤형 글 구조**:
   - **돈/비용형**: '문제 제기 -> 손해 강조 -> 해결책 -> 비교' 위주.
   - **방법/절차형**: 독자가 따라 할 수 있는 '순서 설명(Step-by-step)' 필수.
   - **추천형**: '상황별 추천'과 명확한 '대안 비교' 필수.
3. **🔥 공통 필수 5가지 요소**:
   - 첫 3줄 이내에 독자의 뼈를 때리는 '문제 제기'.
   - 본문 곳곳에 숫자(시간/돈), 비교(전/후), 흔한 실수 포인트, 적용 상황을 녹여라.
   - "이유 + 상황 + 결과"가 담긴 짧고 사람 냄새나는 생생한 찐 후기 3줄 추가.
4. **외부 링크 다이어트 (최대 2~3개)**: SEO 점수 하락 방지를 위해 꼭 필요한 외부 링크 딱 2~3개만 본문 문맥 속에 자연스럽게 배치하라. (target="_blank" 필수)
   - 장소: <a href="[https://www.google.com/maps/search/?api=1&query=장소명+띄어쓰기+대체](https://www.google.com/maps/search/?api=1&query=장소명+띄어쓰기+대체)" target="_blank"> (띄어쓰기는 '+' 기호 사용)
5. **광고/협찬 세탁**: 특정 브랜드 홍보 내용 100% 삭제 및 객관적 정보로 변환.
6. **시간적 표현 절대 금지**: "2026년", "올해", "현재", "최근" 일절 금지. AI 멘트("알아보겠습니다") 절대 금지.
7. **🔥 구조화 및 동적 HTML 양식 적용 (패턴화 방지!)**:
   - 목차의 href와 본문 h2의 id는 'sec1' 같은 고정 단어가 아닌, **해당 문단의 핵심 내용을 나타내는 영문 단어(예: id="esim-cost")**로 매번 새롭게 만들어라. (스크롤 연동 필수)
   
   [HTML 작성 구조 가이드라인 - 반드시 아래 태그들을 사용할 것]
   <p class="intro">[현재 키워드 문제제기 1~2줄]</p>
   <nav>
     <ul>
       <li><a href="#[동적_영문ID_1]">1. [소제목]</a></li>
       <li><a href="#[동적_영문ID_2]">2. [소제목]</a></li>
     </ul>
   </nav>
   <h2 id="[동적_영문ID_1]">1. [소제목]</h2>
   <p>내용...</p>
   <h2 id="[동적_영문ID_2]">2. [소제목]</h2>
   <p>내용...</p>
   
8. **SVG 3줄 요약**: 'summary' 필드에 **[이모지 1개 + 띄어쓰기 포함 6글자 이하의 명사형 단어]** 3개 배열 반환.
9. **슬러그(URL)**: 한글 제목에서 핵심 키워드 2~3개만 뽑아 짧은 영어 단어 조합으로 생성.
10. **카테고리 지정**: 다음 리스트 중 택 1 -> ["여행 교통 팁", "여행 쇼핑 팁", "여행 관광 팁", "여행 준비 팁", "여행 맛집 팁", "생활 정보 꿀팁"]

[출력 포맷]: JSON (title, meta_desc, meta_keys, slug, summary, content, category)
"""
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"✍️ [4/6] 제미나이 원고 작성 중... (시도 {attempt + 1}/{max_retries})")
            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            
            raw_text = response.text.strip()
            # 백틱 제거 처리 안전화
            raw_text = raw_text.replace("```json", "").replace("```", "").strip()

            data = json.loads(raw_text)
            data['used_references'] = [target_blog_url]
            return data
            
        except Exception as e: 
            print(f"⚠️ 제미나이 JSON 문법 오류 발생: {e}")
            time.sleep(5)
            
    return None

# ==================== [6] 메인 실행 및 내부링크 삽입 ====================
def run_automation():
    print("🚀 프로세스 전체 시작...")
    
    # 1. Blogger 인증 (내부링크를 먼저 가져오기 위해 인증 먼저 수행)
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
            
    service = build('blogger', 'v3', credentials=creds)
    print("✅ [1/6] Blogger 인증 완료")

    # 2. 데이터 수집 및 큐 처리
    keyword, ref_info, target_url, scraped_data, title_guide = get_naver_target_data()
    
    # 3. 콘텐츠 생성
    data = generate_master_content(keyword, target_url, scraped_data, title_guide)
    if not data: 
        print("❌ 원고 생성 실패. 프로그램을 종료합니다.")
        # 실패 시 큐 마지막에 다시 추가
        with open(QUEUE_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + keyword)
        return
    
    # 4. 🔥 최신 글 5개 불러와서 내부링크 HTML 만들기
    recent_posts = get_recent_posts(service, BLOG_ID)
    related_html = ""
    if recent_posts:
        related_html = "<div class='related-posts'><h3>📌 같이 보면 좋은 글</h3><ul>"
        for p in recent_posts[:3]:
            related_html += f'<li><a href="{p["url"]}">{p["title"]}</a></li>'
        related_html += "</ul></div>"

    # 5. HTML 조합 (내부링크 -> SVG -> 광고)
    ads_code = """
    <div style="margin:45px 0;">
        <script async src="[https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2303846706279700](https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2303846706279700)" crossorigin="anonymous"></script>
        <ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-2303846706279700" data-ad-slot="1632085406" data-ad-format="auto" data-full-width-responsive="true"></ins>
        <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
    </div>
    """
    card_tag = create_summary_card_tag(data.get('summary', []), data['title'])
    content = data['content']

    # 🔥 nav 태그 바로 밑에 내부링크 블록을 삽입
    if re.search(r'</nav>', content, re.IGNORECASE):
        content = re.sub(r'(</nav>)', f'\\1{related_html}', content, flags=re.IGNORECASE, count=1)
    
    # 그 밑에 SVG 카드와 상단 광고 삽입
    top_insertion = f"{card_tag}{ads_code}"
    if re.search(r'</div><!-- related-posts -->', content): # 내부링크 뒤에 추가
        content = content.replace("</ul></div>", f"</ul></div>{top_insertion}", 1)
    elif re.search(r'</nav>', content, re.IGNORECASE):
        content = re.sub(r'(</nav>)', f'\\1{top_insertion}', content, flags=re.IGNORECASE, count=1)
    else:
        content = related_html + top_insertion + content

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
        .entry-content .intro {{ background: #f0f7ff; padding: 15px 20px; border-radius: 10px; border-left: 5px solid #3498db; margin-bottom: 30px; font-weight: bold; font-size: 17px; line-height: 1.6; }}
        .entry-content nav {{ background: #f8f9fa; padding: 25px; border-radius: 10px; border: 1px solid #eee; margin-bottom: 30px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
        .entry-content nav ul {{ list-style: none; padding-left: 0; }}
        .entry-content nav li {{ margin-bottom: 12px; font-size: 19px; }}
        .entry-content nav a {{ color: #2980b9; text-decoration: none; font-weight: bold; }}
        .entry-content nav a:hover {{ text-decoration: underline; color: #e74c3c; }}
        .related-posts {{ background: #fdfdfd; padding: 20px; border-radius: 10px; border: 2px dashed #3498db; margin-bottom: 30px; }}
        .related-posts h3 {{ margin-top: 0; color: #e74c3c; font-size: 20px; margin-bottom: 15px; }}
        .related-posts ul {{ padding-left: 20px; margin: 0; }}
        .related-posts li {{ margin-bottom: 8px; font-weight: bold; font-size: 17px; }}
        .related-posts a {{ color: #2c3e50; text-decoration: none; }}
        .related-posts a:hover {{ color: #3498db; text-decoration: underline; }}
        b {{ color: #e74c3c; }}
    </style>
    <div class="entry-content">{content}</div>
    """

    # 🔥 6. 카테고리 2개 적용 (메인 + "여행 꿀팁" 고정)
    chosen_category = data.get('category', '').strip()
    if chosen_category not in LABEL_OPTIONS:
        chosen_category = "여행 준비 팁" 
    
    final_labels = [chosen_category, "여행 꿀팁"]
    print(f"🏷️ [5/6] 적용된 카테고리: {final_labels}")
    
    try:
        slug_text = data.get('slug', 'auto-post')
        if not slug_text.strip(): slug_text = "auto-post"
        print(f"🚀 [6/6] 주소 생성 트릭 및 업로드 진행 중... ({slug_text})")
        
        temp_post = service.posts().insert(blogId=BLOG_ID, body={
            "title": slug_text, 
            "content": "loading...",
            "labels": final_labels
        }, isDraft=False).execute()

        service.posts().patch(blogId=BLOG_ID, postId=temp_post['id'], body={
            "title": data['title'], 
            "content": final_html,
            "customMetaData": data.get('meta_desc', '')
        }).execute() 
        
        print(f"✨ [완료] 최종 성공: {data['title']}")

    except Exception as e: 
        print(f"❌ 에러 발생: {e}")
        # 실패 글 재활용 (큐 맨 뒤로 다시 삽입)
        with open(QUEUE_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + keyword)
        print("🔄 업로드 실패로 인해 키워드를 큐에 다시 넣었습니다.")

if __name__ == "__main__":
    run_automation()
