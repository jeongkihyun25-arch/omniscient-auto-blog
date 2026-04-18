import os
import json
import requests
import time
import random
import re
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ==================== 설정 ====================
# .env나 환경변수로 관리하는 것을 강력 추천
API_KEY = os.getenv("GEMINI_API_KEY")          # ← 여전히 필요
BLOG_ID = os.getenv("BLOG_ID")
TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")    # Blogger용

# 2026년 4월 현재 살아있는 안정적인 모델 우선순위
MODEL_PRIORITY = [
    "gemini-2.5-flash-lite",     # 가장 추천 (무료 티어에서 상대적으로 관대)
    "gemini-flash-latest",
    "gemini-2.0-flash-001",
    "gemini-2.5-flash",
    "gemini-2.5-pro"
]

def get_best_model():
    """현재 사용 가능한 최고 모델 자동 선택"""
    print("🔍 현재 사용 가능한 Gemini 모델 탐색 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        res = requests.get(url, timeout=15).json()
        available = [m['name'].replace('models/', '') for m in res.get('models', [])
                     if 'generateContent' in m.get('supportedGenerationMethods', [])]
        
        for priority in MODEL_PRIORITY:
            for model in available:
                if priority in model:
                    print(f"🎯 선택된 모델: {model}")
                    return model
        print("⚠️ 우선순위 모델 없음 → 첫 번째 모델 사용")
        return available[0] if available else None
    except Exception as e:
        print(f"❌ 모델 리스트 가져오기 실패: {e}")
        return "gemini-2.5-flash-lite"


def call_gemini(prompt, max_tokens=6000):
    """안정적인 모델 선택 + 429 방어 강화"""
    model_id = get_best_model()
    if not model_id:
        print("❌ 사용 가능한 모델이 없습니다.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={API_KEY}"
    
    for attempt in range(7):
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.75,
                "maxOutputTokens": max_tokens,
                "topP": 0.95
            }
        }
        try:
            res = requests.post(url, json=payload, timeout=90)
            
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            
            elif res.status_code == 429:
                wait = (2 ** attempt) * 6 + random.uniform(2, 6)
                print(f"⚠️ 429 Quota 초과 → {wait:.1f}초 대기 중... (시도 {attempt+1}/7)")
                time.sleep(wait)
            else:
                print(f"❌ API 오류 {res.status_code}: {res.text[:300]}")
                break
        except Exception as e:
            print(f"❌ 요청 예외: {e}")
        
        time.sleep(3)
    
    print("❌ 모든 시도 실패 → API 키 또는 billing 확인 필요")
    return None


def post_to_blogger(title, content, label, slug):
    try:
        creds_data = json.loads(TOKEN_JSON)
        creds = Credentials.from_authorized_user_info(creds_data)
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
        return False


# ==================== 메인 ====================
if __name__ == "__main__":
    now = datetime.now()
    print(f"🚀 {now.strftime('%Y-%m-%d')} 기현님 자동화 시스템 가동\n")
    
    # 1. 주제 선정 (더 구체적으로)
    pick_prompt = """
현재 2026년 4월 기준으로 구글 애드센스에서 수익성(CPC)이 높고, 
여행/생활 정보 블로그에 잘 맞는 실용적인 주제 1개를 추천해줘.

형식 정확히 지켜서 출력:
주제: [주제명]
라벨: [라벨명]
슬러그: [영문-slug]
"""
    strategy = call_gemini(pick_prompt, max_tokens=800)
    
    if not strategy:
        print("❌ 주제 선정 실패. API 상태를 확인해주세요.")
        exit()
    
    try:
        target_title = re.search(r'주제:\s*(.*?)(?=\n|라벨:|$)', strategy, re.DOTALL).group(1).strip()
        target_label = re.search(r'라벨:\s*(.*?)(?=\n|슬러그:|$)', strategy, re.DOTALL).group(1).strip()
        target_slug = re.search(r'슬러그:\s*(.*)', strategy, re.DOTALL).group(1).strip()
    except:
        target_title = "2026 해외여행 수하물 규정 완벽 정리"
        target_label = "여행 교통 팁"
        target_slug = "2026-overseas-baggage-guide"

    print(f"🎯 선정 주제: {target_title}")
    print(f"🏷️  라벨: {target_label}")
    print(f"🔗 슬러그: {target_slug}")

    # 2. 본문 생성 (개인 정보 완전 배제)
    print(f"\n✍️ 본문 생성 중... (약 5000~8000자 목표)")
    write_prompt = f"""
주제: {target_title}

규칙:
- HTML 형식으로 작성 (h2, h3, table, ul, li 적극 사용)
- 5000자 이상의 상세하고 실용적인 내용
- 필자 개인 정보(양양, GN7, 나이, 가족 등) 절대 언급 금지
- 공신력 있는 외부 링크를 자연스럽게 5개 이상 포함
- 독자에게 바로 도움이 되는 실용 정보 중심
"""
    full_html = call_gemini(write_prompt, max_tokens=10000)

    if full_html and len(full_html) > 1000:
        print(f"✅ 본문 생성 완료 ({len(full_html):,}자)")
        
        # 3. Blogger 게시
        if post_to_blogger(target_title, full_html, target_label, target_slug):
            print(f"\n✨ 성공! {now.strftime('%Y-%m-%d')} 포스팅이 게시되었습니다.")
        else:
            print("\n❌ 게시 실패. Blogger 토큰을 확인해주세요.")
    else:
        print("❌ 본문 생성 실패 또는 내용이 너무 짧습니다.")

    print("\n문제가 지속되면:")
    print("1. Google Cloud Console에서 Billing 계정 연결 (무료 티어 quota 활성화)")
    print("2. 새 API 키 발급 후 GEMINI_API_KEY 교체")
    print("3. 모델 리스트를 다시 확인 (get_best_model 함수 사용)")
