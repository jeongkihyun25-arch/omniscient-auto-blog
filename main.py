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

# 기현님의 6개 고정 라벨
MY_LABELS = ["여행 교통 팁", "여행 준비 팁", "여행 관광 팁", "건강 정보", "경제 이슈", "IT 트렌드"]

def call_gemini(prompt, max_tokens=8192):
    # 1.5 Flash 모델이 속도와 안정성 면에서 자동화에 가장 적합합니다.
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": max_tokens}
    }
    try:
        res = requests.post(url, json=payload, timeout=180)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f"⚠️ Gemini 호출 에러: {e}")
        return None

def post_to_blogger(title, content, label, slug):
    try:
        creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON))
        service = build('blogger', 'v3', credentials=creds)
        body = {
            "kind": "blogger#post",
            "title": title,
            "content": content,
            "labels": [label],
            "customMetaData": slug, # 맞춤 퍼머링크용
            "blog": {"id": BLOG_ID}
        }
        service.posts().insert(blogId=BLOG_ID, body=body, isDraft=False).execute()
        return True
    except Exception as e:
        print(f"⚠️ 블로그 게시 에러: {e}")
        return False

if __name__ == "__main__":
    now = datetime.now()
    print(f"🚀 {now.strftime('%Y-%m-%d')} 기현님 40세 생일 기념 엔진 가동")

    # 1. 수익성 주제 선정 및 라벨 매칭
    strategy_prompt = f"""
    현재 날짜: {now.strftime('%Y-%m-%d')}. 구글 검색 트렌드를 분석해서 고단가 키워드 주제를 정해줘.
    라벨 후보: {MY_LABELS}
    답변은 반드시 아래 형식만 지킬 것 (다른 설명 금지):
    주제: [제목] / 라벨: [후보 중 하나] / 슬러그: [영문-소문자-주소]
    """
    strategy = call_gemini(strategy_prompt)
    print(f"📝 AI 전략 수립: {strategy}")

    try:
        target_title = re.search(r'주제:\s*(.*?)\s*/', strategy).group(1)
        target_label = re.search(r'라벨:\s*(.*?)\s*/', strategy).group(1).strip()
        target_slug = re.search(r'슬러그:\s*(.*)', strategy).group(1).strip()
        if target_label not in MY_LABELS: target_label = "IT 트렌드"
    except:
        target_title = f"오늘의 경제 및 트렌드 리포트 - {now.strftime('%Y-%m-%d')}"
        target_label = "경제 이슈"
        target_slug = f"daily-report-{now.strftime('%Y%m%d')}"

    # 2. 1만 자 분량의 3단계 분할 집필 (기현님 스타일 가이드 준수)
    full_content = ""
    writing_steps = [
        "핵심 요약 및 혜택 (🌸 이모지로 시작, 서론 절대 금지, 바로 정보 제공, 3500자)",
        "심층 데이터 분석 및 가이드 (표와 리스트 사용, 양양 거주자나 GN7 오너의 관점 1개 포함, 4000자)",
        "실제 사례 및 외부 공식 링크 5개 이상 포함한 결론 (3000자)"
    ]

    for step in writing_steps:
        prompt = f"""
        주제: {target_title}
        구간: {step}
        규칙: 20년 차 베테랑 말투, HTML 태그 사용, 텍스트가 없는 자연스러운 손그림 스타일 이미지 묘사 삽입.
        """
        part = call_gemini(prompt, 8000)
        if part: full_content += part + "\n\n"
        time.sleep(5) # API 안정성 확보

    # 3. 최종 게시
    if len(full_content) > 1000:
        if post_to_blogger(target_title, full_content, target_label, target_slug):
            print(f"✅ 게시 완료: {target_title} (라벨: {target_label})")
        else:
            print("❌ 게시 실패")
    else:
        print("❌ 본문 생성량 부족으로 중단")
