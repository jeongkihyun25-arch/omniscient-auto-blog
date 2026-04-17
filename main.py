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

# 릴레이 우선순위 (경로를 정확히 'models/...'로 수정했습니다)
MODEL_RELAY = [
    "models/gemini-2.0-flash-exp", # 최신 실험형 (응답률 높음)
    "models/gemini-1.5-flash", 
    "models/gemini-1.5-pro",
    "models/gemini-1.0-pro" # 최후의 보루
]

def call_gemini_relay(prompt, max_tokens=8192):
    for model_name in MODEL_RELAY:
        # v1beta 대신 안정적인 v1 사용 시도
        url = f"https://generativelanguage.googleapis.com/v1/{model_name}:generateContent?key={API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": max_tokens}
        }
        try:
            print(f"📡 {model_name} 호출 시도 중...")
            res = requests.post(url, json=payload, timeout=120)
            res_json = res.json()
            
            if 'candidates' in res_json:
                print(f"✅ {model_name} 성공!")
                return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            else:
                # 에러 상세 로그 확인용
                msg = res_json.get('error', {}).get('message', '알 수 없는 오류')
                print(f"⚠️ {model_name} 실패: {msg}")
                continue 
        except Exception as e:
            print(f"⚠️ {model_name} 연결 에러: {e}")
            continue
    return None

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
        print(f"❌ 블로그 게시 실패: {e}")
        return False

if __name__ == "__main__":
    now = datetime.now()
    print(f"🚀 {now.strftime('%Y-%m-%d')} 릴레이 엔진 최종 가동")

    # 1. 주제 선정
    pick_prompt = "오늘 날짜 기준 애드센스 고수익 포스팅 주제 1개를 선정해줘. [주제: 제목 / 라벨: 라벨명 / 슬러그: 영문] 형식 엄수."
    strategy = call_gemini_relay(pick_prompt, 1000)
    
    if strategy:
        try:
            target_title = re.search(r'주제:\s*(.*?)(?=/|\n|$)', strategy).group(1).strip()
            target_label = re.search(r'라벨:\s*(.*?)(?=/|\n|$)', strategy).group(1).strip()
            target_slug = re.search(r'슬러그:\s*(.*)', strategy).group(1).strip()
        except:
            target_title = "재테크 핵심 가이드"; target_label = "재테크"; target_slug = "finance-guide"

        # 2. 본문 생성 (개인정보 언급 절대 금지)
        full_html = ""
        sections = [("본문", "🌸 혜택 중심 서론, 데이터 분석, 외부 링크 6개 포함 10,000자 이상")]
        
        for name, goal in sections:
            print(f"✍️ {name} 작성 중...")
            write_prompt = f"주제: {target_title}\n목표: {goal}\n규칙: HTML 사용, 필자 개인신상(양양, 차량, 가족 등) 언급 금지."
            content = call_gemini_relay(write_prompt, 8000)
            if content: full_html += content

        # 3. 게시
        if len(full_html) > 500:
            if post_to_blogger(target_title, full_html, target_label, target_slug):
                print(f"✨ 드디어 게시 성공: {target_title}")
    else:
        print("❌ 모든 모델의 쿼터가 소진되었습니다. 1시간 뒤에 다시 시도해주세요.")
