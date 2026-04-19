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
    
    # 🔥 전문성(Authority)을 위해 테마별로 묶어서 순차적으로 발행!
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

# ==================== [5] 원고 생성 (🔥 SEO 끝판왕 마스터 프롬프트) ====================
def generate_master_content():
    keyword, reference_blogs, target_blog_url, scraped_data = get_naver_target_data()
    best_model = get_best_model()
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(best_model)

    prompt = f"""
[타겟 키워드]: {keyword}
[🔥 집중 분석 타겟 (실제 1위 블로그 뼈대 + 서브 블로그 4개 후기 합본)]: 
{scraped_data}

[미션]: 위 [집중 분석 타겟]의 텍스트를 해부하여 5,000자 이상의 초고품질 딥다이브 포스팅으로 작성하라. 여행 글은 단순한 '정보 나열'이 아니라, 검색한 사람이 '결정'하게 만들고 '손해를 막아주는' 콘텐츠여야 한다.

[🔥 상위 노출 & 체류시간 폭발 카피라이팅 지시사항 - 절대 엄수]:
1. **제목은 무조건 '손해/숫자/상황' 조합형**: "이거 안 하면 요금 3배 나옵니다", "늦은 밤 도착하면 택시비 2배 (이렇게 해결)", "공항에서 30분 줄이는 핵심 1가지" 처럼 구체적 수치와 손실회피 심리를 섞어 자극적으로 지어라.
2. **🔥 반드시 지켜야 할 8단계 글 구조 (CTR + 체류시간 핵심)**:
   ① 문제 제기 (첫 3줄 공감 유도. 예: "공항에서 시간 버린 적 있죠?")
   ② 손해 강조 (돈/시간 낭비를 강조. 예: "이거 모르고 가면 하루 2만원 그냥 나갑니다")
   ③ 해결책 즉시 제시 (빙빙 돌리지 말고 바로 정답부터 던져라)
   ④ 핵심 방법 3~5개 (단순 나열 절대 금지! "왜 해야 좋은지" 구체적 이유 필수)
   ⑤ ⚡ 상황별 사용법 (초보 vs 고수, 가족 vs 혼자 등 타겟을 나눠서 차별화된 팁 제공)
   ⑥ ❌ 비추천 대상 (신뢰도 폭발용. "이런 분들은 굳이 필요 없어요" 솔직하게 작성)
   ⑦ 👍 실제 느낌 후기 (가공된 타겟 소스 활용. 2~3줄로 짧고 강렬하게. 예: "이거 쓰고 위탁 안 맡겼더니 30분 절약됨")
   ⑧ 한줄 결론 (기억에 팍 남는 멘트 하나 던지기)
3. **🔥 무조건 넣어야 하는 5가지 필수 요소**:
   - 숫자 (시간/돈/% 정확하게 명시)
   - 비교 (하기 전 vs 후)
   - 실수 포인트 (사람들이 흔히 놓치는 것)
   - 상황 (언제/누구에게 필요한지)
   - 감정 (짜증/손해/편안함 등 실제 감정 묘사)
4. **하단 스팸 링크 금지 & 본문 내 자연스러운 링크 삽입**: 문서 맨 밑에 '더 알아보기' 같은 링크 리스트를 만들지 마라! 대신 본문을 작성하면서 문맥상 꼭 필요한 중요 정보나 장소에 자연스럽게 구글 링크를 걸어라 (최소 4~6개 필수, 모두 target="_blank").
   - 장소: <a href="https://www.google.com/maps/search/?api=1&query=장소명+띄어쓰기+대체" target="_blank"> (띄어쓰기는 무조건 '+'로 변경!)
   - 정보: <a href="https://www.google.com/search?q=정확한+검색어" target="_blank">
5. **광고/협찬 원천 차단 (브랜드 세탁)**: 원본 글에 특정 브랜드(캐리어, 유심 업체 등) 홍보가 있다면 싹 지우고, 객관적인 '선택 기준'이나 '방법론'으로 100% 필터링하라.
6. **시간적 표현 절대 금지**: "2026년", "최신", "올해", "현재", "최근" 일절 금지.
7. **AI 멘트 원천 차단**: "출처를 종합했다", "알아보겠습니다" 금지.
8. **구조화 요소**: 서론은 `<p class="intro">` 사용. 목차 `<nav>` 및 `<h2 id="...">` 앵커 연동. 표 3개, 리스트 5개 이상.
9. **SVG 3줄 요약**: 'summary' 필드에 **[이모지 1개 + 띄어쓰기 포함 6글자 이하의 명사형 단어]** 3개 배열 반환.
10. **슬러그(URL)**: 한글 제목에서 핵심 키워드 2~3개만 뽑아 짧은 영어 단어 조합으로 생성 (예: flight-ticket-hacks).
11. **🔥 카테고리(라벨) 강제 지정**: 너가 작성한 글의 주제와 가장 완벽하게 일치하는 카테고리를 다음 리스트 중에서 딱 1개만 골라 정확한 텍스트로 반환하라. -> ["여행 교통 팁", "여행 쇼핑 팁", "여행 관광 팁", "여행 준비 팁", "여행 맛집 팁", "생활 정보 꿀팁"]

[출력 포맷]: JSON (title, meta_desc, meta_keys, slug, summary, content, category)
"""
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"✍️ [4/5] 제미나이 원고 작성 중... (시도 {attempt + 1}/{max_retries})")
            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            
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
            time.sleep(5)
            
    print("❌ 제미나이가 3번 연속으로 헛소리를 했습니다. 원고 생성을 포기합니다.")
    return None

# ==================== [6] 실행 및 블로거 업로드 ====================
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
            <script async src="[https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2303846706279700](https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2303846706279700)" crossorigin="anonymous"></script>
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
            .entry-content .intro {{ background: #f0f7ff; padding: 15px 20px; border-radius: 10px; border-left: 5px solid #3498db; margin-bottom: 30px; font-weight: bold; font-size: 17px; line-height: 1.6; }}
            .entry-content nav {{ background: #f8f9fa; padding: 25px; border-radius: 10px; border: 1px solid #eee; margin-bottom: 30px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            .entry-content nav ul {{ list-style: none; padding-left: 0; }}
            .entry-content nav li {{ margin-bottom: 12px; font-size: 19px; }}
            .entry-content nav a {{ color: #2980b9; text-decoration: none; font-weight: bold; }}
            .entry-content nav a:hover {{ text-decoration: underline; color: #e74c3c; }}
            b {{ color: #e74c3c; }}
        </style>
        <div class="entry-content">{content}</div>
        """

        # 🔥 제미나이가 골라준 카테고리 적용 로직
        chosen_category = data.get('category', '').strip()
        if chosen_category not in LABEL_OPTIONS:
            # 제미나이가 이상한 걸 골랐거나 오류를 냈을 경우 기본값: "여행 준비 팁"
            chosen_category = "여행 준비 팁" 
        
        final_labels = [chosen_category]
        print(f"🏷️ [적용된 카테고리]: {chosen_category}")

        with open('token.json', 'rb') as t:
            creds = pickle.load(t)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
        
        service = build('blogger', 'v3', credentials=creds)
        
        # 1단계: 영어 슬러그 확보용 초안
        slug_text = data.get('slug', 'auto-post')
        if not slug_text.strip(): slug_text = "auto-post"
        print(f"🚀 [5/5] 주소 생성용 트릭 실행 중... ({slug_text})")
        
        temp_post = service.posts().insert(blogId=BLOG_ID, body={
            "title": slug_text, 
            "content": "loading...",
            "labels": final_labels
        }, isDraft=False).execute()

        # 2단계: 진짜 한글 제목 덮어쓰기
        print(f"🚀 [5/5] 진짜 한글 제목 덮어쓰는 중... ({data['title']})")
        service.posts().patch(blogId=BLOG_ID, postId=temp_post['id'], body={
            "title": data['title'], 
            "content": final_html,
            "customMetaData": data.get('meta_desc', '')
        }).execute() 
        
        print(f"✨ [완료] 최종 성공: {data['title']}")

    except Exception as e: print(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    run_automation()
