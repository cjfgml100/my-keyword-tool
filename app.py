import streamlit as st
import pandas as pd
import requests
import time
import hmac
import hashlib
import base64
import urllib.parse
from datetime import datetime, timedelta

# --- 1. 페이지 설정 ---
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

# --- 3. 최근 1개월 블로그 발행량 조회 ---
def get_recent_monthly_blog_count(keyword, client_id, client_secret):
    try:
        encoded_kw = urllib.parse.quote(keyword)
        url = f"https://openapi.naver.com/v1/search/blog.json?query={encoded_kw}&display=100&sort=date"
        headers = {
            "X-Naver-Client-Id": client_id.strip(),
            "X-Naver-Client-Secret": client_secret.strip()
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            items = data.get('items', [])
            total_docs = data.get('total', 0)
            
            if not items:
                return 0
            
            # 기준일: 최근 30일 계산
            cutoff_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
            
            recent_count = 0
            oldest_item_date = items[-1].get('postdate', '')
            
            for item in items:
                pdate = str(item.get('postdate', '')).strip()
                if pdate >= cutoff_date:
                    recent_count += 1
                else:
                    break
            
            # 100건 모두 최근 30일 이내에 작성된 대형 키워드인 경우
            if recent_count == 100 and oldest_item_date >= cutoff_date:
                # 첫 글과 100번째 글의 일수 차이를 이용한 월 환산
                try:
                    d_new = datetime.strptime(items[0]['postdate'], '%Y%m%d')
                    d_old = datetime.strptime(items[-1]['postdate'], '%Y%m%d')
                    days_diff = max((d_new - d_old).days, 1)
                    estimated_monthly = int((100 / days_diff) * 30)
                    return min(estimated_monthly, total_docs)
                except:
                    return 100
            
            return recent_count
        return 0
    except:
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

# --- 5. UI 및 분석 실행 ---
st.title("⛏️ 나만의 키워드 채굴기")
st.caption("네이버 월 검색량과 최근 1개월 블로그 발행량을 분석해 S~F 등급을 판정합니다.")

with st.sidebar:
    st.header("🔑 1. 네이버 검색광고 API 키")
    customer_id = st.text_input("CUSTOMER ID", type="password")
    api_key = st.text_input("API KEY (액세스라이선스)", type="password")
    secret_key = st.text_input("SECRET KEY (비밀키)", type="password")
    
    st.markdown("---")
    st.header("🔑 2. 네이버 공식 검색 API 키")
    dev_client_id = st.text_input("Client ID", type="password")
    dev_client_secret = st.text_input("Client Secret", type="password")

query = st.text_input("분석할 대표 키워드를 입력하세요", placeholder="예: 노브랜드몰, 부천맛집")

col_a, col_b = st.columns(2)
with col_a:
    limit_cnt = st.slider("분석할 연관 키워드 수", min_value=5, max_value=50, value=20)
with col_b:
    min_search = st.number_input("최소 월 검색량", min_value=0, value=500, step=100)

if st.button("🚀 키워드 채굴 시작", use_container_width=True):
    if not (customer_id and api_key and secret_key):
        st.warning("사이드바에 네이버 검색광고 API 키 3개를 입력해 주세요.")
    elif not (dev_client_id and dev_client_secret):
        st.warning("사이드바에 공식 검색 API Client ID와 Client Secret을 입력해 주세요.")
    elif not query:
        st.warning("분석할 키워드를 입력해 주세요.")
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
            keywords_data = ad_res.get('keywordList', [])[:limit_cnt]

            result_list = []
            total_items = len(keywords_data)

            for idx, item in enumerate(keywords_data):
                kw = item['relKeyword']
                progress_text.text(f"분석 중 ({idx+1}/{total_items}): {kw}")
                
                pc_cnt = int(item['monthlyPcQcCnt']) if str(item['monthlyPcQcCnt']).isdigit() else 5
                mo_cnt = int(item['monthlyMobileQcCnt']) if str(item['monthlyMobileQcCnt']).isdigit() else 5
                total_search = pc_cnt + mo_cnt

                if total_search < min_search:
                    progress_bar.progress((idx + 1) / total_items)
                    continue

                blog_cnt = get_recent_monthly_blog_count(kw, dev_client_id, dev_client_secret)
                grade = calculate_grade(total_search, blog_cnt)

                result_list.append({
                    "등급": grade,
                    "키워드": kw,
                    "월 검색량": total_search,
                    "월 발행량": blog_cnt,
                })
                progress_bar.progress((idx + 1) / total_items)
                time.sleep(0.05)

            progress_text.empty()
            progress_bar.empty()
            st.session_state['result_df'] = pd.DataFrame(result_list)
            st.success("키워드 채굴 완료!")

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")

# --- 6. 결과 출력 및 필터 ---
if 'result_df' in st.session_state and not st.session_state['result_df'].empty:
    df = st.session_state['result_df']

    s_cnt = len(df[df['등급'] == 'S'])
    a_cnt = len(df[df['등급'] == 'A'])
    b_cnt = len(df[df['등급'] == 'B'])
    f_cnt = len(df[df['등급'] == 'F'])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("S 등급", f"{s_cnt}개")
    c2.metric("A 등급", f"{a_cnt}개")
    c3.metric("B 등급", f"{b_cnt}개")
    c4.metric("F 등급", f"{f_cnt}개")

    grade_choice = st.multiselect(
        "필터링할 등급",
        options=["S", "A", "B", "F"],
        default=["S", "A", "B", "F"]
    )

    filtered = df[df['등급'].isin(grade_choice)].sort_values(by=["등급", "월 검색량"], ascending=[True, False])
    st.dataframe(filtered, use_container_width=True, hide_index=True)

    csv = filtered.to_csv(index=False).encode('utf-8-sig')
    st.download_button("CSV 다운로드", data=csv, file_name=f"{query}_채굴결과.csv")
elif 'result_df' in st.session_state and st.session_state['result_df'].empty:
    st.info("조건에 일치하는 키워드가 없습니다.")
