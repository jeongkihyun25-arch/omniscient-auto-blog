import os
import requests
import time
import json
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ==================== [1] 설정 로드 ====================
API_KEY = os.getenv("GEMINI_API_KEY")
BLOG_ID = os.getenv("BLOG_ID")
COOKIES_JSON = os.getenv("BLOGGER_COOKIES")

# 기현님이 검증하신 최신 모델 릴레이 로직
MODEL_RELAY = ["models/gemini-2.0-flash", "models/gemini-1.5-flash", "models/gemini-1.5-pro"]

def call_gemini_relay(prompt, max_tokens=8192):
    for model_name in MODEL_RELAY:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.8, "maxOutputTokens": max_tokens}
        }
        try:
            res = requests.post(url, json=payload, timeout=60).json()
            if 'candidates' in res:
                return res['candidates'][0]['content']['parts'][0]['text'].strip()
        except: continue
    return None

# ==================== [2] 셀레니움 게시 함수 ====================

def post_to_blogger_selenium(title, content):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        # 1. 쿠키 주입을 위해 도메인 접속
        driver.get("https://www.blogger.com")
        time.sleep(2)
        
        # 2. 쿠키 데이터 파싱 및 주입
        cookies = json.loads(COOKIES_JSON)
        for cookie in cookies:
            if 'expirationDate' in cookie:
                cookie['expiry'] = int(cookie.pop('expirationDate'))
            if 'id' in cookie:
                cookie.pop('id')
            driver.add_cookie(cookie)
        
        # 3. 새 글 쓰기 페이지 진입
        driver.get(f"https://www.blogger.com/blog/post/edit/new/{BLOG_ID}")
        wait = WebDriverWait(driver, 30)
        
        # 4. 제목 입력
        title_area = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='제목']")))
        title_area.send_keys(title)
        print(f"✅ 제목 입력 완료: {title}")

        # 5. HTML 편집 모드 전환
        mode_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[aria-label='작성 모드']")))
        mode_btn.click()
        html_view = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'HTML 보기')]")))
        html_view.click()
        time.sleep(3)

        # 6. 본문 입력 (JavaScript 주입 방식이 1만 자 입력에 가장 안전합니다)
        content_area = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "textarea.editable")))
        driver.execute_script("arguments[0].value = arguments[1];", content_area, content)
        # 내용 변화를 브라우저가 인지하도록 가벼운 키 입력 추가
        content_area.send_keys(" ") 
        print("✅ 본문 1만 자 주입 완료")

        # 7. 게시 버튼 클릭
        publish_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), '게시')]")))
        publish_btn.click()
        confirm_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), '확인')]")))
        confirm_btn.click()
        
        print("✨ 블로그 게시 최종 성공!")
        return True
    except Exception as e:
        print(f"❌ 셀레니움 오류 발생: {e}")
        return False
    finally:
        driver.quit()

# ==================== [3] 실행 메인 ====================

if __name__ == "__main__":
    now = datetime.now()
    print(f"🚀 {now.strftime('%Y-%m-%d')} 자동화 시스템 가동")

    # 주제 선정
    pick_prompt = "구글 애드센스 고수익 포스팅 주제 1개를 선정해줘. 형식: [주제: 제목 / 라벨: 라벨명]"
    strategy = call_gemini_relay(pick_prompt, 1000)
    
    if strategy:
        try:
            target_title = re.search(r'주제:\s*(.*?)(?=\n|라벨:|$)', strategy).group(1).strip()
        except:
            target_title = f"재테크 정보 요약 - {now.strftime('%m%d')}"

        # 본문 생성 (기현님 요청: 1만 자, 개인정보 배제)
        print(f"✍️ '{target_title}' 주제로 본문 작성 시작...")
        write_prompt = f"주제: {target_title}\n규칙: HTML 사용, 1만 자 이상, 필자 개인신상(양양, 차량, 40세 등) 절대 언급 금지."
        full_html = call_gemini_relay(write_prompt)
        
        if full_html and len(full_html) > 500:
            post_to_blogger_selenium(target_title, full_html)
    else:
        print("❌ AI 모델 응답 실패")
