import os
import json
import requests
import time
import re
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# [설정 로드]
API_KEY = os.getenv("GEMINI_API_KEY")
BLOG_ID = os.getenv("BLOG_ID")
TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")

# 릴레이 우선순위 (위에서부터 차례대로 시도합니다)
MODEL_RELAY = [
    "gemini-3-flash", 
    "gemini-2.0-flash", 
    "gemini-1.5-pro", 
    "gemini-1.5-flash"
]

def call_gemini_relay(prompt, max_tokens=8192):
    """성공할 때까지 모델을 바꿔가며 호출하는 릴레이 함수"""
    for model_name in MODEL_RELAY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.8, "maxOutputTokens": max_tokens}
        }
        try:
            print(f"📡 {model_name} 모델로 시도 중...")
            res = requests.post(url, json=payload, timeout=120).json()
            
            # 답변이 정상적으로 들어있는지 확인
            if 'candidates' in res and res['candidates'][0]['content']['parts'][0]['text']:
                print(f"✅ {model_name} 호출 성공!")
                return res['candidates'][0]['content']['parts'][0]['text'].strip()
            else:
                reason = res.get('error', {}).get('message', '응답 내용 없음(Safety Filter 등)')
                print(f"⚠️ {model_name} 실패 사유: {reason}")
                continue # 다음 모델로 패스
        except Exception as e:
            print(f"⚠️ {model_name} 네트워크 에러: {e}")
            continue
    return None # 모든 모델이 실패했을 경우

def post_to_blogger(title, content, label, slug):
    try:
        creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON))
        service = build('blogger', 'v3', credentials=creds)
        body = {
            "title": title, "content": content, "labels": [label], 
            "customMetaData": slug, "blog": {"id": BLOG_ID}
        }
        service.posts().insert(blogId=BLOG_ID, body=body, isDraft=False).execute()
        return True
    except Exception as e:
        print(f"❌ 블로그 게시 에러: {e}")
        return False

if __name__ == "__main__":
    now = datetime.now()
    print(f"🚀 {now.strftime('%Y-%m-%d')} 자동화 엔진 가동 (릴레이 모드)")

    # 1. 주제 선정 (성공할 때까지 릴레이)
    pick_prompt = f"{now.strftime('%Y-%m-%d')} 기준 애드센스 고수익 주제 선정. [주제: 제목 / 라벨: 라벨명 / 슬러그: 영문] 형식으로만 답해줘."
    strategy = call_gemini_relay(pick_prompt, 1000)
    
    if strategy:
        try:
            target_title = re.search(r'주제:\s*(.*?)(?=/|\n|$)', strategy).group(1).strip()
            target_label = re.search(r'라벨:\s*(.*?)(?=/|\n|$)', strategy).group(1).strip()
            target_slug = re.search(r'슬러그:\s*(.*)', strategy).group(1).strip()
        except:
            target_title = "오늘의 핵심 경제 지표 요약"; target_label = "경제"; target_slug = "daily-finance"

        # 2. 본문 생성 (섹션별 릴레이 시도)
        full_html = ""
        sections = [
            ("도입", "🌸 독자 혜택 위주 서론 (3,500자)"),
            ("본론", "데이터 및 표를 활용한 심층 분석 (4,000자)"),
            ("결론", "공식 사이트 외부 링크 6개 포함 마무리 (3,000자)")
        ]
        
        for name, goal in sections:
            print(f"✍️ {name} 섹션 작성 시작...")
            write_prompt = f"주제: {target_title}\n목표: {goal}\n규칙: HTML 사용, 필자 개인정보(거주지, 차량, 나이 등) 절대 언급 금지."
            content = call_gemini_relay(write_prompt, 8000)
            if content:
                full_html += content + "\n\n"
            time.sleep(2)

        # 3. 최종 게시
        if len(full_html) > 1000:
            if post_to_blogger(target_title, full_html, target_label, target_slug):
                print(f"✨ 게시 성공: {target_title}")
    else:
        print("❌ 모든 모델이 응답에 실패했습니다. API 키나 쿼터를 확인해주세요.")
