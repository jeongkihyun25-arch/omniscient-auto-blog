import os
import json
import requests
import time
import re
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ==================== [1] 설정 로드 (Secrets 연동) ====================
API_KEY = os.getenv("GEMINI_API_KEY")
BLOG_ID = os.getenv("BLOG_ID")
TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")

# 기현님의 모델 헌팅 로직 (최신 프리뷰 모델부터 헌팅)
MODEL_PRIORITY = [
    "gemini-3-flash", 
    "gemini-2.5-flash", 
    "gemini-2.0-flash", 
    "gemini-1.5-flash"
]

# 블로그 작성 규칙 (개인정보 언급 금지 지시 강화)
BLOG_RULES = """
- 서론 절대 생략, 🌸 이모지로 바로 독자에게 필요한 핵심 정보부터 시작할 것.
- 20년 차 베테랑 전문가의 말투로 10,000자 이상의 압도적인 분량을 제공할 것.
- <h2>, <h3>, <table>, <ul> 태그를 사용하여 가독성을 극대화할 것.
- 외부 공식 신뢰 사이트 링크 6개 이상을 본문 맥락에 맞게 삽입할 것.
- **중요**: 필자의 거주지, 소유 차량, 나이, 가족 관계 등 모든 개인 신상 정보는 절대 언급하지 말 것.
"""

# ==================== [2] 핵심 엔진 ====================

def get_best_model():
    """가장 성능 좋은 최신 모델을 낚아챕니다."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        res = requests.get(url, timeout=15).json()
        available = [m['name'].replace('models/', '') for m in res.get('models', []) 
                     if 'generateContent' in m.get('supportedGenerationMethods', [])]
        for p in MODEL_PRIORITY:
            for m in available:
                if p in m: 
                    print(f"🎯 모델 헌팅 성공: {m}")
                    return m
        return "gemini-1.5-flash"
    except: 
        return "gemini-1.5-flash"

def call_gemini(model_id, prompt, max_tokens=8192):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.8, "maxOutputTokens": max_tokens}
    }
    try:
        res = requests.post(url, json=payload, timeout=180)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f"⚠️ AI 호출 에러: {e}")
        return None

def post_to_blogger(title, content, label, slug):
    try:
        # 기현님이 새로 뽑으신 '진짜 열쇠' 사용
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
        return True
    except Exception as e:
        print(f"❌ 게시 실패: {e}")
        return False

# ==================== [3] 메인 프로세스 ====================

if __name__ == "__main__":
    now = datetime.now()
    print(f"🚀 {now.strftime('%Y-%m-%d')} 기현님 전용 자동 포스팅 엔진 가동")

    model_id = get_best_model()

    # 1. 고수익 주제 선정
    pick_prompt = f"현재 날짜 {now.strftime('%Y-%m-%d')}. 구글 트렌드 기반 애드센스 수익성 높은 주제 선정. [주제: 제목 / 라벨: 라벨명 / 슬러그: 영문] 형식으로만 답해줘."
    strategy = call_gemini(model_id, pick_prompt, 1000)
    print(f"📝 전략 수립 완료: {strategy}")

    try:
        target_title = re.search(r'주제:\s*(.*?)\s*/', strategy).group(1)
        target_label = re.search(r'라벨:\s*(.*?)\s*/', strategy).group(1).strip()
        target_slug = re.search(r'슬러그:\s*(.*)', strategy).group(1).strip()
    except:
        target_title = f"오늘의 트렌드 핵심 요약 - {now.strftime('%m%d')}"
        target_label = "IT 트렌드"; target_slug = f"trend-{now.strftime('%m%d')}"

    # 2. 1만 자 본문 3단계 분할 생성
    full_html = ""
    sections = [
        ("도입부", "🌸 시작, 핵심 요약 및 독자 혜택 중심 (3,500자)"),
        ("상세 분석", "표(table)와 리스트를 활용한 심층 데이터 분석 (4,000자)"),
        ("결론 및 링크", "실제 활용 팁 및 외부 공식 링크 6개 이상 포함 (3,000자)")
    ]

    for name, goal in sections:
        print(f"✍️ {name} 섹션 작성 중 (개인정보 배제)...")
        write_prompt = f"{BLOG_RULES}\n주제: {target_title}\n목표: {goal}\n필자의 개인 신상 정보는 일절 언급하지 말고 오직 정보에만 집중할 것."
        content = call_gemini(model_id, write_prompt, 8000)
        if content: full_html += content + "\n\n"
        time.sleep(5) # 안정성을 위한 텀

    # 3. 블로그 최종 게시
    if len(full_html) > 1000:
        if post_to_blogger(target_title, full_html, target_label, target_slug):
            print(f"✅ 대성공! 'omniscient.kr'에 글이 게시되었습니다: {target_title}")
        else:
            print("❌ 게시 과정에서 오류가 발생했습니다.")
    else:
        print("❌ 본문 생성량이 부족하여 중단되었습니다.")
