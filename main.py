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

# ==================== [3] 네이버 수집 (🔥 테마별 전문성 축적 + 1+4 본문 추출) ====================
def get_naver_target_data():
    now = datetime.now()
    m = [now.month, (now.month % 12) + 1, ((now.month + 1) % 12) + 1]
    
    # 🔥 전문성(Authority)을 위해 테마별로 묶어서 순차적으로 발행합니다! (랜덤 셔플 삭제)
    BASE_KEYWORDS = [
        # 테마 1: 공항 및 출국 (전문성 집중)
        "인천공항 주차", "공항 라운지", "스마트패스", "공항 리무진", "수하물 규정", "기내 반입", "여권 발급", "항공권 특가",
        # 테마 2: 일본 여행 특화
        "비지트 재팬", "돈키호테", "일본 환전 꿀팁", "트래블월렛", "트래블로그", "일본 esim 설치", "일본 유심 추천",
        # 테마 3: 해외여행 필수 준비 및 안전
        "해외여행 준비물", "여행자 보험", "비상약 리스트", "입국 심사", "세관 신고", "해외 로밍", "가족 여행",
        # 테마 4: 숙박 및 현지 여행지 추천
        "아고다 할인", "에어비앤비", "가성비 숙소", "면세점 쇼핑", "현지 맛집", f"{m[0]}월 여행지", f"{m[1]}월 여행지"
    ]

    if not os.path.exists(QUEUE_FILE) or os.stat(QUEUE_FILE).st_size == 0:
        # random.shuffle(BASE_KEYWORDS) <-- 장기 SEO를 위해 랜덤 추출을 뺐습니다! 차례대로 뽑아먹습니다.
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
            print(f"\n🔍 [본문 추출 시작: 1위 고정 + 서브 랜덤 4개]")
            
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

# ==================== [5] 원고 생성 (🔥 AI 오류 방어 및 3회 재시도 로직) ====================
def generate_master_content():
    keyword, reference_blogs, target_blog_url, scraped_data = get_naver_target_data()
    best_model = get_best_model()
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(best_model)

    prompt = f"""
[타겟 키워드]: {keyword}
[🔥 집중 분석 타겟 (실제 1위 블로그 뼈대 + 서브 블로그 4개 후기 합본)]: 
{scraped_data}

[미션]: 위 [집중 분석 타겟]의 '실제 텍스트 본문'을 뼛속까지 해부하여 5,000자 이상의 초고품질 딥다이브 포스팅으로 작성하라. 절대 원문과 똑같은 패턴으로 쓰지 마라.

[🔥 A급 블로그 장기 SEO & 카피라이팅 지시사항 - 절대 엄수]:
1. **유사문서 회피 (단순 리라이팅 금지 -> '완전 재해석')**: 원본 글의 문장 구조나 전개 방식을 앵무새처럼 따라 하지 마라. 정보를 완전히 분해한 뒤, 너만의 새로운 시각과 흐름으로 '재해석'하여 독창적인 문서로 만들어라.
2. **AI 탐지 100% 회피 (리얼 후기 1줄 강제 삽입)**: 글이 너무 정형화되면 AI로 걸린다. 의도적으로 짧고 끊어지는 문장을 섞어라. 특히 본문 어딘가에 "내가 직접 그 상황에서 느꼈던 짜증이나 안도감 같은 구체적인 감정 묘사 1~2줄"을 사람 냄새나게 툭 던지듯 반드시 넣어라.
3. **클릭을 유발하는 자극형 제목**: 사전적 제목 금지. "이거 안 하면 손해", "안 하면 줄 40분 더 서는 이유" 처럼 구체적 상황과 손실 회피 심리를 자극하라. 끝에 "(실제 후기)" 혹은 "(비교 꿀팁)"을 붙여라.
4. **독자의 고민을 끝내는 '비교 구조' 필수**: A vs B (예: 스마트패스 vs 일반줄, 로밍 vs 이심, 택시 vs 리무진 등)를 자연스럽게 찾아내어, 시간 차이와 상황별 추천을 확실하게 때려주는 파트를 만들어라.
5. **정예 링크만 (4~6개 필수, 스팸 방지)**: 무지성으로 링크를 남발하지 마라. 독자에게 진짜 필요한 핵심 링크만 4~6개 자연스럽게 배치하라. 모두 target="_blank".
   - **장소 (식당, 숙소, 관광지 등)**: 구글 지도 공식 검색 링크 사용. 띄어쓰기가 있다면 반드시 '+' 기호로 연결할 것! -> <a href="https://www.google.com/maps/search/?api=1&query=장소명+띄어쓰기+대체" target="_blank">장소명</a>
   - **일반 정보 (교통편, 팁 등)**: 구글 일반 검색 링크 사용. 띄어쓰기는 '+' 기호로 연결! -> <a href="https://www.google.com/search?q=정확한+검색어" target="_blank">정보 텍스트</a>
6. **시간적 표현 절대 금지**: "2026년", "최신", "올해", "현재", "최근" 등 유행 타는 단어 일절 금지.
7. **AI 멘트 원천 차단**: "출처를 종합했다", "작성되었습니다", "알아보겠습니다" 금지.
8. **구조화 요소**: 서론은 `<p class="intro">` 사용. 서론 밑에 `<nav>` 목차 및 `<h2 id="...">` 앵커 연동. 표 3개, 리스트 5개 이상. 하단에 구글 일반검색 링크 4개 추천 리스트.
9. **SVG 3줄 요약**: 'summary' 필드에 **[이모지 1개 + 띄어쓰기 포함 6글자 이하의 명사형 단어]** 3개 배열 반환.
10. **슬러그(URL)**: 한글 제목에서 핵심 키워드 2~3개만 뽑아 짧은 영어 단어 조합으로 생성 (예: airport-lounge-tips).

[출력 포맷]: JSON (title, meta_desc, meta_keys, slug, summary, content, label_indices)
"""
    
    max_retries = 3 # 최대 3번까지 다시 쓰게 만듦
    for attempt in range(max_retries):
        try:
            print(f"✍️ [4/5] 제미나이 원고 작성 중... (시도 {attempt + 1}/{max_retries})")
            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            
            # 텍스트 청소 (가끔 제미나이가 쓸데없는 마크다운을 붙이는 것 방지)
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text.replace("```json", "", 1).strip()
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3].strip()

            data = json.loads(raw_text)
            data['used_references'] = [target_blog_url]
            return data
            
        except Exception as e: 
            print(f"⚠️ 제미나이 JSON 문법 오류 발생 (재시도 준비 중...): {e}")
            time.sleep(5) # 5초 숨 고르고 다시 시도
            
    print("❌ 제미나이가 3번 연속으로 헛소리를 했습니다. 원고 생성을 포기합니다.")
    return None

# ==================== [6] 실행 및 블로거 업로드 (퍼머링크 트릭 유지) ====================
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
        
        # 1단계: 영어 슬러그 확보용 초안
        slug_text = data.get('slug', 'auto-post')
        if not slug_text.strip(): slug_text = "auto-post"
        print(f"🚀 [4/5] 주소 생성용 트릭 실행 중... ({slug_text})")
        
        temp_post = service.posts().insert(blogId=BLOG_ID, body={
            "title": slug_text, 
            "content": "loading...",
            "labels": final_labels
        }, isDraft=False).execute()

        # 2단계: 진짜 한글 제목 덮어쓰기
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
