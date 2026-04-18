import os
import pickle
import requests
import time
import random
import re
from datetime import datetime
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ==================== 설정 ====================
API_KEY = os.getenv("GEMINI_API_KEY")          # Gemini API 키
BLOG_ID = os.getenv("BLOG_ID")                 # 당신의 Blog ID (6254424106586242042)

# ==================== Gemini 함수 ====================
MODEL_PRIORITY = [
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
    "gemini-2.0-flash-001",
    "gemini-2.5-flash"
]

def get_best_model():
    print("🔍 Gemini 모델 탐색 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        res = requests.get(url, timeout=15).json()
        available = [m['name'].replace('models/', '') for m in res.get('models', [])
                     if 'generateContent' in m.get('supportedGenerationMethods', [])]
        for p in MODEL_PRIORITY:
            for m in available:
                if p in m:
                    print(f"🎯 선택 모델: {m}")
                    return m
        return available[0] if available else None
    except:
        return "gemini-2.5-flash-lite"


def call_gemini(prompt, max_tokens=8000):
    model_id = get_best_model()
    if not model_id:
        print("❌ 모델을 찾을 수 없습니다.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={API_KEY}"
    
    for attempt in range(7):
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.75, "maxOutputTokens": max_tokens, "topP": 0.95}
        }
        try:
            res = requests.post(url, json=payload, timeout=90)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            elif res.status_code == 429:
                wait = (2 ** attempt) * 6 + random.uniform(2, 6)
                print(f"⚠️ 429 → {wait:.1f}초 대기...")
                time.sleep(wait)
        except Exception as e:
            print(f"❌ Gemini 요청 오류: {e}")
        time.sleep(3)
    return None


# ==================== Blogger 게시 함수 (token.pickle 사용) ====================
def post_to_blogger(title, content, label, slug):
    try:
        # token.pickle 불러오기
        with open('token.pickle', 'rb') as f:
            creds = pickle.load(f)
        
        # Access Token 자동 갱신
        if creds.expired and creds.refresh_token:
            print("🔄 Access Token 갱신 중...")
            creds.refresh(Request())
        
        service = build('blogger', 'v3', credentials=creds)
        
        body = {
            "title": title,
            "content": content,
            "labels": [label],
            "blog": {"id": BLOG_ID}
        }
        
        service.posts().insert(blogId=BLOG_ID, body=body, isDraft=False).execute()
        print(f"✅ Blogger 게시 성공! 제목: {title}")
        return True
    except Exception as e:
        print(f"❌ Blogger 게시 실패: {e}")
        print("→ token.pickle을 삭제하고 get_blogger_refresh_token.py를 다시 실행해보세요.")
        return False


# ==================== 메인 ====================
if __name__ == "__main__":
    now = datetime.now()
    print(f"🚀 {now.strftime('%Y-%m-%d')} 기현님 자동화 시스템 가동\n")
    
    # 1. 주제 선정
    pick_prompt = """
현재 2026년 4월 기준으로 여행 실용 정보 블로그에 적합하면서 
수익성(CPC)도 괜찮은 실용적인 주제 하나를 추천해줘.

형식:
주제: [주제명]
라벨: [라벨명]
슬러그: [영문-slug]
"""
    strategy = call_gemini(pick_prompt, 800)
    
    if not strategy:
        print("❌ 주제 선정 실패")
        exit()

    try:
        target_title = re.search(r'주제:\s*(.*?)(?=\n|라벨:|$)', strategy, re.DOTALL).group(1).strip()
        target_label = re.search(r'라벨:\s*(.*?)(?=\n|슬러그:|$)', strategy, re.DOTALL).group(1).strip()
        target_slug = re.search(r'슬러그:\s*(.*)', strategy, re.DOTALL).group(1).strip()
    except:
        target_title = "2026 해외여행 수하물 규정 완벽 정리"
        target_label = "여행 교통 팁"
        target_slug = "2026-baggage-guide"

    print(f"🎯 선정 주제: {target_title}")
    print(f"🏷️ 라벨: {target_label}")
    print(f"🔗 슬러그: {target_slug}")

    # 2. 본문 생성
    print("\n✍️ 본문 생성 중...")
    write_prompt = f"""
주제: {target_title}

규칙:
- HTML 형식으로 작성 (h2, h3, table, ul, li 적극 사용)
- 6000자 이상의 상세하고 실용적인 내용
- 개인 정보 절대 언급 금지
- 공식 링크(인천공항, 외교부 해외안전여행, 일본관광청 등) 6개 이상 자연스럽게 포함
"""
    full_html = call_gemini(write_prompt, 10000)

    if full_html and len(full_html) > 2000:
        print(f"✅ 본문 생성 완료 ({len(full_html):,}자)")
        
        # 3. Blogger 게시
        if post_to_blogger(target_title, full_html, target_label, target_slug):
            print(f"\n✨ 성공! {now.strftime('%Y-%m-%d')} 포스팅이 게시되었습니다.")
        else:
            print("\n❌ 게시 실패 → token.pickle을 삭제하고 다시 발급받아보세요.")
    else:
        print("❌ 본문 생성 실패")
