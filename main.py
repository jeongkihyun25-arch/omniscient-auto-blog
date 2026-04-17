import os
import json
import requests
import time
import re
from bs4 import BeautifulSoup
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ==================== [1] 설정 로드 (GitHub Secrets 연동) ====================
API_KEY = os.getenv("GEMINI_API_KEY")
BLOG_ID = os.getenv("BLOG_ID")
TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")

# 기현님의 블로그 라벨 6개
MY_LABELS = ["여행 교통 팁", "여행 준비 팁", "여행 관광 팁", "건강 정보", "경제 이슈", "IT 트렌드"]

# ==================== [2] 핵심 엔진 함수 ====================

def call_gemini(prompt, max_tokens=8192):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.8, "maxOutputTokens": max_tokens}
    }
    try:
        res = requests.post(url, json=payload, timeout=120)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except: return None

def post_to_blogger(title, content, label, slug):
    creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON))
    service = build('blogger', 'v3', credentials=creds)
    body = {
        "title": title,
        "content": content,
        "labels": [label],
        "customMetaData": slug, # 맞춤 퍼머링크용
        "blog": {"id": BLOG_ID}
    }
    service.posts().insert(blogId=BLOG_ID, body=body, isDraft=False).execute()

# ==================== [3] 메인 실행 프로세스 ====================

if __name__ == "__main__":
    now = datetime.now()
    print(f"🚀 {now.strftime('%Y-%m-%d')} 기현님의 40세 생일 기념 자동 포스팅 엔진 가동")

    # 1. 실시간 트렌드 분석 및 주제/라벨 선정
    strategy_prompt = f"""
    현재 날짜: {now.strftime('%Y-%m-%d')}. 오늘 한국에서 가장 이슈가 될만한 수익성 높은 주제 하나를 선정해줘.
    기현님의 블로그 라벨 {MY_LABELS} 중 하나를 반드시 선택해야 함.
    형식: [주제: 제목 / 라벨: 라벨명 / 슬러그: 영문-슬러그]
    """
    strategy = call_gemini(strategy_prompt)
    
    # 데이터 추출
    try:
        title = re.search(r'주제:\s*(.*?)\s*/', strategy).group(1)
        label = re.search(r'라벨:\s*(.*?)\s*/', strategy).group(1)
        slug = re.search(r'슬러그:\s*(.*)', strategy).group(1).strip()
    except:
        title = f"최신 정보 업데이트 - {now.strftime('%Y-%m-%d')}"
        label = "IT 트렌드"
        slug = f"update-{now.strftime('%Y%m%d')}"

    # 2. 1만 자 분할 집필 (기현님 스타일 가이드: 서론 금지, 🌸 시작)
    full_html = ""
    sections = [
        "도입부 및 핵심 요약 (🌸 시작, 독자 혜택 위주, 3500자)",
        "상세 가이드 및 전문 분석 (표/리스트 포함, 4000자)",
        "꿀팁 및 관련 공식 사이트 외부 링크 6개 포함 결론 (3000자)"
    ]

    for section in sections:
        write_prompt = f"""
        주제: {title}
        작성 구간: {section}
        규칙: 20년 차 베테랑 말투, HTML 형식, 압도적 분량, 외부 링크 포함.
        이미지 요청: '내부에 텍스트가 없는 자연스러운 손그림 스타일' 묘사 포함.
        """
        full_html += (call_gemini(write_prompt, 10000) or "") + "\n\n"
        time.sleep(2) # API 과부하 방지

    # 3. 블로그 게시
    post_to_blogger(title, full_html, label, slug)
    print(f"✨ 게시 완료: {title} (라벨: {label})")
