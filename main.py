import os
import json
import requests
import time
import re
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# [설정]
API_KEY = os.getenv("GEMINI_API_KEY")
BLOG_ID = os.getenv("BLOG_ID")
TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")

# 릴레이 리스트 (가장 확실한 경로들입니다)
MODEL_RELAY = [
    "models/gemini-2.0-flash", 
    "models/gemini-2.0-flash-exp",
    "models/gemini-1.5-flash",
    "models/gemini-1.5-pro"
]

def call_gemini_relay(prompt, max_tokens=8192):
    for model_name in MODEL_RELAY:
        # v1beta를 사용해야 최신 모델을 찾습니다
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": max_tokens}
        }
        try:
            print(f"📡 {model_name} 호출 시도...")
            res = requests.post(url, json=payload, timeout=60)
            res_json = res.json()
            
            if 'candidates' in res_json:
                print(f"✅ {model_name} 성공!")
                return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            else:
                msg = res_json.get('error', {}).get('message', '응답 없음')
                print(f"⚠️ {model_name} 실패: {msg}")
                continue 
        except Exception as e:
            print(f"⚠️ {model_name} 에러: {e}")
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
    print(f"🚀 {now.strftime('%Y-%m-%d')} 자동화 재가동")

    # 1. 주제 선정
    pick_prompt = "구글 애드센스 고단가 주제 1개를 정해서 [주제: 제목 / 라벨: 라벨명 / 슬러그: 영문] 형식으로 알려줘."
    strategy = call_gemini_relay(pick_prompt, 1000)
    
    if strategy:
        try:
            target_title = re.search(r'주제:\s*(.*?)(?=/|\n|$)', strategy).group(1).strip()
            target_label = re.search(r'라벨:\s*(.*?)(?=/|\n|$)', strategy).group(1).strip()
            target_slug = re.search(r'슬러그:\s*(.*)', strategy).group(1).strip()
        except:
            target_title = "재테크 핵심 비법"; target_label = "재테크"; target_slug = "finance-tips"

        # 2. 본문 생성 (개인정보 언급 금지)
        full_html = ""
        write_prompt = f"주제: {target_title}\n목표: 독자 혜택 중심의 10,000자 이상 포스팅, HTML 태그 사용, 필자 개인신상(양양, 차, 나이) 절대 언급 금지."
        
        content = call_gemini_relay(write_prompt, 8000)
        if content:
            full_html = content

        # 3. 게시
        if len(full_html) > 500:
            if post_to_blogger(target_title, full_html, target_label, target_slug):
                print(f"✨ 드디어 성공! 40세 첫 포스팅 완료: {target_title}")
    else:
        print("❌ 모든 모델 호출 실패. API 키의 유효성을 다시 확인해주세요.")
