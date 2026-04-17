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

def call_gemini_direct(prompt):
    """라이브러리 없이 직접 구글 서버에 요청을 꽂아버립니다."""
    # 가장 확실한 모델명 3가지 순회
    models = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.0-pro"]
    
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 8000}
        }
        
        try:
            print(f"📡 {model} 모델로 직접 연결 시도 중...")
            res = requests.post(url, headers=headers, json=payload, timeout=60)
            res_data = res.json()
            
            if 'candidates' in res_data:
                print(f"✅ {model} 연결 성공!")
                return res_data['candidates'][0]['content']['parts'][0]['text'].strip()
            else:
                print(f"⚠️ {model} 응답 없음: {res_data.get('error', {}).get('message', 'Unknown Error')}")
        except Exception as e:
            print(f"⚠️ {model} 통신 에러: {e}")
            
    return None

def post_to_blogger(title, content, label, slug):
    try:
        creds_data = json.loads(TOKEN_JSON)
        creds = Credentials.from_authorized_user_info(creds_data)
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
    print(f"🚀 {now.strftime('%Y-%m-%d')} 최후의 수단 가동")

    # 1. 주제 선정
    pick_prompt = "구글 애드센스 수익성 높은 포스팅 주제 1개 추천해줘. 형식: [주제: 제목 / 라벨: 라벨명 / 슬러그: 영문]"
    strategy = call_gemini_direct(pick_prompt)
    
    if strategy:
        try:
            target_title = re.search(r'주제:\s*(.*?)(?=/|\n|$)', strategy).group(1).strip()
            target_label = re.search(r'라벨:\s*(.*?)(?=/|\n|$)', strategy).group(1).strip()
            target_slug = re.search(r'슬러그:\s*(.*)', strategy).group(1).strip()
        except:
            target_title = "재테크 핵심 비결"; target_label = "재테크"; target_slug = "finance-tips"

        # 2. 본문 생성 (개인정보 언급 금지)
        print(f"✍️ '{target_title}' 본문 생성 중...")
        write_prompt = f"주제: {target_title}\n규칙: HTML 사용, 5,000자 이상, 필자 개인신상(양양, 차량, 40세 등) 절대 언급 금지."
        full_html = call_gemini_direct(write_prompt)

        # 3. 게시
        if full_html and len(full_html) > 500:
            if post_to_blogger(target_title, full_html, target_label, target_slug):
                print(f"✨ [경축] 40세 생일 첫 포스팅 성공!")
    else:
        print("❌ 모든 시도가 실패했습니다. API 키를 새로 발급받는 것을 추천합니다.")
