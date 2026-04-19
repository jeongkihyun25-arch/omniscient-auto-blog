ㅊ

# ==================== [4] 유동적 SVG 요약 카드 ====================
def create_summary_card_tag(summary_list, title):
    safe_list = [str(s).strip()[:15] for s in summary_list if s][:3]
    while len(safe_list) < 3: safe_list.append("") 
    l1, l2, l3 = safe_list

    svg_code = f"""
    <svg width="600" height="230" xmlns="http://www.w3.org/2000/svg">
      <rect width="600" height="230" fill="#FFF9C4" rx="20"/>
      <text x="50%" y="70" font-family="'Apple Color Emoji', 'Segoe UI Emoji', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="30" text-anchor="middle" fill="#2c3e50">{l1}</text>
      <text x="50%" y="130" font-family="'Apple Color Emoji', 'Segoe UI Emoji', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="30" text-anchor="middle" fill="#2c3e50">{l2}</text>
      <text x="50%" y="190" font-family="'Apple Color Emoji', 'Segoe UI Emoji', 'Malgun Gothic', sans-serif" font-weight="bold" font-size="30" text-anchor="middle" fill="#2c3e50">{l3}</text>
    </svg>
    """
    b64_svg = base64.b64encode(svg_code.encode('utf-8')).decode('utf-8')
    data_uri = f"data:image/svg+xml;base64,{b64_svg}"
    return f'<div style="text-align:center; margin:40px 0;"><img src="{data_uri}" style="max-width:100%; height:auto; border-radius:15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);" alt="{title} 핵심 요약 카드"/></div>'

# ==================== [5] 원고 생성 (🔥 SEO 끝판왕 마스터 프롬프트) ====================
def generate_master_content():
    keyword, reference_blogs, target_blog_url, scraped_data = get_naver_target_data()
    best_model = get_best_model()
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(best_model)

    prompt = f"""
[타겟 키워드]: {keyword}
[🔥 집중 분석 타겟 (실제 1위 블로그 뼈대 + 서브 블로그 4개 후기 합본)]: 
{scraped_data}

[미션]: 위 [집중 분석 타겟]의 텍스트를 해부하여 억지로 늘린 내용 없이 '밀도 높은' 초고품질 딥다이브 포스팅으로 작성하라. 여행 글은 단순한 정보 나열이 아니라, 검색한 사람이 '결정'하게 만들고 '손해를 막아주는' 콘텐츠여야 한다.

[🔥 상위 노출 & 체류시간 폭발 카피라이팅 지시사항 - 절대 엄수]:
1. **검색 의도에 맞는 제목 변주 (CTR 최적화)**: 무조건 자극적인 제목만 쓰지 마라. 키워드에 따라 70%는 '손해/숫자/상황'을 결합한 자극형(예: "이거 안 하면 요금 3배 나옵니다")으로, 30%는 신뢰감을 주는 '정보/해결형'(예: "인천공항 스마트패스 등록부터 사용까지 총정리")으로 상황에 맞게 유연하게 적용하라. 끝에 "(실제 후기)" 등을 붙여라.
2. **🔥 검색 의도(타입)별 맞춤형 글 구조 (순위 상승의 핵심)**: 키워드를 분석하여 아래 3가지 타입 중 하나로 구조를 변형하라.
   - **돈/비용형 (예: eSIM, 항공권)**: '문제 제기 -> 손해 강조 -> 해결책 -> 비교' 위주로 작성.
   - **방법/절차형 (예: 스마트패스, 공항 이용)**: 독자가 그대로 따라 할 수 있는 '순서 설명(Step-by-step)' 파트를 반드시 추가.
   - **추천형 (예: 맛집, 숙소)**: 단순 나열 금지. '상황별 추천(가족 vs 혼자)'과 명확한 '대안 비교' 위주로 작성.
3. **🔥 공통 필수 구조 및 5가지 요소**:
   - 도입부는 공감 유도형 '문제 제기'로 시작 (첫 3줄 이내).
   - "이유 + 상황 + 결과"가 포함된 사람 냄새나는 생생한 찐 후기 3줄 추가. (예: "실제로 이 방법 쓰고 위탁 안 맡겼더니 30분 절약됨")
   - 숫자(시간/돈), 비교(전/후), 실수 포인트, 상황, 감정 묘사를 본문 곳곳에 녹여라.
4. **외부 링크 최적화 (2~3개만 엄선)**: 외부 링크 과다는 SEO 점수를 깎는다. 문맥상 꼭 필요한 구글 맵스 장소 링크나 구글 검색 링크만 딱 2~3개로 줄여서 자연스럽게 배치하라. 모두 target="_blank" 적용.
   - 장소: <a href="https://www.google.com/maps/search/?api=1&query=장소명+띄어쓰기+대체" target="_blank"> (띄어쓰기는 '+' 기호로 대체)
5. **광고/협찬 원천 차단 (브랜드 세탁)**: 원본 글에 특정 브랜드 홍보가 있다면 싹 지우고, 객관적인 '선택 기준'이나 '방법론'으로 필터링하라.
6. **시간적 표현 절대 금지**: "2026년", "최신", "올해", "현재", "최근" 일절 금지.
7. **AI 멘트 원천 차단**: "출처를 종합했다", "알아보겠습니다" 금지.
8. **🔥 구조화 및 HTML 양식 강제 적용 (패턴화 방지!)**:
   아래의 HTML '구조'를 지키되, AI 템플릿처럼 보이지 않도록 매번 변형해라. 특히 목차의 href와 본문 h2의 id는 'sec1' 같은 고정 단어 대신, **해당 문단의 핵심 키워드를 영문으로 번역한 고유 단어**(예: id="esim-cost", id="smartpass-register")를 매번 다르게 생성하여 스크롤 앵커를 연결하라!
   ```html
   <p class="intro">[현재 키워드에 맞춰 독자의 뼈를 때리는 공감/문제제기 1~2줄]</p>
   <nav>
     <ul>
       <li><a href="#[매번_바뀌는_영문ID_1]">1. [시선을 끄는 소제목]</a></li>
       <li><a href="#[매번_바뀌는_영문ID_2]">2. [핵심 꿀팁 소제목]</a></li>
     </ul>
   </nav>
   <h2 id="[매번_바뀌는_영문ID_1]">1. [시선을 끄는 소제목]</h2>
   <p>내용...</p>
   <h2 id="[매번_바뀌는_영문ID_2]">2. [핵심 꿀팁 소제목]</h2>
   <p>내용...</p>
   ```
9. **SVG 3줄 요약**: 'summary' 필드에 **[이모지 1개 + 띄어쓰기 포함 6글자 이하의 명사형 단어]** 3개 배열 반환.
10. **슬러그(URL)**: 한글 제목에서 핵심 키워드 2~3개만 뽑아 짧은 영어 단어 조합으로 생성 (예: flight-ticket-hacks).
11. **🔥 카테고리(라벨) 강제 지정**: 너가 작성한 글의 주제와 가장 완벽하게 일치하는 카테고리를 다음 리스트 중에서 딱 1개만 골라 정확한 텍스트로 반환하라. -> ["여행 교통 팁", "여행 쇼핑 팁", "여행 관광 팁", "여행 준비 팁", "여행 맛집 팁", "생활 정보 꿀팁"]

[출력 포맷]: JSON (title, meta_desc, meta_keys, slug, summary, content, category)
"""
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"✍️ [4/5] 제미나이 원고 작성 중... (시도 {attempt + 1}/{max_retries})")
            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text.replace("```json", "", 1).strip()
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3].strip()

            data = json.loads(raw_text)
            data['used_references'] = [target_blog_url]
            return data
            
        except Exception as e: 
            print(f"⚠️ 제미나이 JSON 문법 오류 발생 (재시도 준비 중...): {e}")
            time.sleep(5)
            
    print("❌ 제미나이가 3번 연속으로 헛소리를 했습니다. 원고 생성을 포기합니다.")
    return None

# ==================== [6] 실행 및 블로거 업로드 ====================
def run_automation():
    print("🚀 [2/5] 프로세스 시작...")
    try:
        token_base64 = os.environ.get("BLOGGER_TOKEN_PKL")
        if token_base64:
            with open('token.json', 'wb') as f:
                f.write(base64.b64decode(token_base64))
            print("✅ [3/5] 인증 토큰 복구 완료")

        data = generate_master_content()
        if not data: 
            print("❌ 원고 생성 실패")
            return
        
        print("-" * 50)
        print(f"📚 [딥다이브 타겟 블로그 (실제 본문 스크래핑 완료)]")
        for ref in data.get('used_references', []):
            print(f"🔗 {ref}")
        print("-" * 50)
        
        ads_code = """
        <div style="margin:45px 0;">
            <script async src="[https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2303846706279700](https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2303846706279700)" crossorigin="anonymous"></script>
            <ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-2303846706279700" data-ad-slot="1632085406" data-ad-format="auto" data-full-width-responsive="true"></ins>
            <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
        </div>
        """
        
        card_tag = create_summary_card_tag(data.get('summary', []), data['title'])
        content = data['content']

        # 🔥 서론 -> 목차 -> 요약카드(SVG) -> 애드센스 1 -> 본문 (순서 보장 로직)
        top_insertion = f"{card_tag}{ads_code}"
        
        if re.search(r'</nav>', content, re.IGNORECASE):
            content = re.sub(r'(</nav>)', f'\\1{top_insertion}', content, flags=re.IGNORECASE, count=1)
        elif re.search(r'</p>', content, re.IGNORECASE):
            content = re.sub(r'(</p>)', f'\\1{top_insertion}', content, flags=re.IGNORECASE, count=1)
        else:
            content = top_insertion + content

        h2_parts = content.split("<h2") 
        if len(h2_parts) >= 3:
            mid_index = len(h2_parts) // 2
            h2_parts[mid_index] = ads_code + "<h2" + h2_parts[mid_index]
            content = "<h2".join(h2_parts)

        content = content + ads_code

        final_html = f"""
        <meta name="description" content="{data.get('meta_desc', '')}">
        <meta name="keywords" content="{data.get('meta_keys', '')}">
        <style>
            html {{ scroll-behavior: smooth; }}
            .entry-content {{ font-size: 18px; line-height: 2.0; color: #333; font-family: 'Malgun Gothic', sans-serif; }}
            .entry-content h2 {{ font-size: 28px; color: #2c3e50; border-left: 10px solid #3498db; padding: 10px 15px; margin: 55px 0 25px; background: #f9f9f9; scroll-margin-top: 120px; }}
            .entry-content h3 {{ font-size: 23px; color: #2980b9; border-bottom: 2px solid #3498db; padding-bottom: 8px; margin: 35px 0 20px; scroll-margin-top: 120px; }}
            .entry-content p {{ margin-bottom: 25px; }}
            .entry-content table {{ width: 100%; border-collapse: collapse; margin: 30px 0; }}
            .entry-content th {{ background: #3498db; color: white; padding: 12px; }}
            .entry-content td {{ border: 1px solid #ddd; padding: 12px; text-align: center; }}
            .entry-content .intro {{ background: #f0f7ff; padding: 15px 20px; border-radius: 10px; border-left: 5px solid #3498db; margin-bottom: 30px; font-weight: bold; font-size: 17px; line-height: 1.6; }}
            .entry-content nav {{ background: #f8f9fa; padding: 25px; border-radius: 10px; border: 1px solid #eee; margin-bottom: 30px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            .entry-content nav ul {{ list-style: none; padding-left: 0; }}
            .entry-content nav li {{ margin-bottom: 12px; font-size: 19px; }}
            .entry-content nav a {{ color: #2980b9; text-decoration: none; font-weight: bold; }}
            .entry-content nav a:hover {{ text-decoration: underline; color: #e74c3c; }}
            b {{ color: #e74c3c; }}
        </style>
        <div class="entry-content">{content}</div>
        """

        # 🔥 제미나이가 골라준 카테고리 적용 로직
        chosen_category = data.get('category', '').strip()
        if chosen_category not in LABEL_OPTIONS:
            chosen_category = "여행 준비 팁" 
        
        final_labels = [chosen_category]
        print(f"🏷️ [적용된 카테고리]: {chosen_category}")

        with open('token.json', 'rb') as t:
            creds = pickle.load(t)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
        
        service = build('blogger', 'v3', credentials=creds)
        
        # 1단계: 영어 슬러그 확보용 초안
        slug_text = data.get('slug', 'auto-post')
        if not slug_text.strip(): slug_text = "auto-post"
        print(f"🚀 [5/5] 주소 생성용 트릭 실행 중... ({slug_text})")
        
        temp_post = service.posts().insert(blogId=BLOG_ID, body={
            "title": slug_text, 
            "content": "loading...",
            "labels": final_labels
        }, isDraft=False).execute()

        # 2단계: 진짜 한글 제목 덮어쓰기
        print(f"🚀 [5/5] 진짜 한글 제목 덮어쓰는 중... ({data['title']})")
        service.posts().patch(blogId=BLOG_ID, postId=temp_post['id'], body={
            "title": data['title'], 
            "content": final_html,
            "customMetaData": data.get('meta_desc', '')
        }).execute() 
        
        print(f"✨ [완료] 최종 성공: {data['title']}")

    except Exception as e: print(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    run_automation()
