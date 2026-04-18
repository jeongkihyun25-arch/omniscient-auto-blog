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

# ==================== [1] 설정 및 기존 API 로직 (유지) ====================
API_KEY = os.getenv("GEMINI_API_KEY")
BLOG_ID = "6254424106586242042" # 기현님 블로그 ID 고정
COOKIES_JSON = os.getenv("BLOGGER_COOKIES")

# 기현님이 검증하신 릴레이 로직
MODEL_RELAY = ["models/gemini-2.0-flash", "models/gemini-1.5-flash", "models/gemini-1.5-pro"]

def call_gemini_relay(prompt, max_tokens=8192):
    for model_name in MODEL_RELAY:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={API_KEY}"
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": max_tokens}}
        try:
            res = requests.post(url, json=payload, timeout=60).json()
            if 'candidates' in res:
                return res['candidates'][0]['content']['parts'][0]['text'].strip()
        except: continue
    return None

# ==================== [2] 셀레니움 게시 함수 (쿠키 활용) ====================

def post_to_blogger_selenium(title, content):
    options = Options()
    options.add_argument("--headless") # 서버용
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        # 1. 도메인 접속 및 쿠키 주입
        driver.get("https://www.blogger.com")
        time.sleep(2)
        cookies = json.loads(COOKIES_JSON)
        for cookie in cookies:
            # 셀레니움 쿠키 형식에 맞춰 필요 없는 항목 제거
            if 'expirationDate' in cookie: cookie['expiry'] = int(cookie.pop('expirationDate'))
            if 'id' in cookie: cookie.pop('id')
            driver.add_cookie(cookie)
        
        # 2. 새 글 쓰기 페이지로 직접 이동
        driver.get(f"https://www.blogger.com/blog/post/edit/new/{BLOG_ID}")
        wait = WebDriverWait(driver, 20)
        
        # 3. 제목 입력
        title_area = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='제목']")))
        title_area.send_keys(title)
        print(f"✅ 제목 입력 완료: {title}")

        # 4. HTML 편집 모드로 전환 (매우 중요)
        # 에디터 하단의 연필 모양 아이콘 클릭 후 'HTML 보기' 선택 로직
        mode_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[aria-label='작성 모드']")))
        mode_button.click()
        html_view = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'HTML 보기')]")))
        html_view.click()
        time.sleep(2)

        # 5. 본문 입력 (HTML 코드를 직접 주입)
        content_area = driver.find_element(By.CSS_SELECTOR, "textarea.editable")
        driver.execute_script("arguments[0].value = arguments[1];", content_area, content)
        print("✅ 본문 1만 자 주입 완료")

        # 6. 게시 버튼 클릭
        publish_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), '게시')]")))
        publish_btn.click()
        confirm_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), '확인')]")))
        confirm_btn.click()
        
        print("✨ 블로그 게시 최종 성공!")
        return True
    except Exception as e:
        print(f"❌ 셀레니움 오류: {e}")
        return False
    finally:
        driver.quit()

# ==================== [3] 실행부 ====================
if __name__ == "__main__":
    now = datetime.now()
    # 1. 주제 및 본문 생성 (개인정보 언급 금지)
    pick_prompt = "구글 애드센스 고수익 주제 선정. [주제: 제목 / 라벨: 라벨명]"
    strategy = call_gemini_relay(pick_prompt)
    
    if strategy:
        target_title = re.search(r'주제:\s*(.*?)(?=\n|라벨:|$)', strategy).group(1).strip()
        print(f"🎯 주제: {target_title}")
        
        write_prompt = f"주제: {target_title}\n규칙: HTML 사용, 1만 자 이상, 필자 개인정보(양양, 차량, 나이) 절대 언급 금지."
        full_html = call_gemini_relay(write_prompt)
        
        if full_html:
            post_to_blogger_selenium(target_title, full_html)
