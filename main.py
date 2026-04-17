import os
import json
import requests
import time
import random
import re
from bs4 import BeautifulSoup
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ==================== [1] 핵심 설정 (Secrets 연동) ====================
API_KEY = os.getenv("GEMINI_API_KEY")
BLOG_ID = os.getenv("BLOG_ID")
TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")
BASE_DOMAIN = "https://www.omniscient.kr"
PHARMA_CODE = '<div class="pharma-code" style="margin: 20px 0;"></div>'

# 모델 우선순위 (기현님의 헌팅 로직 적용)
MODEL_PRIORITY = ["gemini-3-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

# 블로그 작성 규칙 (기현님 스타일 가이드)
BLOG_RULES = """
- 서론 절대 생략, 🌸 이모지로 바로 독자 혜택(Benefit)부터 시작할 것.
- 20년 차 베테랑 블로거의 말투로 10,000자 이상의 압도적 정보량을 제공할 것.
- <h2>, <h3>, <table>, <ul> 태그를 사용하여 가독성을 극대화할 것.
- 외부 공식 링크(신뢰도 높은 사이트) 6개 이상을 본문 맥락에 맞게 삽입할 것.
"""

# ==================== [2] 핵심 엔진 (헌팅 및 검색) ====================

def get_best_model():
    """현재 가용한 모델 중 가장 최신 모델을 헌팅합니다."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        res = requests.get(url, timeout=15).json()
        available = [m['name'].replace('models/', '') for m in res.get('models', []) 
                     if 'generateContent' in m.get('supportedGenerationMethods', [])]
        for p in MODEL_PRIORITY:
            for m in available:
                if p in m: 
                    print(f"🎯 최신 모델 헌팅 성공: {m}")
                    return m
        return available[0]
    except: 
        return "gemini-1.5-flash"

def call_gemini(model_id, prompt, max_tokens=8192):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={API_KEY}"
    for attempt in range(5):
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.8, "maxOutputTokens": max_tokens}}
        try:
            res = requests.post(url, json=payload, timeout=120)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            elif res.status_code == 429:
                time.sleep((2 ** attempt) * 5)
        except: time.sleep(2)
    return None

def get_pure_trending_topics():
    print("📡 티스토리 실시간 인기 데이터 수집 중 (주관 0%)...")
    queries = ["site:tistory.com \"인기글\"", "site:tistory.com \"베스트 포스팅\""]
    raw_topics = []
    for q in queries:
        url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
        try:
            res = requests.get(url, timeout=10)
            soup = BeautifulSoup(res.text, 'xml')
            items = [item.title.text.split(' - ')[0].strip() for item in soup.find_all('item')[:5]]
            raw_topics.extend(items)
        except: pass
    return list(set(raw_topics))

def post_to_blogger(title, content, label, slug):
    creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON))
    service = build('blogger', 'v3', credentials=creds)
    body = {
        "title": title,
        "content": content,
        "labels": [label],
        "customMetaData": slug,
        "blog": {"id": BLOG_ID}
    }
    service.posts().insert(blogId=BLOG_ID, body=body, isDraft=False).execute()

# ==================== [3] 메인 프로세스 ====================

if __name__ == "__main__":
    now = datetime.now()
    print(f"🎂 기현님 40세 생일 - 엔진 가동\n")

    model_id = get_best_model()
    raw_results = get_pure_trending_topics()
    
    # 1. 수익성 주제 선정
    pick_prompt = f"현재: {now.strftime('%Y-%m-%d')}. 다음 중 CPC 높은 주제 선정: {raw_results}. 형식: 주제: [제목] / 라벨: [중 하나] / 슬러그: [영문-주소]"
    strategy = call_gemini(model_id, pick_prompt, 1000)
    
    try:
        target_title = re.search(r'주제:\s*(.*?)\s*/', strategy).group(1)
        target_label = re.search(r'라벨:\s*(.*?)\s*/', strategy).group(1).strip()
        target_slug = re.search(r'슬러그:\s*(.*)', strategy).group(1).strip()
    except:
        target_title = raw_results[0]; target_label = "IT 트렌드"; target_slug = "hot-topic"

    # 2. 1만 자 분할 집필
    full_html = f"\n"
    steps = [
        ("도입/요약", "서론 생략. 🌸 시작. 데이터 비교표 포함 3,500자"),
        ("심층/분석", "데이터 전문가 시각 분석 4,000자 (양양 거주자/GN7 오너 팁 포함)"),
        ("마무리/링크", "공식 링크 6개 포함 3,000자 결론")
    ]

    for name, goal in steps:
        print(f"🚀 {name} 섹션 작성 중...")
        content = call_gemini(model_id, f"{BLOG_RULES}\n주제: {target_title}\n목표: {goal}\nHTML로 작성.", 8000)
        if content: full_html += content + "\n\n"
        time.sleep(5)

    # 3. 블로그 직접 게시
    if len(full_html) > 1000:
        post_to_blogger(target_title, full_html, target_label, target_slug)
        print(f"✨ 게시 완료: {target_title}")
