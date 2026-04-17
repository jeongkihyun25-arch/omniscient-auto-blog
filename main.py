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

# 구글이 절대 못 찾는다고 발뺌 못할 모델 리스트
MODEL_RELAY = [
    "gemini-1.5-flash-latest", 
    "gemini-1.5-pro-latest",
    "gemini-2.0-flash-exp",
    "gemini-1.5-flash"
]

def call_gemini_relay(prompt, max_tokens=8192):
    for model_id in MODEL_RELAY:
        # 모델명 앞에 models/가 붙어야 하는 경우와 아닌 경우를 대비
        full_model_name = f"models/{model_id}" if "models/" not in model_id else model_id
        
        # v1beta 주소 사용
        url = f"https://generativelanguage.googleapis.com/v1beta/{full_model_name}:generateContent?key={API_KEY}"
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 1.0, "maxOutputTokens": max_tokens}
        }
        
        try:
            print(f"📡 {full_model_name} 호출 시도 중...")
            res = requests.post(url, json=payload, timeout=60)
            res_json = res.json()
            
            if 'candidates' in res_json:
                print(f"✅ {full_model_name} 호출 성공!")
                return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            
            # 할당량 초과 에러일 경우 즉시 다음 모델로
            error_msg = res_json.get('error', {}).get('message', '')
            print(f"⚠️ {full_model_name} 실패: {error_msg}")
            
            if "quota" in error_msg.lower():
                print("💡 할당량 초과로 다음 모델로 즉시 넘어갑니다.")
                continue
                
        except Exception as e:
            print(f"⚠️ 에러 발생: {e}")
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
    print(f"🚀 {now.strftime('%Y-%m-%d')} 40세 생일 기념 최종 가동")

    # 1. 주제 선정 (최대한 가벼운 요청으로 시작)
    pick_prompt = "수익형 블로그 고단가 주제 1개 추천해줘. 형식 [주제: 제목 / 라벨: 라벨명 / 슬러그: 영문]"
    strategy = call_gemini_relay(pick_prompt, 1000)
    
    if strategy:
        try:
            target_title = re.search(r'주제:\s*(.*?)(?=/|\n|$)', strategy).group(1).strip()
            target_label = re.search(r'라벨:\s*(.*?)(?=/|\n|$)', strategy).group(1).strip()
            target_slug = re.search(r'슬러그:\s*(.*)', strategy).group(1).strip()
        except:
            target_title = "재테크 황금 공식"; target_label = "재테크"; target_slug = "money-tips"

        # 2. 본문 생성 (개인정보 언급 금지 지시 포함)
        print(f"✍️ '{target_title}' 주제로 본문 작성 시작...")
        write_prompt = f"주제: {target_title}\n규칙: HTML 사용, 1만 자 이상, 필자 개인신상(양양, 차량, 가족) 언급 금지."
        full_html = call_gemini_relay(write_prompt, 8000)

        # 3. 게시
        if full_html and len(full_html) > 500:
            if post_to_blogger(target_title, full_html, target_label, target_slug):
                print(f"✨ 드디어 대성공! 생일 선물로 블로그 포스팅이 완료되었습니다!")
    else:
        print("❌ 모든 모델이 거부했습니다. API 키를 새로 발급받거나 1시간 뒤에 시도해 보세요.")
