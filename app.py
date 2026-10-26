import streamlit as st
import pandas as pd
import requests
import time
import hmac
import hashlib
import base64
import urllib.parse
import re

# --- 1. 페이지 기본 설정 ---
st.set_page_config(page_title="나만의 키워드 채굴기", page_icon="⛏️", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    .grade-s { background-color: #059669; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .grade-a { background-color: #2563eb; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .grade-b { background-color: #d97706; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .grade-f { background-color: #dc2626; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 2. 네이버 검색광고 서명 생성 ---
def generate_signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    signature = hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).digest()
    return base64.b64encode(signature).decode('utf-8')

# --- 3. 블로그 최근 1개월 발행량 수집 (모바일 검색 실제 패킷 추출) ---
def get_naver_blog_count(keyword):
    encoded_kw = urllib.parse.quote(keyword)
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 NAVER(inapp; search; 1000; 12.0.0)",
        "Referer": "https://m.search.naver.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9"
    }

    # 1) 모바일 블로그 탭 최근 1개월(1m) 쿼리
    url = f"https://m.search.naver.com/search.naver?where=m_blog&query={encoded_kw}&sm=mtb_opt&nso=so:r,p:1m"
    try:
        res = requests.get(url, headers=headers, timeout=5)
        text = res.text

        # 텍스트 내 총 건수 추출 정규표현식
        patterns = [
            r'class="[^"]*title_num[^"]*"[^>]*>[\s\S]*?/\s*([0-9,]+)건',
            r'/\s*([0-9,]+)건',
            r'class="sub_pack[^"]*"[\s\S]*?([0-9,]+)건',
            r'전체\s*<[^>]+>\s*([0-9,]+)\s*건',
            r'([0-9,]+)건\s*</span>',
            r'"totalCount":\s*([0-9]+)'
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                val = m.group(1).replace(',', '')
                if val.isdigit() and int(val) > 0:
                    return int(val)

        # 2) 스마트블록(VIEW) 검색 백업
        url_view = f"https://m.search.naver.com/search.naver?where=m_view&query={encoded_kw}&sm=mtb_opt&nso=so:r,p:1m"
        res_view = requests.get(url_view, headers=headers, timeout=5)
        for p in patterns:
            m = re.search(p, res_view.text)
            if m:
                val = m.group(1).replace(',', '')
                if val.isdigit() and int(val) > 0:
                    return int(val)
    except:
        pass
    return 0

# --- 4. 블릿AI 공식 등급 판정 로직 ---
def calculate_grade(search_vol, blog_cnt):
    if search_vol < 500:
        return "F"
    elif search_vol <= 1000:
        return "S" if blog_cnt <= 5 else ("A" if blog_cnt <= 15 else ("B" if blog_cnt <= 30 else "F"))
    elif search_vol <= 3000:
        return "S" if blog_cnt <= 10 else ("A" if blog_cnt <= 30 else ("B" if blog_cnt <= 60 else "F"))
    elif search_vol <= 5000:
        return "S" if blog_cnt <= 30 else ("A" if blog_cnt <= 50 else ("B" if blog_cnt <= 80 else "F"))
    elif search_vol <= 10000:
        return "S" if blog_cnt <= 50 else ("A" if blog_cnt <= 100 else ("B" if blog_cnt <= 150 else "F"))
    elif search_vol <= 30000:
        return "S" if blog_cnt <= 100 else ("A" if blog_cnt <= 150 else ("B" if blog_cnt <= 250 else "F"))
    elif search_vol <= 100000:
        return "S" if blog_cnt <= 150 else ("A" if blog_cnt <= 250 else ("B" if blog_cnt <= 450 else "F"))
    else:
        return "S" if blog_cnt <= 200 else ("A" if blog_cnt <= 350 else ("B" if blog_cnt <= 600 else "F"))

# --- 5. UI 화면 ---
st.title("⛏️ 나만의 키워드 채굴기")
st.caption("네이버 검색량과 실시간 최근 1개월 블로그 발행량을 분석하여 S부터 F까지 등급을 판정합니다.")

with st.sidebar:
    st.header("🔑 네이버 검색광고 API 키")
    customer_id = st.text_input("CUSTOMER ID", type="password")
    api_key = st.text_input("API KEY (액세스라이선스)", type="password")
    secret_key = st.text_input("SECRET KEY (비밀키)", type="password")

query = st.text_input("분석할 대표 키워드를 입력하세요", placeholder="예: 노브랜드몰, 부천맛집")

if st.button("🚀 키워드 채굴 시작", use_container_width=True):
    if not (customer_id and api_key and secret_key):
        st.warning("왼쪽 사이드바에 검색광고 API 키 3개를 먼저 입력해 주세요!")
    elif not query:
        st.warning("검색할 키워드를 입력해 주세요.")
    else:
        progress_text = st.empty()
        progress_bar = st.progress(0)
        
        try:
            base_url = "https://api.naver.com"
            uri = "/keywordstool"
            timestamp = str(round(time.time() * 1000))
            sig = generate_signature(timestamp, "GET", uri, secret_key)
            headers = {
                "X-Timestamp": timestamp,
                "X-API-KEY": api_key.strip(),
                "X-Customer": str(customer_id).strip(),
                "X-Signature": sig
            }
            params = {"hintKeywords": query.replace(" ", ""), "showDetail": 1}
            ad_res = requests.get(base_url + uri, params=params, headers=headers).json()
            keywords_data = ad_res.get('keywordList', [])[:25]

            result_list = []
            total_items = len(keywords_data)

            for idx, item in enumerate(keywords_data):
                kw = item['relKeyword']
                progress_text.text(f"분석 중 ({idx+1}/{total_items}): {kw}")
                
                pc_cnt = int(item['monthlyPcQcCnt']) if str(item['monthlyPcQcCnt']).isdigit() else 5
                mo_cnt = int(item['monthlyMobileQcCnt']) if str(item['monthlyMobileQcCnt']).isdigit() else 5
                total_search = pc_cnt + mo_cnt

                monthly_pub = get_naver_blog_count(kw)
                grade = calculate_grade(total_search, monthly_pub)

                result_list.append({
                    "등급": grade,
                    "키워드": kw,
                    "월 검색량": total_search,
                    "월 발행량": monthly_pub,
                })
                progress_bar.progress((idx + 1) / total_items)
                time.sleep(0.12)

            progress_text.empty()
            progress_bar.empty()
            st.session_state['result_df'] = pd.DataFrame(result_list)
            st.success("키워드 채굴 완료!")

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")

# --- 6. 결과 출력 및 필터 ---
if 'result_df' in st.session_state:
    df = st.session_state['result_df']

    s_cnt = len(df[df['등급'] == 'S'])
    a_cnt = len(df[df['등급'] == 'A'])
    b_cnt = len(df[df['등급'] == 'B'])
    f_cnt = len(df[df['등급'] == 'F'])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("S (황금)", f"{s_cnt}개")
    c2.metric("A 등급", f"{a_cnt}개")
    c3.metric("B 등급", f"{b_cnt}개")
    c4.metric("F 등급", f"{f_cnt}개")

    grade_choice = st.multiselect(
        "필터링할 등급을 선택하세요",
        options=["S", "A", "B", "F"],
        default=["S", "A", "B", "F"]
    )

    filtered = df[df['등급'].isin(grade_choice)].sort_values(by=["등급", "월 검색량"], ascending=[True, False])
    st.dataframe(filtered, use_container_width=True, hide_index=True)

    csv = filtered.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 엑셀(CSV)로 다운로드", data=csv, file_name=f"{query}_채굴결과.csv")
