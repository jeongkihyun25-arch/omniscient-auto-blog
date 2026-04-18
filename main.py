import os
import json
import requests
import time
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

API_KEY = os.getenv("GEMINI_API_KEY")
BLOG_ID = os.getenv("BLOG_ID")
BLOGGER_COOKIES = os.getenv("BLOGGER_COOKIES")

def get_best_model():
    print("🔍 Gemini 모델 탐색 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        res = requests.get(url, timeout=15).json()
        available = [m['name'].replace('models/', '') for m in res.get('models', [])
                     if 'generateContent' in m.get('supportedGenerationMethods', [])]
        priorities = ["gemini-2.5-flash-lite", "gemini-flash-latest", "gemini-2.0-flash"]
        for p in priorities:
            for m in available:
                if p in m:
                    print(f"🎯 선택 모델: {m}")
                    return m
        return available[0] if available else None
    except:
        return "gemini-2.5-flash-lite"


def call_gemini(prompt, max_tokens=8000):
    model_id = get_best_model()
    if not model_id:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={API_KEY}"
    for attempt in range(7):
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.75, "maxOutputTokens": max_tokens}
        }
        try:
            res = requests.post(url, json=payload, timeout=90)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            elif res.status_code == 429:
                time.sleep((2 ** attempt) * 7)
        except:
            pass
        time.sleep(4)
    return None


def post_to_blogger_selenium(title, content, label="여행 교통 팁", custom_slug=None):
    print("🌐 Selenium으로 Blogger 게시 시작...")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        driver.get("https://www.blogger.com")
        time.sleep(4)

        # 쿠키 주입
        if BLOGGER_COOKIES:
            try:
                cookies = json.loads(BLOGGER_COOKIES)
                for cookie in cookies:
                    if isinstance(cookie, dict):
                        driver.add_cookie(cookie)
                driver.refresh()
                time.sleep(5)
            except:
                print("⚠️ 쿠키 주입 실패")

        # 새 글 쓰기 페이지
        driver.get(f"https://www.blogger.com/blog/post/edit/new/{BLOG_ID}")
        wait = WebDriverWait(driver, 40)

        # 제목 입력
        title_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='제목']")))
        title_input.clear()
        title_input.send_keys(title)
        print(f"✅ 제목 입력 완료")

        # 라벨 입력 (당신이 준 selector)
        try:
            label_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "textarea[aria-label='쉼표로 라벨을 구분하세요.']")))
            label_input.clear()
            label_input.send_keys(label)
            print(f"✅ 라벨 입력: {label}")
        except:
            print("⚠️ 라벨 입력 스킵")

        # 맞춤 퍼머링크 (필요하면)
        if custom_slug:
            try:
                permalink_btn = driver.find_element(By.CSS_SELECTOR, "div.t5nRo.Id5V1")
                permalink_btn.click()
                time.sleep(2)
                slug_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='맞춤 퍼머링크 입력']")))
                slug_input.clear()
                slug_input.send_keys(custom_slug)
                print(f"✅ 퍼머링크 입력: {custom_slug}")
            except:
                pass

        # 본문 입력 (HTML 모드)
        content_area = wait.until(EC.presence_of_element_located((By.TAG_NAME, "textarea")))
        driver.execute_script("arguments[0].value = arguments[1];", content_area, content)
        print("✅ 본문 주입 완료")

        # 게시 버튼 클릭
        publish_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div.A2yzVd")))
        publish_btn.click()
        print("✅ 게시 버튼 클릭")

        # 확인 버튼 (마지막 팝업)
        confirm_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(),'확인')]")))
        confirm_btn.click()
        print("✅ 확인 버튼 클릭")

        time.sleep(10)
        print("✨ 블로그 게시 완료!")
        return True

    except Exception as e:
        print(f"❌ Selenium 오류: {e}")
        return False
    finally:
        driver.quit()


# ==================== 메인 ====================
if __name__ == "__main__":
    now = datetime.now()
    print(f"🚀 {now.strftime('%Y-%m-%d %H:%M')} 자동화 시작")

    # 주제 선정 (당신 블로그 스타일에 맞게)
    pick_prompt = "2026년 4월 기준으로 여행 실용 정보 블로그에 적합한 고클릭 예상 주제 하나를 추천해줘. 형식: 주제: [제목]"
    strategy = call_gemini(pick_prompt)

    if strategy:
        target_title = re.sub(r'^주제[:\s]*', '', strategy, flags=re.IGNORECASE).strip()
    else:
        target_title = "2026년 4월 해외여행 수하물 규정 완벽 정리"

    print(f"🎯 주제: {target_title}")

    write_prompt = f"""
주제: {target_title}
규칙: HTML 형식, 7000자 이상, 개인 정보 금지, 실용적이고 상세한 내용, 공식 링크 5개 이상 포함
"""
    full_html = call_gemini(write_prompt, 12000)

    if full_html and len(full_html) > 2000:
        print(f"✅ 본문 생성 완료 ({len(full_html):,}자)")
        post_to_blogger_selenium(target_title, full_html, label="여행 교통 팁")
    else:
        print("❌ 본문 생성 실패")
